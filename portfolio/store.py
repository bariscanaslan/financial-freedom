"""
EventStore: append-only event log + parquet kaliciligi.

SILME YOK. Bir islemi geri almak = ters yonlu YENI event yazmak (K1'in
"hard delete yok" ruhu). Boylece log her zaman ne olduysa onu anlatir; gecmis
yeniden yazilmaz, denetlenebilirlik korunur.

Kalicilik parquet: dtype ve timestamp bilgisini kaybetmez (CSV kaybeder).
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from .config import EVENT_LOG_DIR
from .events import Event

_COLUMNS = [
    "portfolio_id", "type", "timestamp",
    "ticker", "quantity", "price", "cash", "fees", "note",
]


class EventStore:
    """
    Event'lerin append-only koleksiyonu. Ekleme sirasi korunur; ayni gune
    dusen event'lerin gorulme sirasi bu ekleme sirasidir (replay stable sort).
    """

    def __init__(self, events: list[Event] | None = None):
        self._events: list[Event] = list(events or [])

    # -- yazma (yalnizca ekleme) --
    def append(self, event: Event) -> "EventStore":
        self._events.append(event)
        return self

    def extend(self, events: list[Event]) -> "EventStore":
        self._events.extend(events)
        return self

    # -- okuma --
    def __len__(self) -> int:
        return len(self._events)

    def all(self) -> list[Event]:
        return list(self._events)

    def for_portfolio(self, portfolio_id: str) -> list[Event]:
        return [e for e in self._events if e.portfolio_id == portfolio_id]

    def portfolio_ids(self) -> list[str]:
        # ekleme sirasini koruyan benzersiz liste
        seen: dict[str, None] = {}
        for e in self._events:
            seen.setdefault(e.portfolio_id, None)
        return list(seen)

    # -- serilestirme --
    def to_frame(self) -> pd.DataFrame:
        if not self._events:
            return pd.DataFrame(columns=_COLUMNS)
        return pd.DataFrame([e.to_row() for e in self._events])[_COLUMNS]

    @classmethod
    def from_frame(cls, df: pd.DataFrame) -> "EventStore":
        return cls([Event.from_row(row) for row in df.to_dict("records")])

    def save(self, path: str | Path | None = None) -> Path:
        """Event log'u parquet olarak yazar. Dizin gerekirse burada olusur."""
        if path is None:
            EVENT_LOG_DIR.mkdir(parents=True, exist_ok=True)
            path = EVENT_LOG_DIR / "events.parquet"
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        self.to_frame().to_parquet(path)
        return path

    @classmethod
    def load(cls, path: str | Path) -> "EventStore":
        path = Path(path)
        if not path.exists():
            raise FileNotFoundError(f"event log yok: {path}")
        return cls.from_frame(pd.read_parquet(path))
