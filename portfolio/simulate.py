"""
"Yatirim yapsaydim" senaryolari: alternatif event log uretir ve AYNI valuation
motorundan gecirir (K2). Kiyas ancak ikisi bit-bit ayni motordan gecerse adildir.

K3: fee/slippage ZORUNLU. make_buy/make_sell fill fiyatini kaydirir ve komisyon
ekler. Fee'ler tamamen kapatilirsa (tum bps + flat = 0) simulasyon SISTEMATIK
olarak iyimser cikar; bu durumda gurultulu bir uyari basilir (susturulamaz
sekilde loglanir).
"""
from __future__ import annotations

import logging

import pandas as pd

from .config import (
    DEFAULT_COMMISSION_BPS,
    DEFAULT_COMMISSION_FLAT,
    DEFAULT_SLIPPAGE_BPS,
    PRICE_COL,
)
from .events import Event, EventType, external_flow
from .portfolio import Portfolio

log = logging.getLogger(__name__)

_BPS = 1e-4


def _warn_if_frictionless(slippage_bps: float, commission_bps: float, commission_flat: float) -> None:
    if slippage_bps == 0.0 and commission_bps == 0.0 and commission_flat == 0.0:
        log.warning(
            "SIMULATION RUNNING WITHOUT FEES (slippage=commission=0). The result "
            "is SYSTEMATICALLY OPTIMISTIC and overstates the real return (K3)."
        )


def fill_price(ref_price: float, side: EventType, slippage_bps: float) -> float:
    """Slippage'li gerceklesme fiyati: BUY yukari, SELL asagi kayar."""
    slip = slippage_bps * _BPS
    if side is EventType.BUY:
        return ref_price * (1.0 + slip)
    if side is EventType.SELL:
        return ref_price * (1.0 - slip)
    raise ValueError(f"fill_price yalnizca BUY/SELL: {side}")


def commission(notional: float, commission_bps: float, commission_flat: float) -> float:
    return abs(notional) * commission_bps * _BPS + commission_flat


def make_buy(
    portfolio_id: str,
    ticker: str,
    quantity: float,
    ref_price: float,
    timestamp,
    *,
    slippage_bps: float = DEFAULT_SLIPPAGE_BPS,
    commission_bps: float = DEFAULT_COMMISSION_BPS,
    commission_flat: float = DEFAULT_COMMISSION_FLAT,
    note: str = "",
) -> Event:
    _warn_if_frictionless(slippage_bps, commission_bps, commission_flat)
    fp = fill_price(ref_price, EventType.BUY, slippage_bps)
    fee = commission(quantity * fp, commission_bps, commission_flat)
    return Event(portfolio_id, EventType.BUY, timestamp, ticker=ticker,
                 quantity=quantity, price=fp, fees=fee, note=note)


def make_sell(
    portfolio_id: str,
    ticker: str,
    quantity: float,
    ref_price: float,
    timestamp,
    *,
    slippage_bps: float = DEFAULT_SLIPPAGE_BPS,
    commission_bps: float = DEFAULT_COMMISSION_BPS,
    commission_flat: float = DEFAULT_COMMISSION_FLAT,
    note: str = "",
) -> Event:
    _warn_if_frictionless(slippage_bps, commission_bps, commission_flat)
    fp = fill_price(ref_price, EventType.SELL, slippage_bps)
    fee = commission(quantity * fp, commission_bps, commission_flat)
    return Event(portfolio_id, EventType.SELL, timestamp, ticker=ticker,
                 quantity=quantity, price=fp, fees=fee, note=note)


def invest_cash(
    portfolio_id: str,
    ticker: str,
    cash: float,
    ref_price: float,
    timestamp,
    *,
    slippage_bps: float = DEFAULT_SLIPPAGE_BPS,
    commission_bps: float = DEFAULT_COMMISSION_BPS,
    commission_flat: float = DEFAULT_COMMISSION_FLAT,
    note: str = "",
) -> Event | None:
    """
    Elde 'cash' kadar para varken tamamini ticker'a yatir. Adet, komisyon dahil
    toplam maliyet cash'i asmayacak sekilde coozulur:
        qty*fill*(1+cb) + flat = cash  =>  qty = (cash - flat) / (fill*(1+cb))
    Yetersiz para (qty <= 0) ise None doner.
    """
    fp = fill_price(ref_price, EventType.BUY, slippage_bps)
    denom = fp * (1.0 + commission_bps * _BPS)
    qty = (cash - commission_flat) / denom if denom > 0 else 0.0
    if qty <= 0:
        return None
    return make_buy(portfolio_id, ticker, qty, ref_price, timestamp,
                    slippage_bps=slippage_bps, commission_bps=commission_bps,
                    commission_flat=commission_flat, note=note)


def _price_asof(price: pd.Series, day: pd.Timestamp) -> tuple[pd.Timestamp, float] | None:
    """day tarihindeki ya da ondan sonraki ilk islem gununun fiyati."""
    fut = price.loc[price.index >= day].dropna()
    if fut.empty:
        return None
    return fut.index[0], float(fut.iloc[0])


def buy_and_hold_from_flows(
    source: Portfolio,
    target_ticker: str,
    price_frames: dict[str, pd.DataFrame],
    *,
    portfolio_id: str = "benchmark",
    price_col: str = PRICE_COL,
    slippage_bps: float = DEFAULT_SLIPPAGE_BPS,
    commission_bps: float = DEFAULT_COMMISSION_BPS,
    commission_flat: float = DEFAULT_COMMISSION_FLAT,
) -> list[Event]:
    """
    "Ayni parayi hep target_ticker'a koysaydim" senaryosu (K4 benchmark).

    source portfolyonun DIS akislarini (DEPOSIT/WITHDRAW) alir:
      - DEPOSIT  -> ayni tutari yatir + o gunku fiyattan target al
      - WITHDRAW -> parayi karsilamak icin yeterli target sat + WITHDRAW
    Ayni fee modelinden gecer; boylece actual ile adil kiyaslanir.
    """
    if target_ticker not in price_frames:
        raise ValueError(f"no benchmark price: {target_ticker}")
    price = price_frames[target_ticker][price_col].dropna()

    fee_kw = dict(slippage_bps=slippage_bps, commission_bps=commission_bps,
                  commission_flat=commission_flat)

    events: list[Event] = []
    shares = 0.0
    for e in source.events():
        flow = external_flow(e)
        if flow == 0.0:
            continue
        hit = _price_asof(price, e.timestamp)
        if hit is None:
            continue
        day, p = hit
        if flow > 0:  # DEPOSIT
            events.append(Event(portfolio_id, EventType.DEPOSIT, day, cash=flow))
            buy = invest_cash(portfolio_id, target_ticker, flow, p, day, **fee_kw,
                              note="benchmark deposit")
            if buy is not None:
                events.append(buy)
                shares += buy.quantity
        else:  # WITHDRAW
            need = -flow
            fp = fill_price(p, EventType.SELL, slippage_bps)
            qty = min(shares, need / fp) if fp > 0 else 0.0
            if qty > 0:
                sell = make_sell(portfolio_id, target_ticker, qty, p, day, **fee_kw,
                                 note="benchmark withdraw")
                events.append(sell)
                shares -= qty
            events.append(Event(portfolio_id, EventType.WITHDRAW, day, cash=need))
    return events
