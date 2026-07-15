"""
actual vs simulated vs benchmark tek tabloda (K4).

Getiri tek basina anlamsizdir: her portfolyo buy-and-hold benchmark'a (SPY)
karsi verilir. Benchmark, actual'in DIS akislari ayni tarihlerde SPY'a
konsaydi senaryosundan uretilir -- boylece kiyas adildir (ayni para, ayni
zamanlama, ayni fee modeli, ayni valuation motoru).
"""
from __future__ import annotations

import pandas as pd

from .config import BENCHMARK_TICKER, PRICE_COL
from .metrics import Performance, daily_returns, performance
from .portfolio import Portfolio
from .simulate import buy_and_hold_from_flows
from .valuation import value_series


def _perf(
    pf: Portfolio,
    label: str,
    price_frames: dict,
    bench_returns: pd.Series | None,
    price_col: str,
    ffill: bool,
) -> Performance:
    vs = value_series(pf, price_frames, price_col=price_col, ffill=ffill)
    return performance(vs, label, benchmark_returns=bench_returns)


def build_report(
    actual: Portfolio,
    simulated: Portfolio | None,
    price_frames: dict[str, pd.DataFrame],
    *,
    benchmark_ticker: str = BENCHMARK_TICKER,
    price_col: str = PRICE_COL,
    ffill: bool = False,
) -> pd.DataFrame:
    """
    Doner: her satiri bir portfolyo (actual / simulated / benchmark) olan
    performans tablosu. benchmark her zaman tablodadir.
    """
    # benchmark: actual'in dis akislarini benchmark_ticker'a koy
    bench_events = buy_and_hold_from_flows(
        actual, benchmark_ticker, price_frames, portfolio_id="benchmark",
        price_col=price_col,
    )
    benchmark = Portfolio("benchmark", bench_events)

    bench_vs = value_series(benchmark, price_frames, price_col=price_col, ffill=ffill)
    bench_returns = daily_returns(bench_vs["total_value"], bench_vs["external_flow"])

    rows = [
        _perf(actual, "actual", price_frames, bench_returns, price_col, ffill).to_row(),
    ]
    if simulated is not None:
        rows.append(
            _perf(simulated, "simulated", price_frames, bench_returns, price_col, ffill).to_row()
        )
    rows.append(
        performance(bench_vs, f"benchmark ({benchmark_ticker})").to_row()
    )
    return pd.DataFrame(rows)


def render(df: pd.DataFrame) -> str:
    """Insan okuyacak tablo."""
    show = df.copy()
    for c in ["total_return", "ann_return", "ann_vol", "max_drawdown", "alpha"]:
        if c in show:
            show[c] = show[c].map(lambda v: f"{v:+.2%}" if pd.notna(v) else "-")
    for c in ["sharpe", "beta"]:
        if c in show:
            show[c] = show[c].map(lambda v: f"{v:.2f}" if pd.notna(v) else "-")
    return show.to_string(index=False)
