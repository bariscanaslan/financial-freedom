import numpy as np
import pandas as pd
import pytest

from data.dataset import Scaler
from portfolio.events import Event, EventType, cash_delta
from portfolio.portfolio import Portfolio


pytestmark = pytest.mark.regression


def test_scaler_round_trip_preserves_values() -> None:
    values = np.array([-0.02, 0.0, 0.03], dtype=np.float64)
    scaler = Scaler(mean=0.005, std=0.02, fitted_on="train-only")
    assert np.allclose(scaler.inverse(scaler.transform(values)), values)
    assert scaler.fitted_on == "train-only"


def test_event_replay_is_deterministic_and_conserves_cash() -> None:
    events = [
        Event("p", EventType.DEPOSIT, pd.Timestamp("2026-01-02"), cash=1000),
        Event("p", EventType.BUY, pd.Timestamp("2026-01-03"), "AAPL", 3, 100, fees=2),
        Event("p", EventType.DIVIDEND, pd.Timestamp("2026-01-04"), "AAPL", cash=5),
    ]
    portfolio = Portfolio("p", events)
    first = portfolio.replay()
    second = portfolio.replay()
    assert first == second
    assert first.cash == sum(cash_delta(event) for event in events)
