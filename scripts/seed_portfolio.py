"""
Seeds the SQLite database with two demo portfolios (actual + simulated) so
smoke runs and manual dev have data. Uses real prices (yfinance cache) to pick
a reasonable buy price; fee/slippage applied via invest_cash.

Run:
    .venv/bin/python scripts/seed_portfolio.py [TICKER]
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from api.config import get_settings  # noqa: E402
from api.services.db import Database  # noqa: E402
from data.loader import fetch  # noqa: E402
from portfolio.config import PRICE_COL  # noqa: E402
from portfolio.events import Event, EventType  # noqa: E402
from portfolio.simulate import invest_cash  # noqa: E402

TICKER = (sys.argv[1] if len(sys.argv) > 1 else "AAPL").upper()
MARKET_TZ = "America/New_York"


def _market_ts(d) -> pd.Timestamp:
    return pd.Timestamp(d).tz_localize(MARKET_TZ)


def _first_on_or_after(index: pd.DatetimeIndex, d: str) -> pd.Timestamp:
    hit = index[index >= pd.Timestamp(d)]
    if len(hit) == 0:
        raise SystemExit(f"no trading day after {d}")
    return hit[0]


def _seed_track(db: Database, name: str, kind: str, buy_after: str) -> str:
    df = fetch(TICKER, start="2015-01-01")
    price = df[PRICE_COL].dropna()
    pf = db.create_portfolio(name, kind)
    pid = pf["id"]
    d0 = _first_on_or_after(price.index, buy_after)
    db.append_event(Event(pid, EventType.DEPOSIT, _market_ts(d0), cash=10_000.0))
    buy = invest_cash(pid, TICKER, 10_000.0, float(price.loc[d0]), _market_ts(d0),
                      note=f"seed {kind}")
    if buy is not None:
        db.append_event(buy)
    return f"{name} ({kind}) buy={d0.date()}"


def main() -> int:
    settings = get_settings()
    db = Database(settings.db_path)
    # actual: buy early and hold
    a = _seed_track(db, "Demo Actual", "actual", "2023-01-03")
    # simulated: same money 3 months later (divergent curve)
    s = _seed_track(db, "Demo Simulation", "simulated", "2023-04-03")
    db.close()
    print(f"seed done: {settings.db_path}")
    print(f"  ticker={TICKER}  {a}  |  {s}")
    print("\nStart the API with:")
    print(f"  SPP_API_DB_PATH={settings.db_path} .venv/bin/uvicorn api.main:app")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
