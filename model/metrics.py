"""
Metrikler.

TEK KURAL: buraya giren her sey LOG GETIRI uzayindadir. Scaler bu dosyada
gecmez, gecmemeli. Olcekli/olceksiz karisikligi predict() sinirinda coozuldu.

Metrik gruplari:
  getiri uzayi : rmse, mae, pinball, coverage, ortalama aralik genisligi
  fiyat uzayi  : rmse  (anchor * exp(r) ile geri cevirerek)
  yon          : directional_accuracy
  kiyas        : skill_score = 1 - rmse_model / rmse_naive

SKILL SCORE'U OKUMA KILAVUZU:
    > 0   model naive'i YENDI     (ne kadar buyukse o kadar iyi, 1 = mukemmel)
    = 0   model naive ile AYNI    (yani model yok)
    < 0   model naive'den KOTU    (yani model zararli)

RMSE'nin kucuk gorunmesi TEK BASINA HICBIR SEY IFADE ETMEZ. Gunluk log
getiriler zaten ~0.02 buyuklugundedir; 0.019'luk bir RMSE "harika" degil,
sadece "getiriler kucuk" demektir. Tek anlamli sayi skill_score'dur.
"""
from __future__ import annotations

import numpy as np

from .losses import pinball_loss_numpy


# ------------------------------------------------------------ getiri uzayi
def rmse(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    return float(np.sqrt(np.mean((np.asarray(y_true) - np.asarray(y_pred)) ** 2)))


def mae(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    return float(np.mean(np.abs(np.asarray(y_true) - np.asarray(y_pred))))


def coverage(y_true: np.ndarray, lo: np.ndarray, hi: np.ndarray) -> float:
    """
    Gercek degerin [lo, hi] araligina dusme orani.

    (0.1, 0.9) quantile'lari icin hedef ~0.80.
      cok DUSUK  -> model asiri kendinden emin, riski KUCUK gosteriyor (tehlikeli)
      cok YUKSEK -> model asiri temkinli, aralik ise yaramayacak kadar genis
    """
    y = np.asarray(y_true)
    return float(np.mean((y >= np.asarray(lo)) & (y <= np.asarray(hi))))


def interval_width(lo: np.ndarray, hi: np.ndarray) -> float:
    """Ortalama p90-p10 genisligi = ham RISK SINYALI."""
    return float(np.mean(np.asarray(hi) - np.asarray(lo)))


def directional_accuracy(y_true: np.ndarray, y_pred_median: np.ndarray) -> tuple[float, int]:
    """
    sign(tahmin) == sign(gercek) orani.

    Doner: (dogruluk, karar_sayisi)

    NIYE karar_sayisi: naive her zaman 0 tahmin eder, yani HIC yon
    soylemez. Onun DA'sini 0.5 diye raporlamak ona olmayan bir yetenek
    atfetmektir. Yon soylemeyen tahminleri sayidan duseriz ve kac kez
    yon soylendigini ayrica raporlariz. n=0 ise DA tanimsizdir (nan).
    """
    y = np.asarray(y_true).ravel()
    p = np.asarray(y_pred_median).ravel()

    called = p != 0.0  # tahmin bir yon soyluyor mu?
    n = int(called.sum())
    if n == 0:
        return float("nan"), 0

    hit = np.sign(p[called]) == np.sign(y[called])
    return float(np.mean(hit)), n


# ------------------------------------------------------------- fiyat uzayi
def to_price(anchor: np.ndarray, log_ret: np.ndarray) -> np.ndarray:
    """
    P_t = anchor * exp(r_t)

    anchor = hedef gunden BIR ONCEKI kapanis (data/dataset.py saglar).
    """
    return np.asarray(anchor, dtype=np.float64) * np.exp(np.asarray(log_ret, dtype=np.float64))


def price_rmse(anchor: np.ndarray, y_true_ret: np.ndarray, y_pred_ret: np.ndarray) -> float:
    """
    Dolar cinsinden RMSE. SADECE yorumlanabilirlik icin -- KIYAS ICIN DEGIL.

    UYARI: fiyat uzayindaki RMSE her zaman "iyi" gorunur cunku
    anchor * exp(kucuk sayi) ~ anchor'dur. Bir modeli fiyat RMSE'siyle
    savunmak, hedefi gizlice fiyat seviyesine geri cevirmektir. Karar her
    zaman getiri uzayindaki skill_score ile verilir.
    """
    return rmse(to_price(anchor, y_true_ret), to_price(anchor, y_pred_ret))


# ------------------------------------------------------------------ kiyas
def skill_score(rmse_model: float, rmse_naive: float) -> float:
    """1 - rmse_model / rmse_naive.  > 0 ise naive yenildi."""
    if rmse_naive <= 0:
        return float("nan")
    return float(1.0 - rmse_model / rmse_naive)


# -------------------------------------------------------------- toplu hesap
def evaluate_predictions(
    y_true_ret: np.ndarray,
    pred_ret: np.ndarray,
    quantiles: tuple[float, ...],
    anchor_price: np.ndarray | None = None,
    name: str = "?",
) -> dict:
    """
    Args:
        y_true_ret : (N, horizon)     -- gercek LOG GETIRI
        pred_ret   : (N, horizon, Q)  -- tahmin LOG GETIRI quantile'lari
        quantiles  : Q uzunlugunda
        anchor_price: (N,) -- varsa fiyat metrikleri de hesaplanir
                              (yalnizca horizon=0 adimi icin gecerli)

    Doner: metrik sozlugu. skill_score BURADA hesaplanmaz -- naive'e
           ihtiyaci var, onu evaluate.py tabloyu kurarken ekler.
    """
    y = np.asarray(y_true_ret, dtype=np.float64)
    p = np.asarray(pred_ret, dtype=np.float64)

    if p.shape[:2] != y.shape:
        raise ValueError(f"sekil uyusmazligi: pred {p.shape} vs true {y.shape}")
    if p.shape[-1] != len(quantiles):
        raise ValueError(f"quantile sayisi uyusmuyor: {p.shape[-1]} vs {len(quantiles)}")

    qs = list(quantiles)
    i_med = qs.index(0.5)
    i_lo, i_hi = 0, len(qs) - 1  # en dis cift

    med = p[..., i_med]   # (N, horizon)
    lo = p[..., i_lo]
    hi = p[..., i_hi]

    da, n_calls = directional_accuracy(y[:, 0], med[:, 0])

    out = {
        "model": name,
        "rmse_ret": rmse(y, med),
        "mae_ret": mae(y, med),
        "pinball": pinball_loss_numpy(p, y, qs),
        "coverage": coverage(y, lo, hi),
        "nominal_cov": qs[i_hi] - qs[i_lo],
        "width": interval_width(lo, hi),
        "dir_acc": da,
        "n_calls": n_calls,
    }

    if anchor_price is not None:
        # Fiyat metrikleri yalnizca ilk ufuk adimi icin anlamli:
        # anchor, hedef gunden bir onceki kapanistir.
        out["rmse_price"] = price_rmse(anchor_price, y[:, 0], med[:, 0])

    return out
