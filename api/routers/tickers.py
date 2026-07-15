"""
GET /tickers -- tickers the user has run the model on (recorded on /predict).
"""
from __future__ import annotations

from fastapi import APIRouter, Depends

from api.deps import get_db
from api.schemas import TickersResponse, TrackedTicker

router = APIRouter(prefix="/tickers", tags=["tickers"])


@router.get("", response_model=TickersResponse)
def list_tickers(db=Depends(get_db)) -> TickersResponse:
    rows = [TrackedTicker(**t) for t in db.list_tickers()]
    return TickersResponse(count=len(rows), tickers=rows)
