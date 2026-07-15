"""
Per-pozisyon anlik gorunum + fiyat bazli period degisimi.

UI /portfolio sayfasi bunu ister: her hisse icin adet, cari fiyat, deger,
agirlik ve gunluk/haftalik/aylik degisim. HESAP BURADA (alt katman); API
yalnizca sunar -- ayni sayi UI'da yeniden hesaplanmaz.

Period degisimi = hissenin adj_close getirisidir (1 / 5 / 21 islem gunu; 21
projedeki aylik penceredir, bkz. features.rv_21). YALNIZCA GECMIS fiyat kullanilir
(leakage yok). Yetersiz gecmis -> None; 0 UYDURULMAZ ("veri yok" != "deger 0").
"""
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from data.calendar import union_calendar

from .config import PRICE_COL
from .portfolio import Portfolio

DAILY, WEEKLY, MONTHLY = 1, 5, 21


@dataclass
class Position:
    ticker: str
    shares: float
    price: float | None          # cari (son bilinen) fiyat
    value: float | None          # shares * price
    weight: float | None         # pozisyonun toplam pozisyon degerine orani
    change_1d: float | None
    change_1w: float | None
    change_1m: float | None


@dataclass
class PositionsView:
    as_of: pd.Timestamp | None
    cash: float
    total_value: float | None    # nakit + pozisyon degeri (eksik fiyat varsa None)
    positions: list[Position]


def pct_change(prices: pd.Series, k: int) -> float | None:
    """adj_close return over k trading days, using only past prices (no leakage).
    Insufficient history -> None (never fabricated 0)."""
    p = prices.dropna()
    if len(p) < k + 1:
        return None
    a, b = p.iloc[-1], p.iloc[-1 - k]
    if pd.isna(a) or pd.isna(b) or b == 0:
        return None
    return float(a / b - 1.0)


def positions_view(
    pf: Portfolio,
    price_frames: dict[str, pd.DataFrame],
    *,
    price_col: str = PRICE_COL,
    as_of=None,
) -> PositionsView:
    """
    Portfolyonun anlik pozisyon gorunumu. Fiyati olmayan pozisyon icin
    price/value/weight/degisim None kalir (K5 ruhu). Bir pozisyonun fiyati
    eksikse toplam deger de None (bilinmeyen) -- 0 sayilmaz.
    """
    state = pf.replay(as_of=as_of)
    cal = union_calendar(price_frames)
    as_of_label = cal[-1] if len(cal) else state.as_of

    tmp = []
    pos_value_sum = 0.0
    have_all = True
    for ticker, shares in state.holdings.items():
        if ticker in price_frames:
            series = price_frames[ticker][price_col]
        else:
            series = pd.Series(dtype="float64")
        s = series.dropna()
        price = float(s.iloc[-1]) if len(s) else None
        value = (shares * price) if price is not None else None
        if value is None:
            have_all = False
        else:
            pos_value_sum += value
        tmp.append((ticker, shares, series, price, value))

    positions = []
    for ticker, shares, series, price, value in tmp:
        weight = (value / pos_value_sum) if (value is not None and pos_value_sum > 0) else None
        positions.append(Position(
            ticker=ticker,
            shares=shares,
            price=price,
            value=value,
            weight=weight,
            change_1d=pct_change(series, DAILY),
            change_1w=pct_change(series, WEEKLY),
            change_1m=pct_change(series, MONTHLY),
        ))

    positions.sort(key=lambda p: (p.value if p.value is not None else -1.0), reverse=True)
    total = (state.cash + pos_value_sum) if have_all else None
    return PositionsView(as_of=as_of_label, cash=state.cash, total_value=total, positions=positions)
