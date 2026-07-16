import pandas as pd
import pytest

from data.calendar import align_to_trading_days, common_calendar, to_market_date


pytestmark = pytest.mark.unit


def test_naive_market_date_is_not_shifted() -> None:
    assert to_market_date("2026-01-15 23:30:00") == pd.Timestamp("2026-01-15")


def test_common_calendar_returns_intersection() -> None:
    frames = {
        "A": pd.DataFrame(index=pd.to_datetime(["2026-01-02", "2026-01-05"])),
        "B": pd.DataFrame(index=pd.to_datetime(["2026-01-05", "2026-01-06"])),
    }
    assert common_calendar(frames).tolist() == [pd.Timestamp("2026-01-05")]


def test_alignment_does_not_forward_fill_missing_prices() -> None:
    frame = pd.DataFrame({"adj_close": [10.0]}, index=pd.to_datetime(["2026-01-02"]))
    aligned = align_to_trading_days(
        frame, pd.to_datetime(["2026-01-02", "2026-01-05"])
    )
    assert pd.isna(aligned.loc["2026-01-05", "adj_close"])
