import pandas as pd
import pytest

from api.services.db import Database
from portfolio.events import Event, EventType
from portfolio.portfolio import Portfolio


pytestmark = pytest.mark.integration


def test_database_round_trip_and_portfolio_isolation(tmp_path) -> None:
    db = Database(tmp_path / "test.db")
    try:
        first = db.create_portfolio("First", "actual")["id"]
        second = db.create_portfolio("Second", "simulated")["id"]
        db.append_event(Event(first, EventType.DEPOSIT, pd.Timestamp("2026-01-02"), cash=1000))
        db.append_event(
            Event(first, EventType.BUY, pd.Timestamp("2026-01-03"), "AAPL", 2, 100, fees=1)
        )
        db.append_event(Event(second, EventType.DEPOSIT, pd.Timestamp("2026-01-02"), cash=500))

        first_state = Portfolio(first, db.events_for(first)).replay()
        second_state = Portfolio(second, db.events_for(second)).replay()
        assert first_state.holdings == {"AAPL": 2}
        assert first_state.cash == 799
        assert second_state.holdings == {}
        assert second_state.cash == 500

        assert db.delete_portfolio(first)
        assert db.events_for(first) == []
        assert db.get_portfolio(second) is not None
    finally:
        db.close()
