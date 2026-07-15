"""
Event veri modeli -- portfolyonun TEK gercek kaynagi (K1).

Portfolyo bir durum tablosu (snapshot) olarak DEGIL, degismez bir OLAY KAYDI
olarak saklanir. Herhangi bir andaki durum her zaman event'lerden yeniden
hesaplanir (portfolio.replay). Snapshot bozulunca sessizce yanlis kalir;
event log denetlenebilir ve yeniden uretilebilir.

NAKIT ETKISI TEK YERDE: cash_delta(). Ikinci bir yerde nakit hesabi YOK --
sessiz muhasebe hatalarinin en sik kaynagi budur.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

import pandas as pd

from data.calendar import to_market_date


class EventType(str, Enum):
    BUY = "BUY"           # ticker, quantity>0, price (fill), fees
    SELL = "SELL"         # ticker, quantity>0, price (fill), fees
    DEPOSIT = "DEPOSIT"   # cash>0 -- dis para girisi
    WITHDRAW = "WITHDRAW" # cash>0 -- dis para cikisi
    DIVIDEND = "DIVIDEND" # ticker, cash>0 -- yatirim getirisi (DIS AKIS DEGIL)
    # K6: v1 valuation adj_close bazlidir; SPLIT event'i URETILMEZ ve
    # degerlemede KULLANILMAZ. Sema butunlugu ve ileride ham-close yolu icin
    # taniml kalir. quantity = bolunme orani (2:1 icin 2.0).
    SPLIT = "SPLIT"


_TRADE = {EventType.BUY, EventType.SELL}
_CASH = {EventType.DEPOSIT, EventType.WITHDRAW}


@dataclass(frozen=True)
class Event:
    """
    Degismez tek islem kaydi. frozen: bir kez yazilan event degistirilemez;
    duzeltme = ters yonlu YENI event (store.py, K1).
    """

    portfolio_id: str
    type: EventType
    timestamp: pd.Timestamp     # borsa gunune normalize edilir (to_market_date)
    ticker: str | None = None
    quantity: float = 0.0       # hisse adedi (BUY/SELL), oran (SPLIT)
    price: float = 0.0          # gerceklesen birim fill fiyati
    cash: float = 0.0           # DEPOSIT/WITHDRAW/DIVIDEND icin acik nakit tutari
    fees: float = 0.0           # komisyon + slippage maliyeti, para cinsinden
    note: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "type", EventType(self.type))
        object.__setattr__(self, "timestamp", to_market_date(self.timestamp))
        if self.ticker is not None:
            object.__setattr__(self, "ticker", str(self.ticker).upper())

        t = self.type
        if t in _TRADE:
            if not self.ticker:
                raise ValueError(f"{t}: ticker required")
            if self.quantity <= 0:
                raise ValueError(f"{t}: quantity must be > 0 ({self.quantity})")
            if self.price < 0:
                raise ValueError(f"{t}: price cannot be negative ({self.price})")
            if self.fees < 0:
                raise ValueError(f"{t}: fees cannot be negative ({self.fees})")
        elif t in _CASH:
            if self.cash <= 0:
                raise ValueError(f"{t}: cash must be > 0 ({self.cash})")
        elif t is EventType.DIVIDEND:
            if not self.ticker:
                raise ValueError("DIVIDEND: ticker required")
            if self.cash <= 0:
                raise ValueError(f"DIVIDEND: cash must be > 0 ({self.cash})")
        elif t is EventType.SPLIT:
            if not self.ticker:
                raise ValueError("SPLIT: ticker required")
            if self.quantity <= 0:
                raise ValueError(f"SPLIT: ratio must be > 0 ({self.quantity})")

    # -- serilestirme (parquet/json) --
    def to_row(self) -> dict:
        return {
            "portfolio_id": self.portfolio_id,
            "type": self.type.value,
            "timestamp": pd.Timestamp(self.timestamp),
            "ticker": self.ticker,
            "quantity": float(self.quantity),
            "price": float(self.price),
            "cash": float(self.cash),
            "fees": float(self.fees),
            "note": self.note,
        }

    @classmethod
    def from_row(cls, row: dict) -> "Event":
        tk = row.get("ticker")
        if tk is not None and (isinstance(tk, float) and pd.isna(tk)):
            tk = None
        return cls(
            portfolio_id=str(row["portfolio_id"]),
            type=EventType(row["type"]),
            timestamp=pd.Timestamp(row["timestamp"]),
            ticker=(None if tk is None else str(tk)),
            quantity=float(row.get("quantity", 0.0) or 0.0),
            price=float(row.get("price", 0.0) or 0.0),
            cash=float(row.get("cash", 0.0) or 0.0),
            fees=float(row.get("fees", 0.0) or 0.0),
            note=str(row.get("note", "") or ""),
        )


# --------------------------------------------------------------- muhasebe
def cash_delta(e: Event) -> float:
    """
    Bir event'in nakit bakiyesine etkisi. TEK GERCEK KAYNAK -- baska yerde
    nakit hesabi yapilmaz.
    """
    t = e.type
    if t is EventType.BUY:
        return -(e.quantity * e.price + e.fees)
    if t is EventType.SELL:
        return +(e.quantity * e.price - e.fees)
    if t is EventType.DEPOSIT or t is EventType.DIVIDEND:
        return +e.cash
    if t is EventType.WITHDRAW:
        return -e.cash
    if t is EventType.SPLIT:
        return 0.0
    raise ValueError(f"bilinmeyen event tipi: {t}")


def external_flow(e: Event) -> float:
    """
    DIS para akisi (TWR icin). DEPOSIT (+), WITHDRAW (-).
    DIVIDEND dis akis DEGILDIR -- yatirim getirisidir, TWR'ye dahil edilir (K7).
    """
    if e.type is EventType.DEPOSIT:
        return +e.cash
    if e.type is EventType.WITHDRAW:
        return -e.cash
    return 0.0
