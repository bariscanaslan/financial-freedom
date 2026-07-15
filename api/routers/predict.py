"""
POST /predict -- model/predict.py'yi cagirir, FAZLASI YOK.

A1: predict() sinirina dokunulmaz. recent_df loader'dan gelir, predict()'e
verilir, Forecast JSON'a cevrilir. Burada scaler fit'i, dataset kurulumu veya
yeniden olcekleme YOKTUR.
A2: model meta (skill_score, coverage) yanitla birlikte doner.
A3: p10/p50/p90 her zaman BIRLIKTE.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends

from api.deps import get_db, get_model_cache, get_price_provider
from api.errors import BadRequest
from api.schemas import ForecastResponse, ModelMeta, ModelsResponse, PredictRequest
from api.services.model_cache import ModelCache
from api.services.price_provider import PriceProvider

router = APIRouter(tags=["predict"])


def build_forecast(ticker: str, cache, prices, db) -> ForecastResponse:
    from model.predict import predict as run_predict

    model = cache.get(ticker)
    recent_df = prices.recent(ticker)
    try:
        fc = run_predict(model, recent_df, ticker=ticker)
    except ValueError as e:
        raise BadRequest(str(e))

    db.record_ticker(ticker)
    d = fc.to_dict()
    meta = cache.meta(ticker)
    tm = meta.get("test_metrics") or {}
    return ForecastResponse(
        ticker=d["ticker"], as_of=d["as_of"], anchor_price=d["anchor_price"],
        quantiles=d["quantiles"], returns=d["returns"], prices=d["prices"],
        uncertainty=d["uncertainty"], uncertainty_pct=d["uncertainty_pct"],
        periods=d["periods"],
        meta=ModelMeta(
            ticker=meta.get("ticker"), saved_at=meta.get("saved_at"),
            skill_score=tm.get("skill_score"), coverage=tm.get("coverage"),
            nominal_cov=tm.get("nominal_cov"), git_commit=meta.get("git_commit"),
        ),
    )


@router.get("/models", response_model=ModelsResponse)
def list_models(cache: ModelCache = Depends(get_model_cache)) -> ModelsResponse:
    rows = cache.summaries()
    return ModelsResponse(count=len(rows), models=rows)


@router.post("/predict", response_model=ForecastResponse)
def predict_endpoint(
    req: PredictRequest,
    cache: ModelCache = Depends(get_model_cache),
    prices: PriceProvider = Depends(get_price_provider),
    db=Depends(get_db),
) -> ForecastResponse:
    return build_forecast(req.ticker, cache, prices, db)
