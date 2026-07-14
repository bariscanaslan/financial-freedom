"""
Model-hazir veri seti uretimi.

BURASI KRITIK KATMAN. Notebook'taki 3 hatanin da coozuldugu yer:

  1. LEAKAGE: scaler SADECE train dilimine fit edilir. Split once,
     olcekleme sonra. Scaler dataset ile birlikte kaydedilir.

  2. HEDEF: fiyat SEVIYESI degil, LOG GETIRI tahmin edilir.
     Seviye tahmininde model "dunku fiyati kopyala" cozumunu bulur,
     RMSE mukemmel gorunur, bilgi degeri sifirdir.

  3. BASELINE: naive tahmin (getiri = 0, yani fiyat degismedi) her zaman
     birlikte hesaplanir. Model bunu yenemiyorsa model yoktur.

Ayrica: kronolojik split (shuffle YOK) ve train/val/test ucluu.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


# ------------------------------------------------------------------ scaler
@dataclass
class Scaler:
    """
    Basit standart olcekleyici. sklearn yerine kendi sinifimiz:
    save/load'u ve neye fit edildigini seffaf tutmak icin.
    """
    mean: float
    std: float
    fitted_on: str  # ne uzerinde fit edildigi -- denetlenebilirlik icin

    @classmethod
    def fit(cls, x: np.ndarray, name: str = "train") -> "Scaler":
        x = np.asarray(x, dtype=np.float64)
        std = float(x.std())
        if std < 1e-12:
            raise ValueError("std ~ 0, olceklenemez")
        return cls(mean=float(x.mean()), std=std, fitted_on=name)

    def transform(self, x):
        return (np.asarray(x, dtype=np.float64) - self.mean) / self.std

    def inverse(self, x):
        return np.asarray(x, dtype=np.float64) * self.std + self.mean

    def to_dict(self):
        return {"mean": self.mean, "std": self.std, "fitted_on": self.fitted_on}

    @classmethod
    def from_dict(cls, d):
        return cls(**d)


# ----------------------------------------------------------------- targets
def log_returns(price: pd.Series) -> pd.Series:
    """
    r_t = ln(P_t / P_{t-1})

    Neden log: toplanabilir (r_1..r_n toplami = toplam log getiri),
    yaklasik olarak stasyoner, ve simetrik (+%10 / -%10 buyuklukce esit).
    """
    return np.log(price / price.shift(1))


# ------------------------------------------------------------------ splits
def chronological_split(
    n: int,
    train: float = 0.70,
    val: float = 0.15,
) -> tuple[slice, slice, slice]:
    """
    Kronolojik ucluu split. Shuffle YOK -- zaman serisinde karistirmak
    gelecegi gecmise sizdirir.
    """
    i_tr = int(n * train)
    i_va = int(n * (train + val))
    return slice(0, i_tr), slice(i_tr, i_va), slice(i_va, n)


# ----------------------------------------------------------------- windows
def make_windows(
    series: np.ndarray,
    seq_len: int,
    horizon: int = 1,
) -> tuple[np.ndarray, np.ndarray]:
    """
    Kayan pencere. X[i] = series[i : i+seq_len]
                   y[i] = series[i+seq_len : i+seq_len+horizon]

    X ve y ARASINDA HIC ORTUSME YOK. y tamamen X'in sonrasindadir.
    """
    x_list, y_list = [], []
    limit = len(series) - seq_len - horizon + 1
    for i in range(limit):
        x_list.append(series[i : i + seq_len])
        y_list.append(series[i + seq_len : i + seq_len + horizon])

    if not x_list:
        raise ValueError(
            f"pencere uretilemedi: len={len(series)}, seq_len={seq_len}, horizon={horizon}"
        )

    X = np.asarray(x_list, dtype=np.float32)[..., None]  # (N, seq_len, 1)
    y = np.asarray(y_list, dtype=np.float32)             # (N, horizon)
    return X, y


# ----------------------------------------------------------------- dataset
@dataclass
class Dataset:
    ticker: str
    seq_len: int
    horizon: int

    X_train: np.ndarray
    y_train: np.ndarray
    X_val: np.ndarray
    y_val: np.ndarray
    X_test: np.ndarray
    y_test: np.ndarray

    scaler: Scaler
    # Ters cevirme icin: her ornegin hedef tarihi ve o andaki son fiyat
    dates_test: pd.DatetimeIndex
    anchor_price_test: np.ndarray   # y'nin hemen oncesindeki kapanis fiyati

    def summary(self) -> str:
        return (
            f"{self.ticker}  seq={self.seq_len} h={self.horizon}\n"
            f"  train {self.X_train.shape}  val {self.X_val.shape}  test {self.X_test.shape}\n"
            f"  scaler mean={self.scaler.mean:+.6f} std={self.scaler.std:.6f} "
            f"(fit: {self.scaler.fitted_on})"
        )


def build_dataset(
    df: pd.DataFrame,
    ticker: str,
    *,
    seq_len: int = 30,
    horizon: int = 1,
    price_col: str = "adj_close",
    train_frac: float = 0.70,
    val_frac: float = 0.15,
) -> Dataset:
    """
    OHLCV -> model-hazir tensorler.

    Adim sirasi ONEMLI:
      1) log getiri hesapla
      2) kronolojik BOL
      3) scaler'i SADECE train'e fit et
      4) uc dilimi de ayni scaler ile transform et
      5) pencereleri her dilim icinde AYRI olustur
         (dilim sinirini asan pencere = leakage)
    """
    price = df[price_col].dropna()
    r = log_returns(price).dropna()

    if len(r) < seq_len + horizon + 50:
        raise ValueError(f"{ticker}: yetersiz veri ({len(r)} getiri)")

    s_tr, s_va, s_te = chronological_split(len(r), train_frac, val_frac)

    r_tr, r_va, r_te = r.iloc[s_tr], r.iloc[s_va], r.iloc[s_te]

    # 3) SADECE train'e fit -- leakage yok
    scaler = Scaler.fit(r_tr.values, name=f"{ticker}:train[{r_tr.index[0].date()}"
                                          f"..{r_tr.index[-1].date()}]")

    z_tr = scaler.transform(r_tr.values)
    z_va = scaler.transform(r_va.values)
    z_te = scaler.transform(r_te.values)

    X_tr, y_tr = make_windows(z_tr, seq_len, horizon)
    X_va, y_va = make_windows(z_va, seq_len, horizon)
    X_te, y_te = make_windows(z_te, seq_len, horizon)

    # --- Test setini gercek FIYATA cevirebilmek icin cipa fiyatlari ---
    # y_te[i][0], r_te[seq_len + i] getirisidir.
    # O getirinin tarihi:
    n_te = len(X_te)
    dates_te = r_te.index[seq_len : seq_len + n_te]

    # r_t = ln(P_t / P_{t-1})  =>  P_t = P_{t-1} * exp(r_t)
    # Yani cipa = hedef gununden BIR ONCEKI islem gunun kapanisi.
    # price uzerinde konumsal olarak bir geri git (reindex+shift degil --
    # reindex NaN uretir cunku onceki gun dates_te icinde olmayabilir).
    pos = price.index.get_indexer(dates_te)
    if (pos < 1).any():
        raise ValueError(f"{ticker}: cipa fiyati bulunamadi")
    anchor_te = price.values[pos - 1].astype(np.float64)

    return Dataset(
        ticker=ticker,
        seq_len=seq_len,
        horizon=horizon,
        X_train=X_tr, y_train=y_tr,
        X_val=X_va, y_val=y_va,
        X_test=X_te, y_test=y_te,
        scaler=scaler,
        dates_test=pd.DatetimeIndex(dates_te),
        anchor_price_test=anchor_te,
    )


# ---------------------------------------------------------------- baseline
def naive_baseline(y_true_scaled: np.ndarray, scaler: Scaler) -> dict:
    """
    Naive tahmin: "yarin getiri = 0" (fiyat degismez / random walk).

    Bu, gecilmesi gereken cizgidir. Bir modelin RMSE'si bunun altinda
    degilse o model ise yaramaz -- ne kadar dusuk gorunurse gorunsun.
    """
    y_true = scaler.inverse(y_true_scaled)          # gercek log getiriler
    y_pred = np.zeros_like(y_true)                  # getiri = 0

    rmse = float(np.sqrt(np.mean((y_true - y_pred) ** 2)))
    mae = float(np.mean(np.abs(y_true - y_pred)))
    # Yon dogrulugu: naive'in yonu yok, referans olarak %50 kabul edilir
    return {
        "name": "naive (r=0)",
        "rmse_logret": rmse,
        "mae_logret": mae,
        "directional_accuracy": 0.5,
    }
