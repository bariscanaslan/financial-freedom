"""
Fiyat saglayici: data/loader uzerine ince kabuk.

AG SINIRI BURADA. Endpoint'ler keyfi URL fetch etmez; yalnizca loader.fetch
(cache'li) cagirilir. Cache taze ise ag'a gidilmez (data/config.CACHE_TTL_HOURS).

Testlerde bu sinif dependency_overrides ile sahte bir saglayiciyla degistirilir,
boylece smoke testi AGSIZ kosar.
"""
from __future__ import annotations

import pandas as pd

from data.loader import fetch, fetch_intraday, fetch_many
from data.config import RAW_DIR
from data.calendar import to_market_date


class PriceProvider:
    """Uretim saglayicisi: loader.fetch (cache-first)."""

    def __init__(self, redis_backend=None):
        self._redis = redis_backend

    def recent(self, ticker: str) -> pd.DataFrame:
        # NOT: ticker cache'te yoksa ilk cagri AG'a gider (yfinance). Sonraki
        # cagrilar cache'ten okur. Request basina canli indirme YOKTUR.
        return fetch(ticker)

    def refresh(self, ticker: str) -> pd.DataFrame:
        """TTL'yi atlayarak ticker cache'ini varsayılan tam aralıkla yeniler."""
        return fetch(ticker, force=True)

    def refresh_intraday(self, ticker: str) -> pd.DataFrame:
        frame = fetch_intraday(ticker, force=True)
        self._cache_quote(ticker, frame)
        return frame

    def cached_tickers(self) -> list[str]:
        return sorted(path.stem.upper() for path in RAW_DIR.glob("*.parquet"))

    def frames(self, tickers: list[str]) -> dict[str, pd.DataFrame]:
        if not tickers:
            return {}
        return fetch_many(list(tickers))

    def latest_quote(self, ticker: str) -> tuple[float, pd.Timestamp]:
        key = f"market:quote:{ticker.upper()}"
        cached = self._redis.get_json(key) if self._redis else None
        if cached:
            return float(cached["price"]), pd.Timestamp(cached["timestamp"])
        frame = fetch_intraday(ticker)
        series = frame["adj_close"].dropna()
        if series.empty:
            raise ValueError(f"{ticker}: güncel fiyat yok")
        value, timestamp = float(series.iloc[-1]), pd.Timestamp(series.index[-1])
        if self._redis:
            self._redis.set_json(key, {"price": value, "timestamp": timestamp.isoformat()},
                                 self._redis.market_ttl)
        return value, timestamp

    def _cache_quote(self, ticker: str, frame: pd.DataFrame) -> None:
        if not self._redis or frame.empty or "adj_close" not in frame:
            return
        series = frame["adj_close"].dropna()
        if not series.empty:
            self._redis.set_json(f"market:quote:{ticker.upper()}",
                {"price": float(series.iloc[-1]), "timestamp": pd.Timestamp(series.index[-1]).isoformat()},
                self._redis.market_ttl)

    def frames_live(self, tickers: list[str]) -> dict[str, pd.DataFrame]:
        frames = self.frames(tickers)
        for ticker, frame in frames.items():
            try:
                value, timestamp = self.latest_quote(ticker)
            except Exception:  # intraday yoksa günlük kapanış güvenli fallback
                continue
            day = to_market_date(timestamp)
            if day not in frame.index:
                frame.loc[day] = frame.iloc[-1]
            frame.loc[day, "close"] = value
            frame.loc[day, "adj_close"] = value
            frames[ticker] = frame.sort_index()
        return frames
