"""
Smoke test -- sentetik geometrik Brownian hareket (GBM).

NEDEN GBM VE BEKLENTI NE:
  GBM'de getiriler TANIM GEREGI bagimsiz ve ayni dagilimlidir. Yani
  tahmin edilecek sinyal YOKTUR. Dolayisiyla dogru sonuc:

      skill_score  ~  0  ya da NEGATIF

  Model burada naive'i YENERSE bu iyi haber degildir -- leakage haberidir.
  Bu test "model calisiyor mu"yu degil, "olcum duzenegi durust mu"yu sinar.

  Buna karsilik OYNAKLIK acisindan bir beklentimiz VAR: GBM'e rejim
  degisimi (dusuk vol -> yuksek vol) koyuyoruz. EWMA ve LSTM'in
  KAPSAMASI ~%80'e yakin olmali; sabit gaussian rejim degisiminde
  sasirmali. Risk katmani icin asil onemli olan sinav budur.

Calistir:
    .venv/Scripts/python.exe tests/smoke_gbm.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from data.dataset import build_dataset  # noqa: E402
from model.config import ModelConfig, get_device  # noqa: E402
from model.evaluate import evaluate  # noqa: E402
from model.predict import predict  # noqa: E402
from model.registry import load, save  # noqa: E402
from model.train import seed_everything, train  # noqa: E402

OK, FAIL = "  [OK]  ", "  [FAIL]"
_failures: list[str] = []


def check(cond: bool, msg: str) -> None:
    print((OK if cond else FAIL) + " " + msg)
    if not cond:
        _failures.append(msg)


# --------------------------------------------------------------- sentetik veri
def make_gbm(
    n: int = 1500,
    p0: float = 100.0,
    mu: float = 0.08 / 252,
    sigma_lo: float = 0.010,
    sigma_hi: float = 0.030,
    seed: int = 7,
) -> pd.DataFrame:
    """
    Rejim degisimli GBM. Ilk yarisi sakin, ikinci yarisi dalgali.
    Getiri ORTALAMASI tahmin edilemez (iid), ama OYNAKLIK degisir.
    """
    rng = np.random.default_rng(seed)
    sigma = np.where(np.arange(n) < n // 2, sigma_lo, sigma_hi)

    # log getiri: r = (mu - sigma^2/2) + sigma * Z
    r = (mu - 0.5 * sigma**2) + sigma * rng.standard_normal(n)
    price = p0 * np.exp(np.cumsum(r))

    dates = pd.bdate_range("2015-01-02", periods=n, name="date")
    return pd.DataFrame(
        {
            "open": price, "high": price * 1.005, "low": price * 0.995,
            "close": price, "adj_close": price,
            "volume": rng.integers(1e6, 5e6, n).astype("float64"),
        },
        index=dates,
    )


# ----------------------------------------------------------------------- main
def main() -> int:
    print("=" * 72)
    print("SMOKE TEST -- sentetik GBM (sinyal YOK, oynaklik rejimi VAR)")
    print(f"device: {get_device()}")
    print("=" * 72)

    seed_everything(42)

    # ---------------------------------------------------------- 1) dataset
    print("\n[1] dataset")
    df = make_gbm()
    ds = build_dataset(df, ticker="GBMTEST", seq_len=30, horizon=1)
    print(ds.summary())

    check(ds.X_train.shape[1:] == (30, 1), "X sekli (N, 30, 1)")
    check(ds.y_test.shape[1] == 1, "y sekli (N, 1)")
    check(ds.scaler.fitted_on.startswith("GBMTEST:train"), "scaler SADECE train'e fit")
    check(len(ds.dates_test) == len(ds.X_test), "dates_test hizali")

    # data/ katmaninin fiyat cevirisi hala saglam mi (bagil hata ~1e-9)
    y_true_ret = ds.scaler.inverse(ds.y_test)[:, 0]
    price_rebuilt = ds.anchor_price_test * np.exp(y_true_ret)
    price_actual = df["adj_close"].reindex(ds.dates_test).values
    rel = np.abs(price_rebuilt - price_actual) / price_actual
    check(rel.max() < 1e-8, f"anchor*exp(r) -> gercek fiyat (max bagil hata {rel.max():.2e})")

    # ---------------------------------------------------------- 2) egitim
    print("\n[2] egitim")
    cfg = ModelConfig(seq_len=30, horizon=1, hidden_dim=32, num_layers=2,
                      max_epochs=60, patience=8, seed=42)
    model = train(ds, cfg)

    check(model.best_epoch > 0, f"early stopping calisti (en iyi epoch={model.best_epoch})")
    check(model.scaler is ds.scaler, "scaler modele BAGLI (ayri yasamiyor)")

    # ------------------------------------------------- 3) quantile crossing
    print("\n[3] quantile crossing")
    pred = model.predict(ds.X_test)  # (N, 1, 3) log getiri
    d = np.diff(pred, axis=-1)
    check((d > 0).all(), f"p10 < p50 < p90 -- TUM {pred.shape[0]} ornek (min fark {d.min():.2e})")

    # asiri girdide bile bozulmamali (mimari garanti, egitim degil)
    wild = np.random.default_rng(0).standard_normal((64, 30, 1)).astype(np.float32) * 50
    d_wild = np.diff(model.predict(wild), axis=-1)
    check((d_wild > 0).all(), "asiri (50 sigma) girdide de crossing YOK")

    # ---------------------------------------------------- 4) degerlendirme
    print("\n[4] degerlendirme")
    table = evaluate(ds, model, verbose=True)

    naive_row = table[table["model"] == "naive (r=0)"]
    check(len(naive_row) == 1, "naive TABLODA")

    lstm = table[table["model"] == "QuantileLSTM"].iloc[0]
    skill = float(lstm["skill_score"])

    # ASIL SINAV: GBM'de sinyal yok. Model naive'i BUYUK farkla yenerse
    # bu bir basari degil, leakage isaretidir.
    check(skill < 0.05, f"GBM'de skill_score kucuk/negatif ({skill:+.4f}) -- leakage yok")
    if skill > 0.05:
        print("      !! skill_score GBM'de anlamli pozitif. Bu IMKANSIZ olmali.")
        print("      !! Leakage suphesi: pencere/split/scaler sinirlarini kontrol et.")

    cov = float(lstm["coverage"])
    check(0.65 <= cov <= 0.92, f"LSTM kapsamasi makul ({cov:.3f}, hedef 0.80)")

    ewma_cov = float(table[table["model"].str.startswith("EWMA")].iloc[0]["coverage"])
    check(0.65 <= ewma_cov <= 0.92, f"EWMA kapsamasi makul ({ewma_cov:.3f})")

    # ---------------------------------------------------- 5) kaydet/yukle
    print("\n[5] registry (scaler modelle birlikte mi?)")
    metrics = table[table["model"] == "QuantileLSTM"].iloc[0].to_dict()
    path = save(model, ticker="GBMTEST", metrics=metrics,
                train_range=(str(df.index[0].date()), str(df.index[-1].date())),
                tag="smoke")
    print(f"      -> {path}")

    reloaded = load(path)
    check(reloaded.scaler.to_dict() == ds.scaler.to_dict(), "scaler diskten AYNEN geldi")
    check(reloaded.cfg.quantiles == cfg.quantiles, "quantiles korundu")

    p_before = model.predict(ds.X_test[:16])
    p_after = reloaded.predict(ds.X_test[:16])
    check(np.allclose(p_before, p_after, atol=1e-6),
          f"yuklenen model AYNI tahmini uretti (max fark {np.abs(p_before-p_after).max():.2e})")

    # ---------------------------------------------------- 6) predict (API)
    print("\n[6] predict() -- API'nin cagiracagi yol")
    fc = predict(path, df.tail(60), ticker="GBMTEST")
    print("      " + str(fc).replace("\n", "\n      "))

    check(fc.prices["p10"] < fc.prices["p50"] < fc.prices["p90"], "fiyat quantile'lari sirali")
    check(abs(fc.anchor_price - float(df["adj_close"].iloc[-1])) < 1e-9, "cipa = son kapanis")
    check(fc.uncertainty > 0, "belirsizlik (risk sinyali) pozitif")

    # ---------------------------------------------------------------- ozet
    print("\n" + "=" * 72)
    if _failures:
        print(f"BASARISIZ: {len(_failures)} kontrol")
        for f in _failures:
            print(f"  - {f}")
        return 1
    print("TUM KONTROLLER GECTI")
    print("=" * 72)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
