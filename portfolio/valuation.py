"""
Portfolyoyu ISLEM GUNU takvimi boyunca degerler (mark-to-market).

FIYAT MANTIGI BURADA. portfolio.replay() adet/nakit verir; bu katman onu
piyasa fiyatiyla carpar.

K5 (islem gunu disiplini): degerleme yalnizca islem gunlerinde yapilir.
Takvim = data.union_calendar(price_frames) -- veride bar bulunan gunlerin
birlesimi. Hafta sonu/tatil zaten yoktur.

K5 (ffill kurali): fiyati olmayan gun icin varsayilan ffill YOKTUR. Bir hisse
o gun islem gormediyse (halt, delist, henuz halka arz olmamis) fiyati NaN'dir
ve o gunku deger de NaN'dir -- 0 saymak degeri sessizce bozar. Son bilinen
kapanisi tasimak (ffill=True) BILINCLI bir secimdir, sessiz varsayilan degil.

K6 (corporate actions): fiyat adj_close'tur (split+temettu duzeltilmis).
Deger = adet * adj_close; toplam getiri zaten adj_close'un icindedir, bu yuzden
ayri SPLIT/DIVIDEND event'ine gerek yoktur. Karar: adj_close BAZLI calis.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from data.calendar import union_calendar

from .config import PRICE_COL
from .events import EventType, cash_delta, external_flow
from .portfolio import Portfolio

_VALUE_COLS = ["cash", "position_value", "total_value", "external_flow"]


def _price_matrix(
    tickers: list[str],
    price_frames: dict[str, pd.DataFrame],
    calendar: pd.DatetimeIndex,
    price_col: str,
    ffill: bool,
) -> pd.DataFrame:
    """Her ticker icin takvime hizalanmis fiyat serisi. ffill=False -> NaN kalir."""
    cols = {}
    for t in tickers:
        if t not in price_frames:
            raise ValueError(f"{t} icin fiyat verisi yok (price_frames eksik)")
        s = price_frames[t][price_col].reindex(calendar)
        if ffill:
            s = s.ffill()
        cols[t] = s
    return pd.DataFrame(cols, index=calendar)


def value_series(
    portfolio: Portfolio,
    price_frames: dict[str, pd.DataFrame],
    *,
    calendar: pd.DatetimeIndex | None = None,
    price_col: str = PRICE_COL,
    ffill: bool = False,
    start: pd.Timestamp | None = None,
    end: pd.Timestamp | None = None,
) -> pd.DataFrame:
    """
    Portfolyonun gunluk deger serisini uretir.

    Doner: kolonlari [cash, position_value, total_value, external_flow] olan,
    islem gunu takvimine indeksli DataFrame.

    total_value bir gun NaN olabilir: o gun ACIK bir pozisyonun fiyati yoksa.
    Bu bir hata degil, "o gunku degeri bilmiyoruz"un durustce raporlanmasidir.
    """
    if calendar is None:
        calendar = union_calendar(price_frames)
    calendar = pd.DatetimeIndex(calendar).sort_values()

    lo = pd.Timestamp(start) if start is not None else portfolio.first_date
    hi = pd.Timestamp(end) if end is not None else calendar[-1] if len(calendar) else None
    if lo is not None:
        calendar = calendar[calendar >= lo]
    if hi is not None:
        calendar = calendar[calendar <= hi]
    if len(calendar) == 0:
        return pd.DataFrame(columns=_VALUE_COLS)

    tickers = portfolio.tickers()
    prices = _price_matrix(tickers, price_frames, calendar, price_col, ffill)

    events = portfolio.events()
    n = len(events)
    ei = 0
    holdings: dict[str, float] = {t: 0.0 for t in tickers}
    cash = 0.0

    rows = []
    for d in calendar:
        flow_today = 0.0
        # o gune (dahil) kadar uygulanmamis tum event'leri isle
        while ei < n and events[ei].timestamp <= d:
            e = events[ei]
            cash += cash_delta(e)
            flow_today += external_flow(e)
            if e.type is EventType.BUY:
                holdings[e.ticker] = holdings.get(e.ticker, 0.0) + e.quantity
            elif e.type is EventType.SELL:
                holdings[e.ticker] = holdings.get(e.ticker, 0.0) - e.quantity
            elif e.type is EventType.SPLIT:
                holdings[e.ticker] = holdings.get(e.ticker, 0.0) * e.quantity
            ei += 1

        # pozisyon degeri: adet 0 ise fiyat NaN olsa bile katki 0 (0-guard).
        # Yalnizca ACIK pozisyonun NaN fiyati toplami NaN yapar -- kasitli.
        pos_val = 0.0
        for t, q in holdings.items():
            if abs(q) <= 1e-12:
                continue
            p = prices.at[d, t]
            pos_val += q * p  # p NaN ise pos_val NaN olur (acik pozisyon, bilinmiyor)

        total = cash + pos_val
        rows.append((cash, pos_val, total, flow_today))

    return pd.DataFrame(rows, index=calendar, columns=_VALUE_COLS)
