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
from pathlib import Path

import pandas as pd
import yfinance as yf

from .calendar import to_market_date
from .config import (
    CACHE_TTL_HOURS,
    DEFAULT_START,
    MIN_BARS,
    OHLCV_COLS,
    RAW_DIR,
    INTRADAY_DIR,
    INTRADAY_CACHE_MINUTES,
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


def _quarantine(path: Path) -> None:
    """Bozuk cache'i silmeden kenara al; sonraki adım temiz indirme yapar."""
    if not path.exists():
        return
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    path.replace(path.with_suffix(f".parquet.corrupt-{stamp}"))


def _read_cache(path: Path, ticker: str) -> pd.DataFrame:
    try:
        return pd.read_parquet(path)
    except Exception as exc:  # noqa: BLE001
        log.error("%s: parquet cache bozuk, karantinaya aliniyor (%s)", ticker, exc)
        _quarantine(path)
        raise DataError(f"{ticker}: bozuk fiyat cache'i yenilenmeli") from exc


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
        try:
            df = _read_cache(path, ticker)
        except DataError:
            return fetch(ticker, start=start, end=end, force=True, retries=retries)
        # Eski normalizasyon saatsiz günlük barları UTC sayıp bir gün geri
        # kaydırıyordu. Hafta sonu etiketi bu cache'in kesin işaretidir.
        if any(pd.Timestamp(day).weekday() >= 5 for day in df.index):
            log.warning("%s: eski tarihli cache yenileniyor", ticker)
            return fetch(ticker, start=start, end=end, force=True, retries=retries)
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
                tmp = path.with_suffix(".parquet.tmp")
                df.to_parquet(tmp)
                tmp.replace(path)
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
                df = _read_cache(path, ticker)
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


def fetch_intraday(ticker: str, *, force: bool = False) -> pd.DataFrame:
    """Son 5 günün 15 dakikalık barlarını ayrı ve kısa ömürlü cache'te tutar."""
    ticker = ticker.upper().strip()
    path = INTRADAY_DIR / f"{ticker}.parquet"
    fresh = path.exists() and datetime.now() - datetime.fromtimestamp(path.stat().st_mtime) < timedelta(minutes=INTRADAY_CACHE_MINUTES)
    if not force and fresh:
        return pd.read_parquet(path)
    raw = yf.download(ticker, period="5d", interval="15m", auto_adjust=False,
                      progress=False, threads=False)
    if raw is None or raw.empty:
        if path.exists():
            return pd.read_parquet(path)
        raise DataError(f"{ticker}: 15 dakikalık veri alınamadı")
    frame = raw.copy()
    if isinstance(frame.columns, pd.MultiIndex):
        frame.columns = frame.columns.get_level_values(0)
    frame.columns = [str(column).strip().lower().replace(" ", "_") for column in frame.columns]
    frame = frame.rename(columns={"adjclose": "adj_close"})
    if "adj_close" not in frame and "close" in frame:
        frame["adj_close"] = frame["close"]
    frame = frame[[column for column in OHLCV_COLS if column in frame]].astype("float64")
    frame.index = pd.DatetimeIndex(frame.index, name="timestamp")
    tmp = path.with_suffix(".parquet.tmp")
    frame.to_parquet(tmp)
    tmp.replace(path)
    return frame
