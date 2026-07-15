"""
Portfolyo katmani smoke testi -- AGSIZ.

Sentetik fiyat serisi + elle kurulmus event log ile muhasebe cekirdegini
dogrular. Model/torch gerekmez; yalnizca event -> replay -> valuation yolu.

Dogrulananlar:
  1. Replay determinizmi     : ayni log -> ayni durum
  2. Nakit korunumu          : valuation nakiti == cash_delta toplami
  3. Adet korunumu           : holdings == bagimsiz buy/sell toplami
  4. Muhasebe kimligi        : total == katkilar + dividend + invest_pnl - fees
  5. Fee'li < fee'siz        : islem maliyeti degeri KESIN dusurur
  6. Benchmark buy-and-hold  : simulate + valuation tutarli
  7. Islem gunu disiplini    : hafta sonu degerleme yok

Kimlik testinde tolerans 1e-6'dan siki (1e-9) -- gevsek toleransla muhasebe
hatasini saklamak, sessiz yalanin ta kendisidir.
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from data.calendar import to_market_date
from portfolio.events import Event, EventType, cash_delta
from portfolio.metrics import daily_returns
from portfolio.portfolio import Portfolio
from portfolio.simulate import buy_and_hold_from_flows, make_buy
from portfolio.valuation import value_series

TOL = 1e-9
N = 40


# --------------------------------------------------------------- sentetik veri
def _calendar() -> pd.DatetimeIndex:
    # tz-aware NY islem gunleri -> to_market_date gun kaymasi yapmaz, hafta
    # sonu uretmez (loader'in gercek veri icin yaptigiyla ayni normalizasyon).
    raw = pd.bdate_range("2024-01-02", periods=N, tz="America/New_York")
    return pd.DatetimeIndex([to_market_date(t) for t in raw])


CAL = _calendar()
RAW = pd.bdate_range("2024-01-02", periods=N, tz="America/New_York")  # event girisleri

A = [100.0 + 0.5 * i + 3.0 * math.sin(i / 3.0) for i in range(N)]
B = [50.0 + 0.2 * i + 2.0 * math.cos(i / 4.0) for i in range(N)]
SPY = [400.0 + 1.0 * i for i in range(N)]


def _frame(prices: list[float]) -> pd.DataFrame:
    return pd.DataFrame({"close": prices, "adj_close": prices}, index=CAL)


FRAMES = {"A": _frame(A), "B": _frame(B), "SPY": _frame(SPY)}


def _events() -> list[Event]:
    pid = "actual"
    return [
        Event(pid, EventType.DEPOSIT, RAW[0], cash=10_000.0),
        Event(pid, EventType.BUY, RAW[1], ticker="A", quantity=30.0, price=A[1], fees=2.0),
        Event(pid, EventType.BUY, RAW[1], ticker="B", quantity=50.0, price=B[1], fees=2.0),
        Event(pid, EventType.DIVIDEND, RAW[10], ticker="A", cash=15.0),
        Event(pid, EventType.SELL, RAW[20], ticker="A", quantity=10.0, price=A[20], fees=1.5),
        Event(pid, EventType.WITHDRAW, RAW[25], cash=500.0),
    ]


# ------------------------------------------------------------------- checkler
def _check(name: str, ok: bool, detail: str = "") -> None:
    mark = "PASS" if ok else "FAIL"
    print(f"  [{mark}] {name}" + (f"  -- {detail}" if detail else ""))
    if not ok:
        raise AssertionError(f"{name}: {detail}")


def test_determinism(pf: Portfolio) -> None:
    a = pf.replay()
    b = pf.replay()
    _check("replay determinizmi", a.holdings == b.holdings and a.cash == b.cash)


def test_cash_conservation(pf: Portfolio) -> None:
    vs = value_series(pf, FRAMES)
    final_cash = float(vs["cash"].iloc[-1])
    expected = sum(cash_delta(e) for e in pf.events())
    _check("nakit korunumu", abs(final_cash - expected) < TOL,
           f"{final_cash:.6f} vs {expected:.6f}")


def test_share_conservation(pf: Portfolio) -> None:
    st = pf.replay()
    _check("adet korunumu", abs(st.holdings["A"] - 20.0) < TOL and abs(st.holdings["B"] - 50.0) < TOL,
           f"A={st.holdings['A']} B={st.holdings['B']}")


def test_accounting_identity(pf: Portfolio) -> None:
    vs = value_series(pf, FRAMES)
    total = float(vs["total_value"].iloc[-1])

    ev = pf.events()
    contributions = sum(e.cash for e in ev if e.type is EventType.DEPOSIT) \
        - sum(e.cash for e in ev if e.type is EventType.WITHDRAW)
    dividends = sum(e.cash for e in ev if e.type is EventType.DIVIDEND)
    fees = sum(e.fees for e in ev)
    buys_cost = sum(e.quantity * e.price for e in ev if e.type is EventType.BUY)
    sells_proceeds = sum(e.quantity * e.price for e in ev if e.type is EventType.SELL)

    d = CAL[-1]
    market_value = 20.0 * float(FRAMES["A"].at[d, "adj_close"]) \
        + 50.0 * float(FRAMES["B"].at[d, "adj_close"])
    invest_pnl = market_value + sells_proceeds - buys_cost
    expected_total = contributions + dividends + invest_pnl - fees

    _check("muhasebe kimligi", abs(total - expected_total) < TOL,
           f"{total:.9f} vs {expected_total:.9f}")


def test_fees_reduce_value() -> None:
    dep = Event("fee", EventType.DEPOSIT, RAW[0], cash=10_000.0)
    dep0 = Event("nofee", EventType.DEPOSIT, RAW[0], cash=10_000.0)
    buy_fee = make_buy("fee", "A", 30.0, A[1], RAW[1])  # varsayilan fee/slippage
    buy_nofee = make_buy("nofee", "A", 30.0, A[1], RAW[1],
                         slippage_bps=0.0, commission_bps=0.0, commission_flat=0.0)

    pf_fee = Portfolio("fee", [dep, buy_fee])
    pf_nofee = Portfolio("nofee", [dep0, buy_nofee])
    v_fee = float(value_series(pf_fee, FRAMES)["total_value"].iloc[-1])
    v_nofee = float(value_series(pf_nofee, FRAMES)["total_value"].iloc[-1])

    _check("fee'li < fee'siz", v_fee < v_nofee - TOL, f"{v_fee:.4f} < {v_nofee:.4f}")


def test_benchmark(pf: Portfolio) -> None:
    bench_events = buy_and_hold_from_flows(pf, "SPY", FRAMES, portfolio_id="benchmark")
    bench = Portfolio("benchmark", bench_events)
    vs = value_series(bench, FRAMES)
    total = float(vs["total_value"].iloc[-1])

    # bagimsiz yeniden hesap: net SPY adedi = alis - satis (WITHDRAW satis uretir)
    buys = [e for e in bench_events if e.type is EventType.BUY]
    _check("benchmark BUY uretildi", len(buys) >= 1)
    qty = sum(e.quantity for e in buys) \
        - sum(e.quantity for e in bench_events if e.type is EventType.SELL)
    d = CAL[-1]
    cash = sum(cash_delta(e) for e in bench_events)
    expected = cash + qty * float(FRAMES["SPY"].at[d, "adj_close"])
    _check("benchmark buy-and-hold", abs(total - expected) < TOL and total > 0,
           f"{total:.6f} vs {expected:.6f}")


def test_no_weekend_valuation(pf: Portfolio) -> None:
    vs = value_series(pf, FRAMES)
    weekend = [d for d in vs.index if d.weekday() >= 5]
    _check("hafta sonu degerleme yok", len(weekend) == 0, f"{weekend[:3]}")

    # deger serisi de saglikli olsun (bilesim testine dokunmadan)
    r = daily_returns(vs["total_value"], vs["external_flow"])
    _check("gunluk getiri hesaplandi", len(r) > 0 and r.notna().all())


def main() -> int:
    print("smoke_portfolio -- agsiz muhasebe dogrulamasi")
    pf = Portfolio("actual", _events())
    test_determinism(pf)
    test_cash_conservation(pf)
    test_share_conservation(pf)
    test_accounting_identity(pf)
    test_fees_reduce_value()
    test_benchmark(pf)
    test_no_weekend_valuation(pf)
    print("TUMU GECTI")
    return 0


if __name__ == "__main__":
    sys.exit(main())
