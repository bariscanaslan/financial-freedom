"""
SQLite persistence smoke test -- NETWORK-FREE.

Covers: portfolio create/list/get/delete (with event cascade), event
append/replay round-trip, and tracked-ticker upsert.
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd  # noqa: E402

from api.services.db import Database  # noqa: E402
from portfolio.events import Event, EventType  # noqa: E402
from portfolio.portfolio import Portfolio  # noqa: E402


def _check(name: str, ok: bool, detail: str = "") -> None:
    mark = "PASS" if ok else "FAIL"
    print(f"  [{mark}] {name}" + (f"  -- {detail}" if detail else ""))
    if not ok:
        raise AssertionError(f"{name}: {detail}")


def main() -> int:
    print("smoke_db -- network-free SQLite verification")
    db = Database(tempfile.mktemp(suffix=".db"))

    pf = db.create_portfolio("Test", "actual")
    pid = pf["id"]
    _check("create returns id + kind", bool(pid) and pf["kind"] == "actual", str(pf))
    _check("kind must be valid", _raises(lambda: db.create_portfolio("x", "bogus")))

    db.append_event(Event(pid, EventType.DEPOSIT, pd.Timestamp("2023-01-03"), cash=1000.0))
    db.append_event(Event(pid, EventType.BUY, pd.Timestamp("2023-01-03"),
                          ticker="AAPL", quantity=5.0, price=100.0, fees=1.0))

    events = db.events_for(pid)
    _check("events round-trip", len(events) == 2 and events[1].ticker == "AAPL", str(events))

    state = Portfolio(pid, events).replay()
    _check("replay from DB events", state.holdings.get("AAPL") == 5.0 and state.cash == 499.0,
           str(state))

    _check("list contains portfolio", any(p["id"] == pid for p in db.list_portfolios()))
    _check("get returns row", db.get_portfolio(pid) is not None)
    _check("get missing -> None", db.get_portfolio("act_missing00") is None)

    db.record_ticker("aapl")
    db.record_ticker("AAPL")
    db.record_ticker("MSFT")
    tks = {t["ticker"]: t["use_count"] for t in db.list_tickers()}
    _check("ticker upsert (case-insensitive)", tks.get("AAPL") == 2 and tks.get("MSFT") == 1,
           str(tks))

    forecast = {"ticker": "AAPL", "as_of": "2026-01-01", "periods": {"daily": {}}}
    saved = db.save_prediction("AAPL", "2026-01-01", forecast)
    predictions = db.list_predictions()
    _check("prediction save/list round-trip",
           len(predictions) == 1 and predictions[0]["id"] == saved["id"]
           and predictions[0]["forecast"] == forecast)
    _check("prediction detail", db.get_prediction(saved["id"])["ticker"] == "AAPL")
    _check("prediction delete", db.delete_prediction(saved["id"]) is True
           and db.get_prediction(saved["id"]) is None)

    risk = {"portfolio_id": pid, "values": {"p10": 900, "p50": 1000, "p90": 1100}}
    saved_risk = db.save_risk(pid, risk)
    risks = db.list_risks()
    _check("risk save/list round-trip", len(risks) == 1
           and risks[0]["id"] == saved_risk["id"] and risks[0]["risk"] == risk)
    _check("risk detail", db.get_risk(saved_risk["id"])["portfolio_id"] == pid)
    _check("risk delete", db.delete_risk(saved_risk["id"]) is True
           and db.get_risk(saved_risk["id"]) is None)

    draft = db.save_portfolio_draft({"name": "Taslak", "allocations": [], "feedback": ""})
    _check("portfolio draft round-trip", db.get_portfolio_draft(draft["id"])["name"] == "Taslak")
    updated = db.update_portfolio_draft(draft["id"], {"name": "Taslak", "allocations": [], "feedback": "Dengeli"})
    _check("portfolio draft update", updated["feedback"] == "Dengeli")

    _check("delete portfolio", db.delete_portfolio(pid) is True)
    _check("event cascade on delete", db.events_for(pid) == [])
    _check("delete missing -> False", db.delete_portfolio(pid) is False)

    db.close()
    print("ALL PASSED")
    return 0


def _raises(fn) -> bool:
    try:
        fn()
        return False
    except Exception:
        return True


if __name__ == "__main__":
    sys.exit(main())
