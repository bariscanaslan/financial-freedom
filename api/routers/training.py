"""Model eğitimini başlatma ve canlı durumunu izleme uçları."""
from fastapi import APIRouter, Depends

from api.deps import get_training_manager
from api.schemas import (
    TrainingCatalogResponse,
    TrainingDeviceResponse,
    TrainingJobResponse,
    TrainingRequest,
    TrainingTicker,
)
from api.deps import get_model_cache
from api.services.nasdaq_catalog import NASDAQ_100
from api.services.training import TrainingManager

router = APIRouter(prefix="/training", tags=["training"])


@router.get("/catalog", response_model=TrainingCatalogResponse)
def training_catalog(cache=Depends(get_model_cache)) -> TrainingCatalogResponse:
    latest = {}
    for model in cache.summaries():
        ticker = model.get("ticker")
        if ticker and ticker not in latest:
            latest[ticker] = model.get("saved_at")
    rows = [TrainingTicker(ticker=ticker, name=name, has_model=ticker in latest,
                           last_trained_at=latest.get(ticker))
            for ticker, name in NASDAQ_100]
    return TrainingCatalogResponse(as_of="2026-07", count=len(rows), tickers=rows)


@router.get("/device", response_model=TrainingDeviceResponse)
def training_device(
    manager: TrainingManager = Depends(get_training_manager),
) -> TrainingDeviceResponse:
    return TrainingDeviceResponse(device=manager.device())


@router.post("", response_model=TrainingJobResponse)
def start_training(
    body: TrainingRequest,
    manager: TrainingManager = Depends(get_training_manager),
) -> TrainingJobResponse:
    return TrainingJobResponse(**manager.start(body.ticker, body.horizon))


@router.get("/{job_id}", response_model=TrainingJobResponse)
def training_status(
    job_id: str,
    manager: TrainingManager = Depends(get_training_manager),
) -> TrainingJobResponse:
    return TrainingJobResponse(**manager.get(job_id))
