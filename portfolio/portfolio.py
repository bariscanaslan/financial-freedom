"""
Portfolio: event log'u REPLAY ederek herhangi bir tarihte pozisyon + nakit.

FIYATSIZ KATMAN. Burada piyasa fiyati YOKTUR -- yalnizca event'lerden hisse
adedi ve nakit tureti1lir. Mark-to-market valuation.py'de yapilir. Bu ayrim
sayesinde muhasebe (adet/nakit) fiyat mantigindan bagimsiz test edilebilir.

actual ve simulated AYNI siniftir (K2): iki ayri kod yolu yoktur, yalnizca
farkli portfolio_id'li iki ornek. "Yatirim yapsaydim" = simulated bir
Portfolio'nun event log'unu uretip AYNI valuation motorundan gecirmektir.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

import pandas as pd

from .events import Event, EventType, cash_delta
from .store import EventStore

# Kayan nokta artigi bu esigin altindaysa pozisyon kapanmis sayilir.
_ZERO = 1e-9


@dataclass(frozen=True)
class PositionState:
    """Belirli bir andaki portfolyo durumu. Event'lerden turer, saklanmaz."""
    as_of: pd.Timestamp
    holdings: dict[str, float]   # ticker -> hisse adedi (yalnizca acik pozisyonlar)
    cash: float


class Portfolio:
    def __init__(self, portfolio_id: str, events: list[Event]):
        self.portfolio_id = portfolio_id
        # Yalnizca bu portfolyonun event'leri. Ekleme sirasi korunarak zamana
        # gore STABLE siralanir: ayni gunun event'leri ekleme sirasinda kalir.
        mine = [e for e in events if e.portfolio_id == portfolio_id]
        self._events: list[Event] = sorted(mine, key=lambda e: e.timestamp)

    @classmethod
    def from_store(cls, store: EventStore, portfolio_id: str) -> "Portfolio":
        return cls(portfolio_id, store.for_portfolio(portfolio_id))

    # -- meta --
    def events(self) -> list[Event]:
        return list(self._events)

    def tickers(self) -> list[str]:
        seen: dict[str, None] = {}
        for e in self._events:
            if e.ticker is not None and e.type is not EventType.DIVIDEND:
                seen.setdefault(e.ticker, None)
        return list(seen)

    @property
    def first_date(self) -> pd.Timestamp | None:
        return self._events[0].timestamp if self._events else None

    @property
    def last_date(self) -> pd.Timestamp | None:
        return self._events[-1].timestamp if self._events else None

    # -- replay --
    def replay(self, as_of: pd.Timestamp | None = None) -> PositionState:
        """
        as_of (dahil) tarihine kadar tum event'leri uygulayarak durumu kurar.
        as_of None ise tum event'ler uygulanir.

        Ayni log her zaman ayni durumu verir (determinizm) -- snapshot tutulmaz.
        """
        cutoff = pd.Timestamp(as_of) if as_of is not None else None
        holdings: dict[str, float] = defaultdict(float)
        cash = 0.0

        for e in self._events:
            if cutoff is not None and e.timestamp > cutoff:
                break
            cash += cash_delta(e)

            if e.type is EventType.BUY:
                holdings[e.ticker] += e.quantity
            elif e.type is EventType.SELL:
                holdings[e.ticker] -= e.quantity
                if holdings[e.ticker] < -_ZERO:
                    # Acikta satis (short) v1'de desteklenmiyor: sessizce negatif
                    # pozisyon tasimak muhasebeyi bozar, gurultulu patlasin.
                    raise ValueError(
                        f"{self.portfolio_id}: {e.ticker} icin elde olandan fazla "
                        f"satis ({e.timestamp.date()}), kalan {holdings[e.ticker]:.6f}"
                    )
            elif e.type is EventType.SPLIT:
                # v1 valuation adj_close bazli oldugu icin normalde uretilmez;
                # yine de log'a girerse adedi tutarli tut.
                holdings[e.ticker] *= e.quantity
            # DEPOSIT / WITHDRAW / DIVIDEND: yalnizca nakit, adet degismez.

        clean = {t: q for t, q in holdings.items() if abs(q) > _ZERO}
        return PositionState(
            as_of=(cutoff if cutoff is not None else self.last_date),
            holdings=clean,
            cash=cash,
        )
