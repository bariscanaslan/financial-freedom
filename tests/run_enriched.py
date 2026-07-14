"""
Zenginlestirilmis girdi kosusu -- DURUST PROTOKOL.

PROTOKOL (ihlal edilirse butun sonuclar coop olur):
  1. Butun ozellik seti secimi ve karsilastirmasi VAL uzerinde yapilir.
  2. TEST'e SADECE EN SONDA, kazanan tek konfigurasyonla, BIR KEZ bakilir.
  3. Test sonucu kotu cikarsa geri donup baska ozellik denemeyiz --
     o an test seti kirlenmis olur. Kotu sonuc RAPOR EDILIR.

  "Istenen sonuc gelene kadar deneme" TEST uzerinde yapilirsa bilim degil,
  test setine overfit'tir. Bu dosya buna izin vermeyecek sekilde yazildi.

HEDEFLER (gercekci olanlar):
  A) Nokta tahmini: naive'i yenmek. BEKLENTI: yenemeyecegiz. Gunluk getiri
     tahmin edilemez. Bu bir basarisizlik degil, dogru cevaptir.
  B) ARALIK: EWMA'yi pinball'da ve kalibrasyonda yenmek. ASIL SINAV BU.
     Model artik oynaklik + piyasa girdisi goruyor; EWMA'nin gordugunden
     FAZLASINI goruyor. Yenemezse sinir aginin katkisi yoktur.

Calistir:
    .venv/Scripts/python.exe tests/run_enriched.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from data.loader import fetch  # noqa: E402
from model.baselines import EWMAVolModel  # noqa: E402
from model.config import ModelConfig, get_device  # noqa: E402
from model.evaluate import evaluate  # noqa: E402
from model.features import build_multi_dataset  # noqa: E402
from model.losses import pinball_loss_numpy  # noqa: E402
from model.registry import save  # noqa: E402
from model.train import seed_everything, train  # noqa: E402

TICKERS = ["AAPL", "MSFT", "NVDA", "KO"]
MARKET = "SPY"
SEQ_LEN = 30
QUANTILES = (0.1, 0.5, 0.9)

# --- denenecek ozellik setleri (hepsi VAL'de yarisacak) ---
VARIANTS: dict[str, list[str] | None] = {
    # referans: eskisi. sadece log getiri.
    "uni": ["r"],
    # oynaklik ailesi -- EWMA'nin gordugu bilginin zenginlestirilmisi
    "vol": ["r", "abs_r", "rv_5", "rv_21", "parkinson", "rv_ratio"],
    # + piyasa faktoru: tek hissenin en buyuk aciklayicisi
    "vol+mkt": ["r", "abs_r", "rv_5", "rv_21", "parkinson", "rv_ratio",
                "mkt_r", "mkt_rv_21", "rel_r"],
    # her sey (momentum ve hacim dahil)
    "all": None,
}


# ------------------------------------------------------------------ olcum
def score_on(model, ds, split: str) -> dict:
    """Bir dilimde (val/test) pinball + kapsama. Scaler burada gecmez--
    predict zaten log getiri doner."""
    X = getattr(ds, f"X_{split}")
    y = ds.scaler.inverse(getattr(ds, f"y_{split}"))
    p = model.predict(X)
    lo, med, hi = p[..., 0], p[..., 1], p[..., -1]
    return {
        "pinball": pinball_loss_numpy(p, y, QUANTILES),
        "coverage": float(np.mean((y >= lo) & (y <= hi))),
        "width": float(np.mean(hi - lo)),
        "rmse": float(np.sqrt(np.mean((y - med) ** 2))),
    }


def naive_rmse_on(ds, split: str) -> float:
    y = ds.scaler.inverse(getattr(ds, f"y_{split}"))
    return float(np.sqrt(np.mean(y**2)))  # tahmin = 0


# ------------------------------------------------------------------- main
def main() -> int:
    print("=" * 80)
    print("ZENGINLESTIRILMIS GIRDI -- secim VAL'de, TEST en sonda BIR KEZ")
    print(f"device: {get_device()}   tickers: {TICKERS}   market: {MARKET}")
    print("=" * 80)

    print("\n[veri] indiriliyor...")
    market_df = fetch(MARKET, start="2015-01-01")
    frames = {t: fetch(t, start="2015-01-01") for t in TICKERS}
    print(f"  {MARKET}: {len(market_df)} bar")
    for t, d in frames.items():
        print(f"  {t}: {len(d)} bar")

    # ================================================================
    # ASAMA 1 -- VAL uzerinde ozellik seti secimi
    # ================================================================
    print("\n" + "=" * 80)
    print("ASAMA 1: VAL uzerinde yarisma  (TEST'E DOKUNULMUYOR)")
    print("=" * 80)

    rows = []
    for vname, feats in VARIANTS.items():
        for t in TICKERS:
            ds = build_multi_dataset(
                frames[t], t, market_df=market_df,
                features=feats, seq_len=SEQ_LEN, horizon=1,
            )
            seed_everything(42)
            cfg = ModelConfig(
                seq_len=SEQ_LEN, horizon=1,
                input_dim=ds.n_features,
                feature_names=tuple(ds.feature_names),
                quantiles=QUANTILES, seed=42,
            )
            model = train(ds, cfg, verbose=False)

            lstm = score_on(model, ds, "val")
            ewma = score_on(EWMAVolModel(QUANTILES).fit(ds), ds, "val")
            nrmse = naive_rmse_on(ds, "val")

            rows.append({
                "variant": vname, "ticker": t, "F": ds.n_features,
                "val_pinball_lstm": lstm["pinball"],
                "val_pinball_ewma": ewma["pinball"],
                # EWMA'ya gore pinball iyilesmesi (%). POZITIF = LSTM daha iyi.
                "pin_gain_%": 100 * (1 - lstm["pinball"] / ewma["pinball"]),
                "val_cov_lstm": lstm["coverage"],
                "val_cov_ewma": ewma["coverage"],
                "cov_err_lstm": abs(lstm["coverage"] - 0.80),
                "cov_err_ewma": abs(ewma["coverage"] - 0.80),
                "val_skill": 1 - lstm["rmse"] / nrmse,
            })
            print(f"  {vname:8} {t:5} F={ds.n_features:2}  "
                  f"pinball {lstm['pinball']:.6f} vs EWMA {ewma['pinball']:.6f}  "
                  f"({rows[-1]['pin_gain_%']:+5.2f}%)  "
                  f"cov {lstm['coverage']:.3f} vs {ewma['coverage']:.3f}")

    val = pd.DataFrame(rows)

    print("\n--- VAL ozeti (ticker ortalamasi) ---")
    agg = val.groupby("variant").agg(
        F=("F", "first"),
        pin_gain=("pin_gain_%", "mean"),
        cov_err_lstm=("cov_err_lstm", "mean"),
        cov_err_ewma=("cov_err_ewma", "mean"),
        val_skill=("val_skill", "mean"),
    ).sort_values("pin_gain", ascending=False)
    print(agg.to_string(float_format=lambda v: f"{v:+.4f}"))

    winner = str(agg.index[0])
    print(f"\n  VAL kazanani: '{winner}'  "
          f"(EWMA'ya gore pinball {agg.loc[winner, 'pin_gain']:+.2f}%)")

    if agg.loc[winner, "pin_gain"] <= 0:
        print("\n  DIKKAT: VAL'de hicbir varyant EWMA'yi gecemedi.")
        print("  Test'e gecmenin bir anlami yok ama protokol geregi kazananla")
        print("  bir kez bakiyoruz -- ve sonucu oldugu gibi raporluyoruz.")

    # ================================================================
    # ASAMA 2 -- TEST. TEK KONFIGURASYON. TEK SEFER.
    # ================================================================
    print("\n" + "=" * 80)
    print(f"ASAMA 2: TEST -- sadece '{winner}' ile, BIR KEZ")
    print("=" * 80)

    final = []
    for t in TICKERS:
        ds = build_multi_dataset(
            frames[t], t, market_df=market_df,
            features=VARIANTS[winner], seq_len=SEQ_LEN, horizon=1,
        )
        seed_everything(42)
        cfg = ModelConfig(
            seq_len=SEQ_LEN, horizon=1,
            input_dim=ds.n_features, feature_names=tuple(ds.feature_names),
            quantiles=QUANTILES, seed=42,
        )
        model = train(ds, cfg, verbose=False)

        print(f"\n### {t}  ({winner}, F={ds.n_features})")
        table = evaluate(ds, model, verbose=True)

        lstm = table[table["model"] == "QuantileLSTM"].iloc[0]
        ewma = table[table["model"].str.startswith("EWMA")].iloc[0]

        save(model, ticker=t, metrics=lstm.to_dict(),
             train_range=(str(frames[t].index[0].date()),
                          str(frames[t].index[-1].date())),
             tag=winner.replace("+", "_"))

        final.append({
            "ticker": t,
            "skill": float(lstm["skill_score"]),
            "beats_naive": bool(lstm["beats_naive"]),
            "pin_lstm": float(lstm["pinball"]),
            "pin_ewma": float(ewma["pinball"]),
            "pin_gain_%": 100 * (1 - float(lstm["pinball"]) / float(ewma["pinball"])),
            "cov_lstm": float(lstm["coverage"]),
            "cov_ewma": float(ewma["coverage"]),
        })

    f = pd.DataFrame(final)
    f["cov_err_lstm"] = (f["cov_lstm"] - 0.80).abs()
    f["cov_err_ewma"] = (f["cov_ewma"] - 0.80).abs()

    print("\n\n" + "#" * 80)
    print(f"### NIHAI TEST SONUCU  (ozellik seti: {winner})")
    print("#" * 80)

    print("\nA) NOKTA TAHMINI -- naive yenildi mi?")
    print(f.loc[:, ["ticker", "skill", "beats_naive"]].to_string(
        index=False, float_format=lambda v: f"{v:+.4f}"))
    n_naive = int(f["beats_naive"].sum())
    print(f"   -> {n_naive}/{len(f)} ticker (esik skill > 0.01)")

    print("\nB) ARALIK -- EWMA yenildi mi?  (ASIL SINAV)")
    print(f.loc[:, ["ticker", "pin_lstm", "pin_ewma", "pin_gain_%",
                    "cov_lstm", "cov_ewma"]].to_string(
        index=False, float_format=lambda v: f"{v:.4f}"))
    n_pin = int((f["pin_gain_%"] > 0).sum())
    n_cov = int((f["cov_err_lstm"] < f["cov_err_ewma"]).sum())
    print(f"   -> pinball:     LSTM {n_pin}/{len(f)}  "
          f"(ortalama {f['pin_gain_%'].mean():+.2f}%)")
    print(f"   -> kalibrasyon: LSTM {n_cov}/{len(f)}")

    print("\n" + "#" * 80)
    print("### KARAR")
    print("#" * 80)
    if n_naive == 0:
        print("  A) Nokta tahmini: MODEL YOK. Naive yenilmedi. (Beklenen sonuc.)")
    else:
        print(f"  A) Nokta tahmini: {n_naive}/{len(f)} ticker'da naive gecildi.")

    if n_pin >= 3 and f["pin_gain_%"].mean() > 0:
        print("  B) Aralik: LSTM EWMA'yi gecti -- OLASILIKSAL KATMAN DEGER URETIYOR.")
        print("     Risk sinyali (p90-p10) artik EWMA'dan daha bilgili.")
    else:
        print("  B) Aralik: EWMA hala onde ya da fark yok.")
        print("     Sinir aginin katkisi kanitlanamadi.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
