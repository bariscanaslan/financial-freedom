"""
Cok degiskenli girdi uretimi.

NEDEN VAR: tek degiskenli gunluk getiri, bir sinir agini besleyecek sinyali
TASIMIYOR -- bunu 4 ticker'da olctuk, skill_score ~ 0 cikti. Problem model
kapasitesinde degil GIRDIDE. Bu dosya girdiyi zenginlestirir.

data/dataset.py'ye DOKUNULMADI. Oradaki disiplin burada AYNEN tekrarlanir:
  1) once kronolojik SPLIT, sonra olcekleme
  2) scaler'lar SADECE train dilimine fit
  3) pencereler her dilim ICINDE ayri uretilir, sinir asilmaz
  4) hedef yine LOG GETIRI (fiyat seviyesi DEGIL)

NEDENSELLIK (en kritik nokta):
  Pencerenin son satiri t gunudur, hedef t+1 gununun getirisidir.
  Dolayisiyla t gununde bilinmeyen hicbir sey ozellik olamaz. Butun rolling
  pencereler GERIYE bakar (pandas rolling zaten boyle calisir), hicbiri
  shift(-1) icermez. Bir ozellik eklerken kendine sor:
      "Bu sayiyi t gunu piyasa kapanirken GERCEKTEN bilebilir miydim?"
  Cevap hayirsa o ozellik leakage'dir ve modeli sahte sekilde parlatir.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from data.dataset import Scaler, chronological_split, log_returns


# --------------------------------------------------------------- ozellikler
def build_features(
    df: pd.DataFrame,
    market_df: pd.DataFrame | None = None,
    price_col: str = "adj_close",
) -> pd.DataFrame:
    """
    OHLCV (+ opsiyonel piyasa endeksi) -> ozellik tablosu.

    KANAL 0 HER ZAMAN 'r' (log getiri) OLMALI. Hedef de odur; boylece
    hedefin scaler'i ile 0. kanalin scaler'i AYNI nesnedir ve EWMA gibi
    baseline'lar pencereden ham getiriyi hatasiz geri okuyabilir.
    """
    price = df[price_col].dropna()
    r = log_returns(price)

    f = pd.DataFrame(index=price.index)

    # --- 0) getirinin kendisi (hedefin gecmisi) ---
    f["r"] = r

    # --- oynaklik ailesi: modelin ARALIGI daraltip genisletmesi icin ---
    # EWMA'nin gordugu bilgi bu; LSTM'e de verelim ki adil bir yaris olsun.
    f["abs_r"] = r.abs()
    f["rv_5"] = r.rolling(5).std()
    f["rv_21"] = r.rolling(21).std()
    # Parkinson: gun ici menzil. Kapanis-kapanis oynakligindan daha
    # verimli bir tahmin edici -- gun icinde olan biteni de gorur.
    f["parkinson"] = np.log(df["high"] / df["low"]).reindex(price.index)
    # oynaklik rejimi: kisa vade / uzun vade. >1 ise vol yukseliyor.
    f["rv_ratio"] = f["rv_5"] / f["rv_21"]

    # --- momentum / trend ---
    f["mom_5"] = r.rolling(5).sum()
    f["mom_21"] = r.rolling(21).sum()

    # --- hacim ---
    vol = df["volume"].reindex(price.index).replace(0, np.nan)
    f["vol_z"] = np.log(vol / vol.rolling(21).mean())

    # --- piyasa faktoru (sistematik risk) ---
    # Tek bir hissenin getirisinin en buyuk aciklayicisi PIYASADIR.
    # Tek degiskenli modelin goremedigi sey tam olarak buydu.
    if market_df is not None:
        m = market_df[price_col].dropna()
        rm = log_returns(m).reindex(price.index)
        f["mkt_r"] = rm
        f["mkt_rv_21"] = rm.rolling(21).std()
        # goreli guc: hisse piyasadan daha mi iyi gidiyor
        f["rel_r"] = f["r"] - rm

    return f.replace([np.inf, -np.inf], np.nan).dropna()


# ------------------------------------------------------------------ dataset
@dataclass
class MultiDataset:
    """
    data.dataset.Dataset ile AYNI alan isimlerine sahiptir -- bu sayede
    train/evaluate/metrics hicbir degisiklik olmadan calisir.

    Tek fark: X'in son ekseni 1 degil F (ozellik sayisi).
    """

    ticker: str
    seq_len: int
    horizon: int

    X_train: np.ndarray
    y_train: np.ndarray
    X_val: np.ndarray
    y_val: np.ndarray
    X_test: np.ndarray
    y_test: np.ndarray

    scaler: Scaler                 # HEDEFIN scaler'i (= 0. kanalinki)
    dates_test: pd.DatetimeIndex
    anchor_price_test: np.ndarray

    feature_names: list[str]
    feature_scalers: list[Scaler]
    return_channel: int = 0        # baseline'lar ham getiriyi buradan okur

    @property
    def n_features(self) -> int:
        return len(self.feature_names)

    def summary(self) -> str:
        return (
            f"{self.ticker}  seq={self.seq_len} h={self.horizon} F={self.n_features}\n"
            f"  ozellikler: {', '.join(self.feature_names)}\n"
            f"  train {self.X_train.shape}  val {self.X_val.shape}  test {self.X_test.shape}\n"
            f"  hedef scaler mean={self.scaler.mean:+.6f} std={self.scaler.std:.6f} "
            f"(fit: {self.scaler.fitted_on})"
        )


def _windows(
    F: np.ndarray,        # (T, n_features) olceklenmis
    y: np.ndarray,        # (T,) olceklenmis hedef (= F[:, 0])
    seq_len: int,
    horizon: int,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """
    X[i] = F[i : i+seq_len]                  -- t-seq_len+1 .. t gunleri
    y[i] = y[i+seq_len : i+seq_len+horizon]  -- t+1 .. gunleri

    X ve y ORTUSMEZ. Pencerenin son gunu t, hedefin ilk gunu t+1.
    Doner: (X, Y, idx) -- idx[i] = hedefin ilk gununun konumu.
    """
    xs, ys, idx = [], [], []
    limit = len(F) - seq_len - horizon + 1
    for i in range(limit):
        xs.append(F[i : i + seq_len])
        ys.append(y[i + seq_len : i + seq_len + horizon])
        idx.append(i + seq_len)

    if not xs:
        raise ValueError(f"pencere uretilemedi: T={len(F)}, seq_len={seq_len}")

    return (
        np.asarray(xs, dtype=np.float32),
        np.asarray(ys, dtype=np.float32),
        np.asarray(idx, dtype=np.int64),
    )


def build_multi_dataset(
    df: pd.DataFrame,
    ticker: str,
    *,
    market_df: pd.DataFrame | None = None,
    features: list[str] | None = None,
    seq_len: int = 30,
    horizon: int = 1,
    price_col: str = "adj_close",
    train_frac: float = 0.70,
    val_frac: float = 0.15,
) -> MultiDataset:
    """
    Cok degiskenli, leakage'siz dataset.

    Args:
        features: None ise build_features'in urettigi HER SEY kullanilir.
                  Liste verilirse sirasi korunur; 'r' HER ZAMAN basa alinir.
    """
    feat = build_features(df, market_df=market_df, price_col=price_col)

    if features is not None:
        missing = [c for c in features if c not in feat.columns]
        if missing:
            raise ValueError(f"bilinmeyen ozellik: {missing}")
        cols = ["r"] + [c for c in features if c != "r"]
        feat = feat[cols]

    names = list(feat.columns)
    if names[0] != "r":
        raise ValueError("0. kanal 'r' olmali (hedef scaler'i onunkiyle paylasilir)")

    if len(feat) < seq_len + horizon + 50:
        raise ValueError(f"{ticker}: yetersiz veri ({len(feat)} satir)")

    # ---- 1) once SPLIT ----
    s_tr, s_va, s_te = chronological_split(len(feat), train_frac, val_frac)
    tr, va, te = feat.iloc[s_tr], feat.iloc[s_va], feat.iloc[s_te]

    # ---- 2) scaler'lar SADECE train'e fit ----
    tag = f"{ticker}:train[{tr.index[0].date()}..{tr.index[-1].date()}]"
    scalers = [Scaler.fit(tr[c].values, name=f"{tag}:{c}") for c in names]

    def _scale(block: pd.DataFrame) -> np.ndarray:
        return np.column_stack(
            [sc.transform(block[c].values) for sc, c in zip(scalers, names)]
        )

    Z_tr, Z_va, Z_te = _scale(tr), _scale(va), _scale(te)

    # ---- 3) pencereler her dilim ICINDE ----
    # hedef = 0. kanal (r), dolayisiyla hedefin scaler'i scalers[0]'dir.
    X_tr, y_tr, _ = _windows(Z_tr, Z_tr[:, 0], seq_len, horizon)
    X_va, y_va, _ = _windows(Z_va, Z_va[:, 0], seq_len, horizon)
    X_te, y_te, idx_te = _windows(Z_te, Z_te[:, 0], seq_len, horizon)

    # ---- 4) test icin tarih + cipa fiyati ----
    dates_te = te.index[idx_te]                       # hedef gunleri

    price = df[price_col].dropna()
    pos = price.index.get_indexer(dates_te)
    if (pos < 1).any():
        raise ValueError(f"{ticker}: cipa fiyati bulunamadi")
    # cipa = hedef gununden BIR ONCEKI kapanis  =>  P_t = cipa * exp(r_t)
    anchor_te = price.values[pos - 1].astype(np.float64)

    return MultiDataset(
        ticker=ticker,
        seq_len=seq_len,
        horizon=horizon,
        X_train=X_tr, y_train=y_tr,
        X_val=X_va, y_val=y_va,
        X_test=X_te, y_test=y_te,
        scaler=scalers[0],                 # hedefin scaler'i
        dates_test=pd.DatetimeIndex(dates_te),
        anchor_price_test=anchor_te,
        feature_names=names,
        feature_scalers=scalers,
        return_channel=0,
    )
