"""
OHLCV veri indirme + cache katmani.

Tasarim kararlari:
  - yfinance ciktisi ASLA disari sizmaz. Her sey normalize edilmis,
    tek seviyeli, kucuk harf kolonlu bir DataFrame olarak doner.
    (Notebook'taki MultiIndex kolon sorununun kaynagi buydu.)
  - Cache parquet. CSV degil: dtype ve timezone bilgisini kaybetmez.
  - auto_adjust=False + adj_close ayri kolon. Split/temettu duzeltmesini
    biz kontrol ederiz, kutuphane bizim adimiza sessizce yapmaz.
"""
from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta

import pandas as pd
import yfinance as yf

from .calendar import to_market_date
from .config import (
    CACHE_TTL_HOURS,
    DEFAULT_START,
    MIN_BARS,
    OHLCV_COLS,
    RAW_DIR,
)

log = logging.getLogger(__name__)


class DataError(Exception):
    """Veri katmani hatasi."""


# ---------------------------------------------------------------- normalize
def _normalize(raw: pd.DataFrame, ticker: str) -> pd.DataFrame:
    """yfinance ciktisini standart forma sokar."""
    if raw is None or raw.empty:
        raise DataError(f"{ticker}: bos veri dondu")

    df = raw.copy()

    # yfinance tek ticker'da bile MultiIndex kolon dondurebiliyor.
    if isinstance(df.columns, pd.MultiIndex):
        # ('Close', 'AAPL') -> 'Close'
        df.columns = df.columns.get_level_values(0)

    df.columns = [str(c).strip().lower().replace(" ", "_") for c in df.columns]

    # Kolon isim varyasyonlari
    rename = {"adjclose": "adj_close", "stock_splits": "splits"}
    df = df.rename(columns=rename)

    if "adj_close" not in df.columns and "close" in df.columns:
        # auto_adjust=True gelmisse close zaten adjusted'dir
        df["adj_close"] = df["close"]

    missing = [c for c in OHLCV_COLS if c not in df.columns]
    if missing:
        raise DataError(f"{ticker}: eksik kolon {missing}")

    df = df[OHLCV_COLS]

    # Index -> borsa gunu, tz-naive
    df.index = pd.DatetimeIndex([to_market_date(t) for t in df.index], name="date")
    df = df[~df.index.duplicated(keep="last")].sort_index()

    return df.astype("float64")


# -------------------------------------------------------------------- cache
def _cache_path(ticker: str):
    return RAW_DIR / f"{ticker.upper()}.parquet"


def _is_fresh(path) -> bool:
    if not path.exists():
        return False
    age = datetime.now() - datetime.fromtimestamp(path.stat().st_mtime)
    return age < timedelta(hours=CACHE_TTL_HOURS)


# -------------------------------------------------------------------- fetch
def fetch(
    ticker: str,
    start: str = DEFAULT_START,
    end: str | None = None,
    *,
    force: bool = False,
    retries: int = 3,
) -> pd.DataFrame:
    """
    Tek bir ticker icin OHLCV getirir. Cache varsa ve tazeyse onu kullanir.

    Doner: index=date (tz-naive, borsa gunu), kolonlar=OHLCV_COLS
    """
    ticker = ticker.upper().strip()
    path = _cache_path(ticker)

    if not force and _is_fresh(path):
        log.debug("%s: cache hit", ticker)
        df = pd.read_parquet(path)
    else:
        last_err = None
        for attempt in range(retries):
            try:
                raw = yf.download(
                    ticker,
                    start=start,
                    end=end,
                    auto_adjust=False,   # adj_close'u ayri istiyoruz
                    progress=False,
                    threads=False,
                )
                df = _normalize(raw, ticker)
                df.to_parquet(path)
                log.info("%s: %d bar indirildi", ticker, len(df))
                break
            except Exception as e:  # noqa: BLE001
                last_err = e
                sleep = 2 ** attempt
                log.warning("%s: deneme %d basarisiz (%s), %ds bekleniyor",
                            ticker, attempt + 1, e, sleep)
                time.sleep(sleep)
        else:
            if path.exists():
                log.warning("%s: indirme basarisiz, BAYAT cache kullaniliyor", ticker)
                df = pd.read_parquet(path)
            else:
                raise DataError(f"{ticker}: indirilemedi ({last_err})") from last_err

    # Cache tam araligi tutar; istenen pencereye kirp
    if start:
        df = df.loc[df.index >= pd.Timestamp(start)]
    if end:
        df = df.loc[df.index <= pd.Timestamp(end)]

    return df


def fetch_many(
    tickers: list[str],
    start: str = DEFAULT_START,
    end: str | None = None,
    *,
    force: bool = False,
    skip_failed: bool = True,
) -> dict[str, pd.DataFrame]:
    """
    Birden fazla ticker. Basarisizlari atlar (skip_failed=True) ve loglar.

    Portfolyo takibinde tek bir kotu ticker yuzunden tum yuklemenin
    patlamasini istemeyiz.
    """
    out: dict[str, pd.DataFrame] = {}
    failed: list[str] = []

    for t in tickers:
        try:
            df = fetch(t, start=start, end=end, force=force)
            if len(df) < MIN_BARS:
                raise DataError(f"{t}: yetersiz veri ({len(df)} < {MIN_BARS} bar)")
            out[t.upper()] = df
        except DataError as e:
            if not skip_failed:
                raise
            failed.append(t.upper())
            log.error("atlandi -> %s", e)

    if failed:
        log.warning("%d ticker atlandi: %s", len(failed), failed)

    return out
