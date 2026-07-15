"""GET /health -- ayakta mi, hangi cihaz, yuklu modeller."""
from __future__ import annotations

from fastapi import APIRouter, Depends

from api.config import Settings, get_settings
from api.deps import get_model_cache, get_redis_backend, settings_dep
from api.services.model_cache import ModelCache
from api.services.redis_backend import RedisBackend

router = APIRouter(tags=["health"])


@router.get("/health")
def health(
    cache: ModelCache = Depends(get_model_cache),
    redis: RedisBackend = Depends(get_redis_backend),
    settings: Settings = Depends(settings_dep),
) -> dict:
    # Cihaz cozumu import aninda DEGIL, istek aninda (guide §5).
    from model.device import best_device
    device = settings.device or best_device().spec
    return {
        "status": "ok",
        "device": device,
        "loaded_models": len(cache.loaded_tickers()),
        "redis": "connected" if redis.enabled else "fallback",
    }
