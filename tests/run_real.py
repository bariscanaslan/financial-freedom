"""
Gercek veri kosusu: yfinance -> validate -> build_dataset -> train -> evaluate

BEKLENTI (bastan yaziyorum ki sonuca gore hikaye uydurmayalim):
  skill_score muhtemelen <= 0 cikacak. Gunluk tek degiskenli getiri
  neredeyse tahmin edilemez. Cikarsa da MIN_SKILL (0.01) esigini gecmesi
  gerekir; kucuk pozitif degerler gurultudur.

  ASIL SORU nokta tahmini degil: LSTM'in ARALIGI, EWMA'nin araligindan
  daha bilgili mi? Bunu pinball + coverage ile olcuyoruz.

Calistir:
    .venv/Scripts/python.exe tests/run_real.py [TICKER ...]
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from data.dataset import build_dataset  # noqa: E402
from data.loader import fetch  # noqa: E402
from data.validate import validate  # noqa: E402
from model.config import ModelConfig, get_device  # noqa: E402
from model.evaluate import evaluate  # noqa: E402
from model.registry import save  # noqa: E402
from model.train import seed_everything, train  # noqa: E402

TICKERS = sys.argv[1:] or ["AAPL", "MSFT", "NVDA", "KO"]
SEQ_LEN = 30
HORIZON = 1


def run_one(ticker: str) -> dict | None:
    print("\n" + "=" * 78)
    print(f"### {ticker}")
    print("=" * 78)

    df = fetch(ticker, start="2015-01-01")
    rep = validate(df, ticker)
    print(rep)
    if not rep.ok:
        print(f"  {ticker}: dogrulama BASARISIZ -- atlaniyor")
        return None

    ds = build_dataset(df, ticker, seq_len=SEQ_LEN, horizon=HORIZON)
    print(ds.summary())

    seed_everything(42)
    cfg = ModelConfig(seq_len=SEQ_LEN, horizon=HORIZON, seed=42)
    model = train(ds, cfg, verbose=True)

    table = evaluate(ds, model, verbose=True)

    lstm = table[table["model"] == "QuantileLSTM"].iloc[0]
    ewma = table[table["model"].str.startswith("EWMA")].iloc[0]

    path = save(
        model, ticker=ticker,
        metrics=lstm.to_dict(),
        train_range=(str(df.index[0].date()), str(df.index[-1].date())),
    )
    print(f"\n  kaydedildi -> {path.name}")

    return {
        "ticker": ticker,
        "n_test": len(ds.X_test),
        "skill_lstm": float(lstm["skill_score"]),
        "beats_naive": bool(lstm["beats_naive"]),
        "pinball_lstm": float(lstm["pinball"]),
        "pinball_ewma": float(ewma["pinball"]),
        "cov_lstm": float(lstm["coverage"]),
        "cov_ewma": float(ewma["coverage"]),
        "width_lstm": float(lstm["width"]),
        "width_ewma": float(ewma["width"]),
        "dir_acc_lstm": float(lstm["dir_acc"]),
    }


def main() -> int:
    print(f"device: {get_device()}   tickers: {TICKERS}")
    rows = [r for t in TICKERS if (r := run_one(t)) is not None]
    if not rows:
        print("hicbir ticker islenemedi")
        return 1

    s = pd.DataFrame(rows)
    s["pinball_kazanan"] = [
        "LSTM" if a < b else "EWMA" for a, b in zip(s["pinball_lstm"], s["pinball_ewma"])
    ]
    s["cov_hata_lstm"] = (s["cov_lstm"] - 0.80).abs()
    s["cov_hata_ewma"] = (s["cov_ewma"] - 0.80).abs()
    s["kalibrasyon_kazanan"] = [
        "LSTM" if a < b else "EWMA" for a, b in zip(s["cov_hata_lstm"], s["cov_hata_ewma"])
    ]

    print("\n\n" + "#" * 78)
    print("### TOPLU OZET")
    print("#" * 78 + "\n")

    print("1) NOKTA TAHMINI -- naive'i yendi mi?")
    print(s[["ticker", "n_test", "skill_lstm", "beats_naive", "dir_acc_lstm"]]
          .to_string(index=False, float_format=lambda v: f"{v:+.4f}"))

    n_win = int(s["beats_naive"].sum())
    print(f"\n   {n_win}/{len(s)} ticker'da LSTM naive'i ANLAMLI olcude yendi "
          f"(esik: skill > 0.01)")

    print("\n2) ARALIK -- LSTM, EWMA'dan daha bilgili mi?")
    print(s[["ticker", "pinball_lstm", "pinball_ewma", "pinball_kazanan",
             "cov_lstm", "cov_ewma", "kalibrasyon_kazanan"]]
          .to_string(index=False, float_format=lambda v: f"{v:.4f}"))

    p_win = int((s["pinball_kazanan"] == "LSTM").sum())
    c_win = int((s["kalibrasyon_kazanan"] == "LSTM").sum())
    print(f"\n   pinball:      LSTM {p_win}/{len(s)}")
    print(f"   kalibrasyon:  LSTM {c_win}/{len(s)}  (|coverage - 0.80| kucuk olan)")

    print("\n" + "#" * 78)
    print("### KARAR")
    print("#" * 78)
    if n_win == 0:
        print("  LSTM hicbir ticker'da naive'i yenemedi. NOKTA TAHMINI OLARAK MODEL YOKTUR.")
    else:
        print(f"  LSTM {n_win}/{len(s)} ticker'da naive'i gecti -- tekrarlanabilirligi sorgula.")

    if p_win > len(s) / 2:
        print("  Ama ARALIK tarafinda LSTM EWMA'yi gecti: olasiliksal katman deger uretiyor.")
    else:
        print("  ARALIK tarafinda da EWMA onde. Sinir aginin su anki katkisi YOK;")
        print("  ayni riski 3 satirlik EWMA ile bedavaya alabilirsin.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
