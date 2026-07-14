"""
Borsa takvimi yardimcilari.

Neden gerekli: portfolyo degerlemesi ve simulasyon "her gun" degil,
"her ISLEM gunu" hesaplanmali. Hafta sonu / tatil gunlerinde fiyat yoktur;
bunlari 0 veya NaN saymak simulasyonu bozar.
"""
from __future__ import annotations

import pandas as pd

from .config import MARKET_TZ


def to_market_date(ts) -> pd.Timestamp:
    """Herhangi bir timestamp'i borsa saat diliminde, saatsiz bir gune cevirir."""
    ts = pd.Timestamp(ts)
    if ts.tz is None:
        ts = ts.tz_localize("UTC")
    return ts.tz_convert(MARKET_TZ).normalize().tz_localize(None)


def trading_days(index: pd.DatetimeIndex) -> pd.DatetimeIndex:
    """
    Gercek islem gunleri = veride bar bulunan gunler.

    Ayri bir takvim kutuphanesi (exchange_calendars) kullanmak yerine
    veriyi kaynak kabul ediyoruz. Boylece tatil listesi guncel tutma
    derdi olmuyor ve veri ile takvim her zaman tutarli oluyor.
    """
    return pd.DatetimeIndex(sorted(set(index))).sort_values()


def align_to_trading_days(
    df: pd.DataFrame,
    calendar: pd.DatetimeIndex,
) -> pd.DataFrame:
    """
    Bir seriyi ortak islem gunu takvimine hizalar.

    Eksik gunler ffill EDILMEZ, NaN birakilir. Sebep: bir hisse o gun
    islem gormediyse (halt, henuz halka arz olmamis, delist olmus) bunu
    bilmek isteriz. ffill sessizce sahte veri uretir ve modelin
    "hicbir sey degismedi" ornekleri ogrenmesine yol acar.
    """
    return df.reindex(calendar)


def common_calendar(frames: dict[str, pd.DataFrame]) -> pd.DatetimeIndex:
    """Birden fazla ticker icin ORTAK islem gunlerini (kesisim) dondurur."""
    if not frames:
        return pd.DatetimeIndex([])
    idx = None
    for df in frames.values():
        cur = pd.DatetimeIndex(df.index)
        idx = cur if idx is None else idx.intersection(cur)
    return idx.sort_values()


def union_calendar(frames: dict[str, pd.DataFrame]) -> pd.DatetimeIndex:
    """Birlesim takvimi. Portfolyo degerlemesinde bunu kullan (kesisim degil)."""
    if not frames:
        return pd.DatetimeIndex([])
    idx = pd.DatetimeIndex([])
    for df in frames.values():
        idx = idx.union(pd.DatetimeIndex(df.index))
    return idx.sort_values()
