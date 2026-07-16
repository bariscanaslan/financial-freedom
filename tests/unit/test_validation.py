import pandas as pd
import pytest

from data.validate import validate


pytestmark = pytest.mark.unit


def _prices() -> pd.DataFrame:
    index = pd.bdate_range("2026-01-02", periods=3)
    return pd.DataFrame(
        {
            "open": [10, 11, 12], "high": [11, 12, 13], "low": [9, 10, 11],
            "close": [10, 11, 12], "adj_close": [10, 11, 12], "volume": [100, 100, 100],
        },
        index=index,
    )


def test_valid_prices_pass() -> None:
    assert validate(_prices(), "TEST").ok


def test_duplicate_and_non_positive_prices_fail() -> None:
    frame = _prices()
    frame.index = pd.to_datetime(["2026-01-03", "2026-01-02", "2026-01-02"])
    frame.loc[:, "close"] = [10, 0, 12]
    report = validate(frame, "TEST")
    assert not report.ok
    assert any("tekrarli" in error for error in report.errors)
    assert any("pozitif olmayan" in error for error in report.errors)
