"""
Degerlendirme: tum modelleri YAN YANA, ayni test seti uzerinde.

TASARIM KARARI: naive tabloya OPSIYONEL OLARAK EKLENMEZ -- HER ZAMAN ORADADIR.
Cagiran kisi onu listeden cikarsa bile evaluate() geri koyar. Sebep basit:
naive olmadan hicbir sayi anlam tasimaz. "RMSE 0.0184" cumlesi tek basina
bilgi degildir; naive 0.0181 ise model KOTUDUR ve bunu ancak yan yana
gorursen anlarsin.

Ayni sebeple skill_score her satirda hesaplanir ve model naive'i yenemiyorsa
tablonun altina acik bir UYARI basilir. Bu uyari susturulamaz.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from data.dataset import Dataset

from .baselines import NaiveModel, QuantileForecaster, default_baselines
from .metrics import evaluate_predictions, skill_score

# Tabloda gosterim sirasi
_COLS = [
    "model", "rmse_ret", "mae_ret", "pinball", "coverage", "nominal_cov",
    "width", "dir_acc", "n_calls", "rmse_price", "skill_score", "beats_naive",
]

# ONEMLI ESIK: skill_score'un SIFIRDAN buyuk olmasi yetmez, ANLAMLI
# olcude buyuk olmasi gerekir.
#
# Gunluk getiride skill_score +0.0005 gibi degerler rutin olarak cikar ve
# tamamen GURULTUDUR -- test dilimini bir gun kaydirsan isareti degisir.
# Esik olmadan "model naive'i yendi" diye rapor edersen kendi kendini
# kandirirsin. %1'lik RMSE iyilesmesi, bu problemde iddia edilebilecek
# en kucuk ciddi kazanctir.
MIN_SKILL = 0.01


def evaluate(
    dataset: Dataset,
    models: QuantileForecaster | list[QuantileForecaster] | None = None,
    *,
    with_baselines: bool = True,
    verbose: bool = True,
) -> pd.DataFrame:
    """
    Args:
        dataset: build_dataset() ciktisi. TEST dilimi burada -- ilk ve tek defa.
        models:  degerlendirilecek model(ler). Baseline'lar otomatik eklenir.

    Doner: her satiri bir model olan DataFrame, skill_score'a gore sirali.
    """
    if models is None:
        models = []
    elif isinstance(models, QuantileForecaster):
        models = [models]
    else:
        models = list(models)

    quantiles = tuple(models[0].quantiles) if models else (0.1, 0.5, 0.9)

    if with_baselines:
        models = default_baselines(quantiles) + models

    # --- naive sigortasi: listede yoksa BASA ekle ---
    if not any(isinstance(m, NaiveModel) for m in models):
        models = [NaiveModel(quantiles)] + models

    # Test dilimini GERCEK log getiriye cevir. Bundan sonra scaler yok.
    y_true = dataset.scaler.inverse(dataset.y_test)  # (N, horizon)

    rows = []
    for m in models:
        # Baseline'lar train istatistiklerine ihtiyac duyar (fit train'e bakar,
        # test'e DEGIL). Egitilmis modelde fit() no-op'tur.
        m.fit(dataset)
        pred = m.predict(dataset.X_test)  # (N, horizon, Q) -- log getiri

        _assert_monotone(pred, m.name)

        rows.append(
            evaluate_predictions(
                y_true_ret=y_true,
                pred_ret=pred,
                quantiles=tuple(m.quantiles),
                anchor_price=dataset.anchor_price_test,
                name=m.name,
            )
        )

    df = pd.DataFrame(rows)

    # --- skill score: naive'e gore ---
    naive_rmse = float(
        df.loc[df["model"] == NaiveModel.name, "rmse_ret"].iloc[0]
    )
    df["skill_score"] = [skill_score(r, naive_rmse) for r in df["rmse_ret"]]
    df["beats_naive"] = df["skill_score"] > MIN_SKILL  # > 0 DEGIL -- yukaridaki nota bak
    df.loc[df["model"] == NaiveModel.name, "beats_naive"] = False  # kendini yenemez

    for c in _COLS:
        if c not in df.columns:
            df[c] = np.nan
    df = df[_COLS].sort_values("skill_score", ascending=False).reset_index(drop=True)

    if verbose:
        print(report(df, dataset))

    return df


# ---------------------------------------------------------------- yardimci
def _assert_monotone(pred: np.ndarray, name: str) -> None:
    """
    Quantile crossing sigortasi. QuantileLSTM'de mimari geregi imkansiz,
    ama bir baseline ya da ileride eklenen bir model bunu bozarsa
    SESSIZ GECMESIN -- "guven araligi" negatif genislige duserse
    urunun risk vaadi coker.
    """
    d = np.diff(np.asarray(pred), axis=-1)
    if (d < -1e-9).any():
        n = int((d < -1e-9).sum())
        raise ValueError(f"{name}: quantile crossing tespit edildi ({n} ihlal)")


def report(df: pd.DataFrame, dataset: Dataset | None = None) -> str:
    """Insan okuyacak tablo + DURUSTLUK BOLUMU."""
    lines = []
    if dataset is not None:
        lines.append(
            f"TEST  {dataset.ticker}  n={len(dataset.X_test)}  "
            f"{dataset.dates_test[0].date()} -> {dataset.dates_test[-1].date()}"
        )
    lines.append("")

    show = df.copy()
    for c in ["rmse_ret", "mae_ret", "pinball", "width"]:
        show[c] = show[c].map(lambda v: f"{v:.6f}" if pd.notna(v) else "-")
    for c in ["coverage", "nominal_cov", "dir_acc", "skill_score"]:
        show[c] = show[c].map(lambda v: f"{v:.3f}" if pd.notna(v) else "-")
    show["rmse_price"] = show["rmse_price"].map(lambda v: f"{v:.3f}" if pd.notna(v) else "-")

    lines.append(show.to_string(index=False))
    lines.append("")

    # ---------------- durustluk bolumu ----------------
    lines.append("-" * 70)
    winners = df[(df["beats_naive"]) & (df["model"] != NaiveModel.name)]

    if winners.empty:
        best = df[df["model"] != NaiveModel.name].iloc[0] if len(df) > 1 else None
        lines.append("HICBIR MODEL NAIVE'I YENMEDI.")
        if best is not None:
            s = float(best["skill_score"])
            lines.append(
                f"  En iyi model: {best['model']}  skill_score = {s:+.4f}"
            )
            if 0 < s <= MIN_SKILL:
                # Bu satir ozellikle onemli: kucuk pozitif bir skill,
                # "az da olsa yendik" DEGILDIR. Gurultudur.
                lines.append(
                    f"  skill_score pozitif ama {MIN_SKILL:.2f} esiginin ALTINDA "
                    f"-- bu bir kazanc DEGIL, GURULTUDUR.\n"
                    f"  Test dilimini birkac gun kaydirsan isareti degisir. "
                    f"Buna 'model naive'i yendi' DENMEZ."
                )
        lines.append(
            "  Nokta tahmini bakimindan MODEL YOKTUR.\n"
            "  Bu beklenen bir sonuctur -- gunluk tek degiskenli getiri neredeyse\n"
            "  tahmin edilemez (etkin piyasa). Bunu RMSE'nin kucuk gorunmesiyle\n"
            "  ortbas ETME ve hedefi fiyat seviyesine geri CEVIRME.\n"
            "  Modelin degeri (varsa) ARALIKTA aranmali -- asagiya bak."
        )
    else:
        b = winners.iloc[0]
        lines.append(
            f"NAIVE YENILDI: {b['model']}  skill_score = {b['skill_score']:+.4f} "
            f"(esik {MIN_SKILL:.2f})"
        )
        lines.append(
            "  Kutlamadan once: bu tek bir test dilimidir. Baska ticker/donemde\n"
            "  tekrar etmiyorsa sans olabilir."
        )

    # kapsama yorumu -- risk katmani icin asil onemli olan bu
    lines.append("")
    lines.append("KAPSAMA (risk katmaninin tasiyicisi):")
    for _, r in df.iterrows():
        if pd.isna(r["coverage"]):
            continue
        gap = r["coverage"] - r["nominal_cov"]
        if r["model"] == NaiveModel.name:
            # Naive'in araligi sifir genisliktedir. Kapsamasinin 0 cikmasi
            # bir KUSUR degil, tanimidir -- "asiri kendinden emin" demek
            # ona olmayan bir iddia atfetmek olur. Naive risk KONUSMAZ.
            verdict = "dejenere -- aralik yok, risk hakkinda SESSIZ (beklenen)"
        elif abs(gap) < 0.05:
            verdict = "kalibre"
        elif gap < 0:
            verdict = "ASIRI KENDINDEN EMIN -- riski kucuk gosteriyor"
        else:
            verdict = "asiri temkinli -- aralik gereksiz genis"
        lines.append(
            f"  {r['model']:<22} {r['coverage']:.3f} "
            f"(hedef {r['nominal_cov']:.2f}, sapma {gap:+.3f})  {verdict}"
        )

    return "\n".join(lines)
