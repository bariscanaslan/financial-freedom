"""
Conformal kalibrasyon -- holdout'ta kapsama duzeliyor mu?

DURUSTLUK BEYANI:
  Bu, holdout'a IKINCI bakisim. Bunu mesru sayiyorum cunku:
    1. Conformal'in ayarlanacak hiperparametresi YOK (alpha quantile'lardan
       gelir). Yani "iyi sonuc verene kadar denedim" durumu olusamaz.
    2. Kalibrasyon SADECE VAL dilimiyle yapilir; test hicbir asamada
       kalibrasyona girmez.
    3. Asil karar (sinir agi EWMA'yi gecmiyor) ONCEKI kosuda kilitlendi ve
       burada DEGISTIRILMIYOR. Burada olculen sey farkli bir soru:
       "aralik dogru genislikte mi?"

  Yine de kayda geciyorum: bu sayilar ilk bakis kadar temiz degildir.

Calistir:
    .venv/Scripts/python.exe tests/run_conformal.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from data.loader import fetch  # noqa: E402
from model.baselines import EWMAVolModel  # noqa: E402
from model.conformal import ConformalWrapper  # noqa: E402
from model.config import ModelConfig  # noqa: E402
from model.features import build_multi_dataset  # noqa: E402
from model.losses import pinball_loss_numpy  # noqa: E402
from model.train import train  # noqa: E402

HOLDOUT = ["AMZN", "GOOGL", "META", "JPM", "XOM", "PG", "INTC", "CSCO"]
FEATS = ["r", "abs_r", "rv_5", "rv_21", "parkinson", "rv_ratio",
         "mkt_r", "mkt_rv_21", "rel_r"]
SEQ_LEN, Q = 30, (0.1, 0.5, 0.9)
TARGET_COV = 0.80
DEVICE = "cpu"  # bkz. run_hybrid.py -- XPU coklu egitimde cokuyor


def score(model, ds) -> dict:
    p = model.predict(ds.X_test)
    y = ds.scaler.inverse(ds.y_test)
    lo, hi = p[..., 0], p[..., -1]
    return {
        "coverage": float(np.mean((y >= lo) & (y <= hi))),
        "width": float(np.mean(hi - lo)),
        "pinball": pinball_loss_numpy(p, y, Q),
    }


def main() -> int:
    print("=" * 78)
    print("CONFORMAL KALIBRASYON -- 8 holdout ticker, hedef kapsama %80")
    print("=" * 78)

    market = fetch("SPY", start="2015-01-01")
    rows = []

    for t in HOLDOUT:
        df = fetch(t, start="2015-01-01")
        ds = build_multi_dataset(df, t, market_df=market, features=FEATS,
                                 seq_len=SEQ_LEN, horizon=1)
        cfg = ModelConfig(seq_len=SEQ_LEN, horizon=1, input_dim=ds.n_features,
                          feature_names=tuple(ds.feature_names), quantiles=Q,
                          seed=42, device=DEVICE)

        lstm = train(ds, cfg, verbose=False)
        ewma = EWMAVolModel(Q).fit(ds)

        # conformal sarmalayicilar -- kalibrasyon VAL'de
        lstm_c = ConformalWrapper(lstm).fit(ds)
        ewma_c = ConformalWrapper(EWMAVolModel(Q)).fit(ds)

        for name, m in [("EWMA", ewma), ("EWMA+conf", ewma_c),
                        ("LSTM", lstm), ("LSTM+conf", lstm_c)]:
            rows.append({"ticker": t, "model": name, **score(m, ds)})

        r = {x["model"]: x for x in rows if x["ticker"] == t}
        print(f"  {t:6} kapsama:  EWMA {r['EWMA']['coverage']:.3f} -> "
              f"{r['EWMA+conf']['coverage']:.3f}   |   "
              f"LSTM {r['LSTM']['coverage']:.3f} -> {r['LSTM+conf']['coverage']:.3f}")

    d = pd.DataFrame(rows)
    agg = d.groupby("model").agg(
        coverage=("coverage", "mean"),
        width=("width", "mean"),
        pinball=("pinball", "mean"),
    )
    agg["cov_err"] = (agg["coverage"] - TARGET_COV).abs()
    agg = agg.reindex(["EWMA", "EWMA+conf", "LSTM", "LSTM+conf"])

    print("\n" + "#" * 78)
    print("### 8 TICKER ORTALAMASI")
    print("#" * 78 + "\n")
    print(agg.to_string(float_format=lambda v: f"{v:.4f}"))

    print("\n--- kapsama sapmasi (|coverage - 0.80|), ticker basina ---")
    piv = d.pivot(index="ticker", columns="model", values="coverage")
    piv = piv[["EWMA", "EWMA+conf", "LSTM", "LSTM+conf"]]
    print(piv.to_string(float_format=lambda v: f"{v:.3f}"))

    print("\n" + "#" * 78)
    print("### KARAR")
    print("#" * 78)
    for name in ["EWMA", "EWMA+conf", "LSTM", "LSTM+conf"]:
        c = agg.loc[name, "coverage"]
        e = agg.loc[name, "cov_err"]
        flag = "KALIBRE" if e < 0.03 else ("DAR (riski kucuk gosteriyor)"
                                           if c < TARGET_COV else "GENIS")
        print(f"  {name:12} kapsama {c:.3f}  sapma {e:+.3f}  -> {flag}")

    best = agg["cov_err"].idxmin()
    print(f"\n  En iyi kalibre: {best}")
    print(f"  pinball karsilastirmasi: "
          f"EWMA+conf {agg.loc['EWMA+conf','pinball']:.6f}  vs  "
          f"LSTM+conf {agg.loc['LSTM+conf','pinball']:.6f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
