import pandas as pd
import pytest

from portfolio.events import Event, EventType, cash_delta, external_flow


pytestmark = pytest.mark.unit


def test_trade_cash_deltas_include_fees() -> None:
    buy = Event("p", EventType.BUY, pd.Timestamp("2026-01-02"), "aapl", 2, 100, fees=3)
    sell = Event("p", EventType.SELL, pd.Timestamp("2026-01-03"), "AAPL", 1, 110, fees=2)
    assert buy.ticker == "AAPL"
    assert cash_delta(buy) == -203
    assert cash_delta(sell) == 108


def test_only_deposits_and_withdrawals_are_external_flows() -> None:
    deposit = Event("p", EventType.DEPOSIT, pd.Timestamp("2026-01-02"), cash=100)
    dividend = Event("p", EventType.DIVIDEND, pd.Timestamp("2026-01-03"), "AAPL", cash=5)
    assert external_flow(deposit) == 100
    assert external_flow(dividend) == 0


@pytest.mark.parametrize("quantity,price", [(0, 10), (-1, 10), (1, -1)])
def test_invalid_trades_are_rejected(quantity: float, price: float) -> None:
    with pytest.raises(ValueError):
        Event("p", EventType.BUY, pd.Timestamp("2026-01-02"), "AAPL", quantity, price)
