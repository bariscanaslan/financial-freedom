"""
Pinball (quantile) loss.

Neden MSE degil:
  MSE, kosullu ORTALAMAYI tahmin etmeye zorlar -- tek sayi, belirsizlik yok.
  Pinball loss, q. quantile'i asimetrik cezalandirir:

      q  = 0.9  -> dusuk tahmin etmek 9 kat pahali  => model yukari kacar
      q  = 0.1  -> yuksek tahmin etmek 9 kat pahali => model asagi kacar
      q  = 0.5  -> simetrik (= MAE)                 => medyan

  Bu asimetri sayesinde tek bir ag, ayni gecisten uc farkli quantile
  ogrenir ve p90-p10 genisligi dogal olarak BELIRSIZLIK olcusu olur.
"""
from __future__ import annotations

from collections.abc import Sequence

import torch


def pinball_loss(
    pred: torch.Tensor,
    target: torch.Tensor,
    quantiles: Sequence[float],
    reduction: str = "mean",
) -> torch.Tensor:
    """
    Args:
        pred:      (N, horizon, Q)  -- tahmin edilen quantile'lar
        target:    (N, horizon)     -- gercek deger
        quantiles: uzunlugu Q olan quantile listesi
        reduction: "mean" | "none"

    Doner:
        reduction="mean" -> skaler
        reduction="none" -> (N, horizon, Q) ham kayip

    Not: pred ve target AYNI uzayda olmali (egitimde: olceklenmis log getiri).
    """
    if pred.ndim != 3:
        raise ValueError(f"pred (N, horizon, Q) olmali, geldi: {tuple(pred.shape)}")
    if target.ndim != 2:
        raise ValueError(f"target (N, horizon) olmali, geldi: {tuple(target.shape)}")
    if pred.shape[-1] != len(quantiles):
        raise ValueError(
            f"pred son boyutu {pred.shape[-1]} != len(quantiles) {len(quantiles)}"
        )
    if pred.shape[:2] != target.shape:
        raise ValueError(
            f"sekil uyusmazligi: pred {tuple(pred.shape)} vs target {tuple(target.shape)}"
        )

    q = torch.as_tensor(quantiles, dtype=pred.dtype, device=pred.device)  # (Q,)

    # (N, horizon, 1) - (N, horizon, Q) -> (N, horizon, Q)
    err = target.unsqueeze(-1) - pred

    # y > pred (yetersiz tahmin) -> q * err
    # y < pred (asiri tahmin)    -> (q - 1) * err   [err < 0 oldugu icin pozitif]
    loss = torch.maximum(q * err, (q - 1.0) * err)

    if reduction == "none":
        return loss
    if reduction == "mean":
        return loss.mean()
    raise ValueError(f"bilinmeyen reduction: {reduction}")


def pinball_loss_numpy(pred, target, quantiles) -> float:
    """
    metrics.py ve baseline'lar icin numpy karsiligi (grafik yok, sadece sayi).

    pred: (N, horizon, Q), target: (N, horizon)
    """
    import numpy as np

    pred = np.asarray(pred, dtype=np.float64)
    target = np.asarray(target, dtype=np.float64)
    q = np.asarray(quantiles, dtype=np.float64)

    err = target[..., None] - pred
    loss = np.maximum(q * err, (q - 1.0) * err)
    return float(loss.mean())
