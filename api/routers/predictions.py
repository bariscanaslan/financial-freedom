"""Tahmin anlık görüntülerini kaydetme ve listeleme uçları."""
from fastapi import APIRouter, Depends

from api.deps import get_db, get_model_cache, get_price_provider
from api.errors import NotFound
from api.routers.predict import build_forecast
from api.schemas import (
    PredictRequest,
    SavedPredictionResponse,
    SavedPredictionsResponse,
)

router = APIRouter(prefix="/predictions", tags=["predictions"])


@router.post("", response_model=SavedPredictionResponse)
def save_prediction(
    body: PredictRequest,
    cache=Depends(get_model_cache),
    prices=Depends(get_price_provider),
    db=Depends(get_db),
) -> SavedPredictionResponse:
    forecast = build_forecast(body.ticker, cache, prices, db)
    row = db.save_prediction(body.ticker, forecast.as_of, forecast.model_dump())
    return SavedPredictionResponse(**row)


@router.get("", response_model=SavedPredictionsResponse)
def list_predictions(db=Depends(get_db)) -> SavedPredictionsResponse:
    rows = [SavedPredictionResponse(**row) for row in db.list_predictions()]
    return SavedPredictionsResponse(count=len(rows), predictions=rows)


@router.get("/{prediction_id}", response_model=SavedPredictionResponse)
def get_prediction(prediction_id: str, db=Depends(get_db)) -> SavedPredictionResponse:
    row = db.get_prediction(prediction_id)
    if row is None:
        raise NotFound("Tahmin kaydı bulunamadı.")
    return SavedPredictionResponse(**row)


@router.delete("/{prediction_id}")
def delete_prediction(prediction_id: str, db=Depends(get_db)) -> dict:
    if not db.delete_prediction(prediction_id):
        raise NotFound("Tahmin kaydı bulunamadı.")
    return {"id": prediction_id, "deleted": True}
