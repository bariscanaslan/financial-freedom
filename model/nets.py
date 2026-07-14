"""
Sinir agi mimarisi: QuantileLSTM.

TASARIMIN KALBI -- quantile crossing'i CEZALANDIRMIYORUZ, IMKANSIZ KILIYORUZ.

Naif yaklasim: Linear katman len(quantiles) sayi uretir, pinball loss
"umarim sirali cikarlar" der. Cikmazlar. Egitimin ortasinda p10 > p50
gorursun ve "%80 guven araligi" dedigin sey negatif genislige duser.
Urun risk yorumlamasi vaat ediyorsa bu kabul edilemez.

Cozum -- medyani cipa al, komsulari softplus ile ittir:

    out[m]   = raw[m]                        m = medyanin (0.5) indeksi
    out[i]   = out[i-1] + softplus(raw[i])   i > m   (yukari, kumulatif)
    out[i]   = out[i+1] - softplus(raw[i])   i < m   (asagi, kumulatif)

softplus(x) > 0 her zaman. Dolayisiyla p10 < p50 < p90 bir UMUT degil,
mimarinin cebirsel sonucudur. Model hangi agirliklari ogrenirse ogrensin,
ne kadar kotu egitilirse egitilsin, crossing uretemez.
"""
from __future__ import annotations

from collections.abc import Sequence

import torch
import torch.nn as nn
import torch.nn.functional as F


class QuantileLSTM(nn.Module):
    """
    Girdi : (B, seq_len, input_dim)  -- olceklenmis log getiri dizisi
    Cikti : (B, horizon, n_quantiles) -- olceklenmis log getiri quantile'lari

    Cikti SIRALIDIR: son eksen boyunca kesin artan.
    """

    def __init__(
        self,
        quantiles: Sequence[float],
        input_dim: int = 1,
        hidden_dim: int = 64,
        num_layers: int = 2,
        horizon: int = 1,
        dropout: float = 0.2,
    ) -> None:
        super().__init__()

        q = tuple(float(x) for x in quantiles)
        if list(q) != sorted(q):
            raise ValueError(f"quantiles sirali olmali: {q}")
        if 0.5 not in q:
            raise ValueError(f"quantiles medyani (0.5) icermeli: {q}")

        self.quantiles = q
        self.n_quantiles = len(q)
        self.median_idx = q.index(0.5)
        self.horizon = horizon
        self.hidden_dim = hidden_dim
        self.num_layers = num_layers

        self.lstm = nn.LSTM(
            input_size=input_dim,
            hidden_size=hidden_dim,
            num_layers=num_layers,
            batch_first=True,
            # PyTorch tek katmanda dropout'u yok sayar ve uyari basar.
            dropout=dropout if num_layers > 1 else 0.0,
        )
        # Son gizli durumdan horizon * quantile sayisi kadar HAM sayi.
        # "Ham" -- cunku sirasi henuz garanti degil; head bunu duzeltir.
        self.head = nn.Linear(hidden_dim, horizon * self.n_quantiles)

    # ------------------------------------------------------------------
    def _monotonic(self, raw: torch.Tensor) -> torch.Tensor:
        """
        (B, horizon, Q) ham cikti -> son eksende KESIN ARTAN cikti.

        Medyan oldugu gibi gecer; ustundekiler kumulatif softplus ile
        yukari, altindakiler asagi tasarlanir.
        """
        m = self.median_idx
        cols: list[torch.Tensor | None] = [None] * self.n_quantiles

        # medyan: serbest, isaret kisiti yok (getiri negatif olabilir)
        cols[m] = raw[..., m]

        # ustu: her adimda pozitif bir miktar EKLE
        for i in range(m + 1, self.n_quantiles):
            cols[i] = cols[i - 1] + F.softplus(raw[..., i])

        # alti: her adimda pozitif bir miktar CIKAR
        for i in range(m - 1, -1, -1):
            cols[i] = cols[i + 1] - F.softplus(raw[..., i])

        return torch.stack(cols, dim=-1)  # (B, horizon, Q)

    # ------------------------------------------------------------------
    def forward(self, x: torch.Tensor) -> torch.Tensor:
        if x.ndim != 3:
            raise ValueError(f"girdi (B, seq_len, input_dim) olmali: {tuple(x.shape)}")

        out, _ = self.lstm(x)          # (B, seq_len, hidden)
        last = out[:, -1, :]           # (B, hidden) -- dizinin son adimi
        raw = self.head(last)          # (B, horizon * Q)
        raw = raw.view(-1, self.horizon, self.n_quantiles)
        return self._monotonic(raw)

    # ------------------------------------------------------------------
    def n_params(self) -> int:
        return sum(p.numel() for p in self.parameters() if p.requires_grad)

    def extra_repr(self) -> str:
        return f"quantiles={self.quantiles}, horizon={self.horizon}"
