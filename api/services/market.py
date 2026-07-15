"""
Market overview: latest price + 1d/1w/1m change for a curated set of
high-liquidity NASDAQ tickers. Prices come from the cache-first PriceProvider
(yfinance under the hood); period change reuses portfolio.positions.pct_change.
"""
from __future__ import annotations

import pandas as pd

from portfolio.positions import pct_change

# Curated high-traffic NASDAQ names. Not an exhaustive index; a legible overview.
NASDAQ_TOP = [
    "AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "TSLA", "AVGO",
    "COST", "PEP", "NFLX", "AMD", "ADBE", "INTC", "CSCO", "QCOM",
    "TMUS", "AMAT", "MU", "INTU", "BKNG", "ISRG", "ADP", "GILD",
]

_DAILY, _WEEKLY, _MONTHLY = 1, 5, 21


def build_overview(
    frames: dict[str, pd.DataFrame],
    model_tickers: set[str],
    *,
    price_col: str = "adj_close",
) -> list[dict]:
    rows = []
    for ticker in NASDAQ_TOP:
        df = frames.get(ticker)
        if df is None or price_col not in df:
            rows.append({"ticker": ticker, "has_model": ticker in model_tickers})
            continue
        s = df[price_col].dropna()
        rows.append({
            "ticker": ticker,
            "price": float(s.iloc[-1]) if len(s) else None,
            "change_1d": pct_change(s, _DAILY),
            "change_1w": pct_change(s, _WEEKLY),
            "change_1m": pct_change(s, _MONTHLY),
            "has_model": ticker in model_tickers,
        })
    return rows
