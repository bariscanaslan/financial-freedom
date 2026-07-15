"""
FastAPI bagimliliklari: paylasilan servislere erisim ve portfolio_id sinirI.

Butun servis erisimi Depends(...) uzerinden yapilir; boylece testler
app.dependency_overrides ile bunlari sahte/temp orneklerle degistirebilir
(smoke AGSIZ kosar).

PORTFOLIO_ID IZOLASYONU: her portfolyo erisimi valid_portfolio_id'den gecer
ve alt katmanda YALNIZCA store.for_portfolio(id) ile okunur. Bir id baskasinin
event'ini goremez. v1'de auth yok; auth eklenince tam BURAYA girer.
"""
from __future__ import annotations

import re

from fastapi import Depends, Request

from .config import Settings, get_settings
from .errors import BadRequest, NotFound
from .services.db import Database
from .services.model_cache import ModelCache
from .services.price_provider import PriceProvider
from .services.training import TrainingManager
from .services.portfolio_drafts import PortfolioDraftManager

_PID_RE = re.compile(r"^[A-Za-z0-9_\-]{1,64}$")


def settings_dep() -> Settings:
    return get_settings()


def get_model_cache(request: Request) -> ModelCache:
    return request.app.state.model_cache


def get_price_provider(request: Request) -> PriceProvider:
    return request.app.state.price_provider


def get_db(request: Request) -> Database:
    return request.app.state.db


def get_training_manager(request: Request) -> TrainingManager:
    return request.app.state.training_manager


def get_portfolio_draft_manager(request: Request) -> PortfolioDraftManager:
    return request.app.state.portfolio_draft_manager


def valid_portfolio_id(portfolio_id: str) -> str:
    """Path'teki portfolio_id'yi dogrular. Izolasyonun giris kapisi."""
    if not _PID_RE.match(portfolio_id):
        raise BadRequest("invalid portfolio_id (allowed: letters/digits/_/-, 1-64)")
    return portfolio_id


def require_portfolio(
    portfolio_id: str = Depends(valid_portfolio_id),
    db: Database = Depends(get_db),
) -> str:
    """valid_portfolio_id + registry check. Unknown id -> 404."""
    if db.get_portfolio(portfolio_id) is None:
        raise NotFound(f"portfolio not found: {portfolio_id}")
    return portfolio_id
