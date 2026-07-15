"""
Lightweight SQLite persistence for the app: portfolio registry, event log, and
the tickers the user has run the model on.

The event-sourced compute engine (portfolio/) is unchanged: this layer only
stores events and hands back plain list[Event] for replay/valuation. SQLite
lives here in api/ so the portfolio accounting core stays persistence- and
torch-agnostic.

Single-user, local. No auth. A threading.Lock serializes access because
FastAPI runs sync endpoints in a threadpool over one shared connection.
"""
from __future__ import annotations

import sqlite3
import threading
import uuid
import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from portfolio.events import Event, EventType

_SCHEMA = """
CREATE TABLE IF NOT EXISTS portfolios (
    id            TEXT PRIMARY KEY,
    name          TEXT NOT NULL,
    kind          TEXT NOT NULL CHECK (kind IN ('actual','simulated')),
    base_currency TEXT NOT NULL DEFAULT 'USD',
    created_at    TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS events (
    seq          INTEGER PRIMARY KEY AUTOINCREMENT,
    portfolio_id TEXT NOT NULL REFERENCES portfolios(id) ON DELETE CASCADE,
    type         TEXT NOT NULL,
    timestamp    TEXT NOT NULL,
    ticker       TEXT,
    quantity     REAL NOT NULL DEFAULT 0,
    price        REAL NOT NULL DEFAULT 0,
    cash         REAL NOT NULL DEFAULT 0,
    fees         REAL NOT NULL DEFAULT 0,
    note         TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_events_pid ON events(portfolio_id, seq);
CREATE TABLE IF NOT EXISTS tracked_tickers (
    ticker     TEXT PRIMARY KEY,
    first_used TEXT NOT NULL,
    last_used  TEXT NOT NULL,
    use_count  INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS saved_predictions (
    id         TEXT PRIMARY KEY,
    ticker     TEXT NOT NULL,
    as_of      TEXT NOT NULL,
    created_at TEXT NOT NULL,
    payload    TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_predictions_created
ON saved_predictions(created_at DESC);
CREATE TABLE IF NOT EXISTS saved_risks (
    id           TEXT PRIMARY KEY,
    portfolio_id TEXT NOT NULL,
    created_at   TEXT NOT NULL,
    payload      TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS portfolio_drafts (
    id         TEXT PRIMARY KEY,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    payload    TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS portfolio_evaluations (
    id           TEXT PRIMARY KEY,
    portfolio_id TEXT NOT NULL REFERENCES portfolios(id) ON DELETE CASCADE,
    created_at   TEXT NOT NULL,
    payload      TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_portfolio_evaluations_pid ON portfolio_evaluations(portfolio_id);
"""

_KINDS = ("actual", "simulated")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class Database:
    def __init__(self, path: str | Path):
        self._path = Path(path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(str(self._path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode = WAL")
        self._conn.execute("PRAGMA foreign_keys = ON")
        with self._lock:
            self._conn.executescript(_SCHEMA)
            self._conn.commit()

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    # ------------------------------------------------------------- registry
    def create_portfolio(self, name: str, kind: str, *, base_currency: str = "USD") -> dict:
        if kind not in _KINDS:
            raise ValueError(f"invalid kind: {kind}")
        pid = f"{kind[:3]}_{uuid.uuid4().hex[:12]}"
        created_at = _now()
        with self._lock:
            self._conn.execute(
                "INSERT INTO portfolios (id, name, kind, base_currency, created_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (pid, name, kind, base_currency, created_at),
            )
            self._conn.commit()
        return {"id": pid, "name": name, "kind": kind,
                "base_currency": base_currency, "created_at": created_at}

    def list_portfolios(self) -> list[dict]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT id, name, kind, base_currency, created_at "
                "FROM portfolios ORDER BY created_at ASC"
            ).fetchall()
        return [dict(r) for r in rows]

    def get_portfolio(self, portfolio_id: str) -> dict | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT id, name, kind, base_currency, created_at "
                "FROM portfolios WHERE id = ?",
                (portfolio_id,),
            ).fetchone()
        return dict(row) if row is not None else None

    def delete_portfolio(self, portfolio_id: str) -> bool:
        with self._lock:
            cur = self._conn.execute("DELETE FROM portfolios WHERE id = ?", (portfolio_id,))
            self._conn.commit()
            return cur.rowcount > 0

    # -------------------------------------------------------------- events
    def append_event(self, event: Event) -> None:
        r = event.to_row()
        with self._lock:
            self._conn.execute(
                "INSERT INTO events "
                "(portfolio_id, type, timestamp, ticker, quantity, price, cash, fees, note) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    r["portfolio_id"], r["type"], pd.Timestamp(r["timestamp"]).isoformat(),
                    r["ticker"], r["quantity"], r["price"], r["cash"], r["fees"], r["note"],
                ),
            )
            self._conn.commit()

    def append_events(self, events: list[Event]) -> None:
        for e in events:
            self.append_event(e)

    def events_for(self, portfolio_id: str) -> list[Event]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT portfolio_id, type, timestamp, ticker, quantity, price, cash, fees, note "
                "FROM events WHERE portfolio_id = ? ORDER BY seq ASC",
                (portfolio_id,),
            ).fetchall()
        return [Event.from_row(dict(r)) for r in rows]

    # ------------------------------------------------------- tracked tickers
    def record_ticker(self, ticker: str) -> None:
        ticker = ticker.upper()
        now = _now()
        with self._lock:
            self._conn.execute(
                "INSERT INTO tracked_tickers (ticker, first_used, last_used, use_count) "
                "VALUES (?, ?, ?, 1) "
                "ON CONFLICT(ticker) DO UPDATE SET "
                "last_used = excluded.last_used, use_count = use_count + 1",
                (ticker, now, now),
            )
            self._conn.commit()

    def list_tickers(self) -> list[dict]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT ticker, first_used, last_used, use_count "
                "FROM tracked_tickers ORDER BY last_used DESC"
            ).fetchall()
        return [dict(r) for r in rows]

    # ------------------------------------------------------ predictions
    def save_prediction(self, ticker: str, as_of: str, forecast: dict) -> dict:
        prediction_id = f"pred_{uuid.uuid4().hex[:16]}"
        created_at = _now()
        with self._lock:
            self._conn.execute(
                "INSERT INTO saved_predictions (id, ticker, as_of, created_at, payload) "
                "VALUES (?, ?, ?, ?, ?)",
                (prediction_id, ticker.upper(), as_of, created_at,
                 json.dumps(forecast, ensure_ascii=False)),
            )
            self._conn.commit()
        return {
            "id": prediction_id, "ticker": ticker.upper(), "as_of": as_of,
            "created_at": created_at, "forecast": forecast,
        }

    def list_predictions(self) -> list[dict]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT id, ticker, as_of, created_at, payload "
                "FROM saved_predictions ORDER BY created_at DESC"
            ).fetchall()
        return [
            {
                "id": row["id"], "ticker": row["ticker"], "as_of": row["as_of"],
                "created_at": row["created_at"], "forecast": json.loads(row["payload"]),
            }
            for row in rows
        ]

    def get_prediction(self, prediction_id: str) -> dict | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT id, ticker, as_of, created_at, payload "
                "FROM saved_predictions WHERE id = ?", (prediction_id,),
            ).fetchone()
        if row is None:
            return None
        return {
            "id": row["id"], "ticker": row["ticker"], "as_of": row["as_of"],
            "created_at": row["created_at"], "forecast": json.loads(row["payload"]),
        }

    def delete_prediction(self, prediction_id: str) -> bool:
        with self._lock:
            cur = self._conn.execute(
                "DELETE FROM saved_predictions WHERE id = ?", (prediction_id,)
            )
            self._conn.commit()
        return cur.rowcount > 0

    # -------------------------------------------------------------- risks
    def save_risk(self, portfolio_id: str, risk: dict) -> dict:
        risk_id = f"risk_{uuid.uuid4().hex[:16]}"
        created_at = _now()
        with self._lock:
            self._conn.execute(
                "INSERT INTO saved_risks (id, portfolio_id, created_at, payload) VALUES (?, ?, ?, ?)",
                (risk_id, portfolio_id, created_at, json.dumps(risk, ensure_ascii=False)),
            )
            self._conn.commit()
        return {"id": risk_id, "portfolio_id": portfolio_id,
                "created_at": created_at, "risk": risk}

    def list_risks(self) -> list[dict]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT id, portfolio_id, created_at, payload FROM saved_risks ORDER BY created_at DESC"
            ).fetchall()
        return [{"id": row["id"], "portfolio_id": row["portfolio_id"],
                 "created_at": row["created_at"], "risk": json.loads(row["payload"])}
                for row in rows]

    def get_risk(self, risk_id: str) -> dict | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT id, portfolio_id, created_at, payload FROM saved_risks WHERE id = ?",
                (risk_id,),
            ).fetchone()
        if row is None:
            return None
        return {"id": row["id"], "portfolio_id": row["portfolio_id"],
                "created_at": row["created_at"], "risk": json.loads(row["payload"])}

    def delete_risk(self, risk_id: str) -> bool:
        with self._lock:
            cur = self._conn.execute("DELETE FROM saved_risks WHERE id = ?", (risk_id,))
            self._conn.commit()
        return cur.rowcount > 0

    # ------------------------------------------------------ portfolio drafts
    def save_portfolio_draft(self, payload: dict) -> dict:
        draft_id = f"draft_{uuid.uuid4().hex[:16]}"
        now = _now()
        with self._lock:
            self._conn.execute(
                "INSERT INTO portfolio_drafts (id, created_at, updated_at, payload) VALUES (?, ?, ?, ?)",
                (draft_id, now, now, json.dumps(payload, ensure_ascii=False)),
            )
            self._conn.commit()
        return {"id": draft_id, "created_at": now, "updated_at": now, **payload}

    def get_portfolio_draft(self, draft_id: str) -> dict | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT id, created_at, updated_at, payload FROM portfolio_drafts WHERE id = ?",
                (draft_id,),
            ).fetchone()
        return None if row is None else {"id": row["id"], "created_at": row["created_at"],
            "updated_at": row["updated_at"], **json.loads(row["payload"])}

    def update_portfolio_draft(self, draft_id: str, payload: dict) -> dict | None:
        now = _now()
        with self._lock:
            cur = self._conn.execute(
                "UPDATE portfolio_drafts SET updated_at = ?, payload = ? WHERE id = ?",
                (now, json.dumps(payload, ensure_ascii=False), draft_id),
            )
            self._conn.commit()
        return self.get_portfolio_draft(draft_id) if cur.rowcount else None

    # ------------------------------------------------ portfolio evaluations
    def save_portfolio_evaluation(self, portfolio_id: str, payload: dict) -> dict:
        evaluation_id = f"eval_{uuid.uuid4().hex[:16]}"
        created_at = _now()
        with self._lock:
            self._conn.execute(
                "INSERT INTO portfolio_evaluations (id, portfolio_id, created_at, payload) VALUES (?, ?, ?, ?)",
                (evaluation_id, portfolio_id, created_at, json.dumps(payload, ensure_ascii=False)),
            )
            self._conn.commit()
        return {"id": evaluation_id, "portfolio_id": portfolio_id, "created_at": created_at, **payload}

    def list_portfolio_evaluations(self) -> list[dict]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT id, portfolio_id, created_at, payload FROM portfolio_evaluations ORDER BY created_at DESC"
            ).fetchall()
        return [{"id": row["id"], "portfolio_id": row["portfolio_id"],
                 "created_at": row["created_at"], **json.loads(row["payload"])} for row in rows]

    def get_portfolio_evaluation(self, evaluation_id: str) -> dict | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT id, portfolio_id, created_at, payload FROM portfolio_evaluations WHERE id = ?",
                (evaluation_id,),
            ).fetchone()
        return None if row is None else {"id": row["id"], "portfolio_id": row["portfolio_id"],
            "created_at": row["created_at"], **json.loads(row["payload"])}
