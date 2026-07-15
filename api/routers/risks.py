"""Portföy risk anlık görüntülerini kaydetme ve listeleme."""
from fastapi import APIRouter, Depends

from api.deps import get_db, get_model_cache, get_price_provider, require_portfolio
from api.routers.portfolio import build_portfolio_forecast
from api.schemas import RiskSaveRequest, SavedRiskResponse, SavedRisksResponse
from api.errors import NotFound

router = APIRouter(prefix="/risks", tags=["risks"])


@router.post("", response_model=SavedRiskResponse)
def save_risk(body: RiskSaveRequest, db=Depends(get_db), cache=Depends(get_model_cache),
              prices=Depends(get_price_provider)) -> SavedRiskResponse:
    # Registry kontrolü path dependency dışında açıkça uygulanır.
    if db.get_portfolio(body.portfolio_id) is None:
        from api.errors import NotFound
        raise NotFound("Portföy bulunamadı.")
    risk = build_portfolio_forecast(body.portfolio_id, db, cache, prices)
    return SavedRiskResponse(**db.save_risk(body.portfolio_id, risk.model_dump()))


@router.get("", response_model=SavedRisksResponse)
def list_risks(db=Depends(get_db)) -> SavedRisksResponse:
    rows = [SavedRiskResponse(**row) for row in db.list_risks()]
    return SavedRisksResponse(count=len(rows), risks=rows)


@router.get("/{risk_id}", response_model=SavedRiskResponse)
def get_risk(risk_id: str, db=Depends(get_db)) -> SavedRiskResponse:
    row = db.get_risk(risk_id)
    if row is None:
        raise NotFound("Risk kaydı bulunamadı.")
    return SavedRiskResponse(**row)


@router.delete("/{risk_id}")
def delete_risk(risk_id: str, db=Depends(get_db)) -> dict:
    if not db.delete_risk(risk_id):
        raise NotFound("Risk kaydı bulunamadı.")
    return {"id": risk_id, "deleted": True}
