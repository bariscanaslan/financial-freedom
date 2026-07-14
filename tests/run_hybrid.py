"""
Hibrit model kosusu -- TEMIZ HOLDOUT PROTOKOLU.

NEDEN YENI TICKER'LAR:
  AAPL/MSFT/NVDA/KO'nun TEST dilimine bir kez baktik (run_enriched).
  Ayni test setine tekrar bakip mimari secersek o sayilar KIRLENIR --
  raporladigimiz skor artik modelin degil, bizim kac kez baktigimizin
  fonksiyonu olur.

  Bu yuzden:
    GELISTIRME  : 4 dev ticker'in VAL dilimi (test'e dokunulmaz)
    NIHAI KARAR : 8 YENI ticker -- hicbir asamada gorulmediler

  Yeni ticker'lar ayrica daha zor bir sinav: model sadece yeni bir ZAMAN
  dilimine degil, yeni bir HISSEYE genellemek zorunda.

ADAYLAR:
  ewma          : klasik taban (yenilmesi gereken)
  lstm-uni      : sadece log getiri
  lstm-vol+mkt  : 9 ozellik (zenginlestirme)
  hybrid-uni    : EWMA cipali, tek degiskenli
  hybrid-vol+mkt: EWMA cipali + 9 ozellik

Calistir:
    .venv/Scripts/python.exe tests/run_hybrid.py
"""
from __future__ import annotations

import math
import sys
from pathlib import Path
from statistics import NormalDist

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from data.loader import fetch  # noqa: E402
from model.baselines import EWMAVolModel  # noqa: E402
from model.config import ModelConfig, get_device  # noqa: E402
from model.features import build_multi_dataset  # noqa: E402
from model.hybrid import HybridEWMALSTM  # noqa: E402
from model.train import train  # noqa: E402

DEV = ["AAPL", "MSFT", "NVDA", "KO"]
# Bunlar SADECE en sonda kullanilacak. Simdiye kadar hic gorulmediler.
HOLDOUT = ["AMZN", "GOOGL", "META", "JPM", "XOM", "PG", "INTC", "CSCO"]
MARKET = "SPY"
SEQ_LEN, Q = 30, (0.1, 0.5, 0.9)

FEATS = {
    "uni": ["r"],
    "vol+mkt": ["r", "abs_r", "rv_5", "rv_21", "parkinson", "rv_ratio",
                "mkt_r", "mkt_rv_21", "rel_r"],
}


# CPU, XPU degil. Bu bir performans tercihi DEGIL, zorunluluk:
# torch 2.13.0+xpu, ard arda ~20 model yaratilip egitildiginde
# UR_RESULT_ERROR_OUT_OF_RESOURCES ile cokuyor (empty_cache yetmiyor --
# surec basina sizan bir kaynak var). Bu supurme 5 aday x 12 ticker = 60
# egitim yapiyor. Modeller kucuk (~50k parametre), CPU rahat kaldiriyor.
# XPU tek model egitiminde sorunsuz calisiyor (bkz. tests/run_real.py).
DEVICE = "cpu"


def make_cfg(ds) -> ModelConfig:
    return ModelConfig(
        seq_len=SEQ_LEN, horizon=1, input_dim=ds.n_features,
        feature_names=tuple(ds.feature_names), quantiles=Q, seed=42,
        device=DEVICE,
    )


def pinball_per_sample(pred: np.ndarray, y: np.ndarray) -> np.ndarray:
    """(N,) -- ornek basina pinball. Esli test icin gerekli."""
    q = np.array(Q)
    err = y[..., None] - pred
    return np.maximum(q * err, (q - 1) * err).mean(axis=(1, 2))


def fit_candidate(kind: str, feat: str, ds):
    cfg = make_cfg(ds)
    if kind == "lstm":
        return train(ds, cfg, verbose=False)
    if kind == "hybrid":
        return HybridEWMALSTM(cfg).fit(ds)
    if kind == "ewma":
        return EWMAVolModel(Q).fit(ds)
    raise ValueError(kind)


CANDIDATES = [
    ("ewma", "uni"),
    ("lstm", "uni"),
    ("lstm", "vol+mkt"),
    ("hybrid", "uni"),
    ("hybrid", "vol+mkt"),
]


def eval_split(model, ds, split: str) -> tuple[np.ndarray, np.ndarray]:
    X = getattr(ds, f"X_{split}")
    y = ds.scaler.inverse(getattr(ds, f"y_{split}"))
    return model.predict(X), y


def summarize(pred, y) -> dict:
    lo, med, hi = pred[..., 0], pred[..., 1], pred[..., -1]
    return {
        "pinball": float(pinball_per_sample(pred, y).mean()),
        "coverage": float(np.mean((y >= lo) & (y <= hi))),
        "width": float(np.mean(hi - lo)),
        "rmse": float(np.sqrt(np.mean((y - med) ** 2))),
        "naive_rmse": float(np.sqrt(np.mean(y**2))),
    }


def main() -> int:
    print("=" * 84)
    print("HIBRIT KOSU -- gelistirme DEV/VAL'de, karar HIC GORULMEMIS 8 ticker'da")
    print(f"device: {get_device()}")
    print("=" * 84)

    print("\n[veri] indiriliyor...")
    market = fetch(MARKET, start="2015-01-01")
    frames = {t: fetch(t, start="2015-01-01") for t in DEV + HOLDOUT}
    print(f"  {len(frames)} ticker + {MARKET}")

    datasets: dict[tuple[str, str], object] = {}

    def get_ds(t: str, feat: str):
        key = (t, feat)
        if key not in datasets:
            datasets[key] = build_multi_dataset(
                frames[t], t, market_df=market,
                features=FEATS[feat], seq_len=SEQ_LEN, horizon=1,
            )
        return datasets[key]

    # =============================================================
    # ASAMA 1 -- DEV tickerlarin VAL dilimi. TEST'E BAKILMIYOR.
    # =============================================================
    print("\n" + "=" * 84)
    print("ASAMA 1: aday secimi -- DEV tickerlarin VAL dilimi")
    print("=" * 84)

    rows = []
    for kind, feat in CANDIDATES:
        name = f"{kind}-{feat}"
        for t in DEV:
            ds = get_ds(t, feat)
            m = fit_candidate(kind, feat, ds)
            s = summarize(*eval_split(m, ds, "val"))
            rows.append({"cand": name, "ticker": t, **s})
        sub = [r for r in rows if r["cand"] == name]
        print(f"  {name:16} val_pinball={np.mean([r['pinball'] for r in sub]):.6f}  "
              f"cov={np.mean([r['coverage'] for r in sub]):.3f}")

    val = pd.DataFrame(rows)
    BASE = "ewma-uni"  # aday isimleri "<kind>-<feat>" formatinda
    base = val[val["cand"] == BASE].set_index("ticker")["pinball"]
    val["gain_%"] = [
        100 * (1 - r["pinball"] / base[r["ticker"]]) for _, r in val.iterrows()
    ]

    agg = val.groupby("cand").agg(
        pinball=("pinball", "mean"),
        gain=("gain_%", "mean"),
        coverage=("coverage", "mean"),
    )
    agg["cov_err"] = (agg["coverage"] - 0.80).abs()
    agg = agg.sort_values("gain", ascending=False)

    print("\n--- VAL ozeti (EWMA'ya gore pinball kazanci) ---")
    print(agg.to_string(float_format=lambda v: f"{v:+.4f}"))

    winner = str(agg.index[0])
    if winner == BASE:
        print("\n  VAL kazanani EWMA. Sinir agi hicbir varyantta gecemedi.")
        print("  Yine de protokol geregi en iyi AG adayini holdout'ta test edecegiz.")
        winner = str(agg.drop(BASE).index[0])
    print(f"\n  Holdout'a goturulen aday: '{winner}'")

    w_kind, w_feat = winner.split("-", 1)

    # =============================================================
    # ASAMA 2 -- HOLDOUT. YENI TICKERLAR. TEK SEFER.
    # =============================================================
    print("\n" + "=" * 84)
    print(f"ASAMA 2: HOLDOUT -- '{winner}' vs EWMA, 8 YENI ticker, TEST dilimi")
    print("=" * 84)

    final, pooled_d = [], []
    for t in HOLDOUT:
        ds = build_multi_dataset(
            frames[t], t, market_df=market,
            features=FEATS[w_feat], seq_len=SEQ_LEN, horizon=1,
        )
        mdl = fit_candidate(w_kind, w_feat, ds)
        ewm = EWMAVolModel(Q).fit(ds)

        p_m, y = eval_split(mdl, ds, "test")
        p_e, _ = eval_split(ewm, ds, "test")

        s_m, s_e = summarize(p_m, y), summarize(p_e, y)

        # esli fark: ornek basina pinball. Gurultu mu, gercek mi?
        d = pinball_per_sample(p_m, y) - pinball_per_sample(p_e, y)
        pooled_d.append(d)
        tstat = d.mean() / (d.std(ddof=1) / math.sqrt(len(d)))
        pval = 2 * (1 - NormalDist().cdf(abs(tstat)))

        final.append({
            "ticker": t, "n": len(y),
            "pin_model": s_m["pinball"], "pin_ewma": s_e["pinball"],
            "gain_%": 100 * (1 - s_m["pinball"] / s_e["pinball"]),
            "p": pval,
            "cov_model": s_m["coverage"], "cov_ewma": s_e["coverage"],
            "skill": 1 - s_m["rmse"] / s_m["naive_rmse"],
        })
        print(f"  {t:6} n={len(y):4}  pinball {s_m['pinball']:.6f} vs "
              f"{s_e['pinball']:.6f}  ({final[-1]['gain_%']:+5.2f}%, p={pval:.3f})  "
              f"cov {s_m['coverage']:.3f} vs {s_e['coverage']:.3f}")

    f = pd.DataFrame(final)

    print("\n" + "#" * 84)
    print(f"### HOLDOUT SONUCU  --  {winner}  vs  EWMA   (8 gorulmemis ticker)")
    print("#" * 84)
    print("\n" + f[["ticker", "n", "pin_model", "pin_ewma", "gain_%", "p",
                    "cov_model", "cov_ewma", "skill"]]
          .to_string(index=False, float_format=lambda v: f"{v:.4f}"))

    # --- havuzlanmis esli test: butun ornekler bir arada ---
    D = np.concatenate(pooled_d)
    t_all = D.mean() / (D.std(ddof=1) / math.sqrt(len(D)))
    p_all = 2 * (1 - NormalDist().cdf(abs(t_all)))
    n_win = int((f["gain_%"] > 0).sum())
    n_sig = int(((f["gain_%"] > 0) & (f["p"] < 0.05)).sum())

    print("\n--- OZET ---")
    print(f"  pinball kazanci (ortalama)      : {f['gain_%'].mean():+.2f}%")
    print(f"  EWMA'yi gectigi ticker sayisi   : {n_win}/8  "
          f"(istatistiksel anlamli: {n_sig}/8)")
    print(f"  havuzlanmis esli test (n={len(D)}) : t={t_all:+.2f}  p={p_all:.4f}")
    print(f"  kapsama  model {f['cov_model'].mean():.3f}  |  "
          f"EWMA {f['cov_ewma'].mean():.3f}  |  hedef 0.800")
    print(f"  naive skill_score (ortalama)    : {f['skill'].mean():+.4f}")

    print("\n" + "#" * 84)
    print("### KARAR")
    print("#" * 84)

    mean_gain = f["gain_%"].mean()
    if p_all < 0.05 and mean_gain > 0 and n_win >= 6:
        print(f"  {winner} EWMA'yi HOLDOUT'ta ANLAMLI olcude gecti.")
        print(f"  ortalama {mean_gain:+.2f}% pinball, p={p_all:.4f}, {n_win}/8 ticker.")
        print("  Olasiliksal katman deger uretiyor: risk sinyali EWMA'dan bilgili.")
    elif mean_gain > 0 and p_all >= 0.05:
        print(f"  {winner} ortalamada onde ({mean_gain:+.2f}%) ama fark ANLAMLI DEGIL "
              f"(p={p_all:.4f}).")
        print("  Bu bir kazanc DEGIL. Gurultuyle ayirt edilemiyor.")
    else:
        print(f"  {winner} EWMA'yi GECEMEDI ({mean_gain:+.2f}%, p={p_all:.4f}).")
        print("  Sinir aginin katkisi kanitlanamadi.")

    # kapsama yorumu -- yon onemli
    cm = f["cov_model"].mean()
    if cm < 0.75:
        print(f"\n  UYARI: model kapsamasi {cm:.3f} < 0.80. Aralik DAR --")
        print("  yani riski OLDUGUNDAN KUCUK gosteriyor. Bu, genis araliktan")
        print("  daha tehlikelidir: kullanici korunmadigi bir yerde korundugunu sanir.")

    print("\n  NOT: naive skill_score ortalamasi "
          f"{f['skill'].mean():+.4f} -- nokta tahmini bakimindan hala MODEL YOK.")
    print("  Bu degismedi ve degismesini beklemiyorduk.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
