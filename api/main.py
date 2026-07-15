"""
FastAPI uygulamasi.

Import aninda AGIR IS YOK (model yukleme / ag / input). Model cache lazy'dir;
lifespan yalnizca hafif kurulum yapar (bos cache + store). Bu surec stdin'siz
calisir (guide §5) -- import sirasinda soru soran / model yukleyen bir modul
sunucuyu asardi.
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import get_settings
from .errors import install_handlers
from .routers import health, market, notifications, portfolio, portfolio_drafts, portfolio_evaluations, predict, predictions, risks, tickers, training
from .services.db import Database
from .services.model_cache import ModelCache
from .services.price_provider import PriceProvider
from .services.redis_backend import RedisBackend
from .services.training import TrainingManager
from .services.portfolio_drafts import PortfolioDraftManager
from .services.notifications import NotificationService

log = logging.getLogger("api")


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    # Lazy cache -- model burada YUKLENMEZ, ilk /predict'te yuklenir.
    app.state.model_cache = ModelCache(settings.models_dir, device=settings.device)
    app.state.redis = RedisBackend(
        settings.redis_url,
        settings.redis_prefix,
        job_ttl=settings.redis_job_ttl_seconds,
        market_ttl=settings.redis_market_ttl_seconds,
    )
    app.state.price_provider = PriceProvider(app.state.redis)
    app.state.db = Database(settings.db_path)
    app.state.training_manager = TrainingManager(
        settings.models_dir, settings.device, app.state.price_provider, app.state.redis
    )
    app.state.portfolio_draft_manager = PortfolioDraftManager(
        app.state.model_cache, app.state.price_provider, app.state.db, app.state.redis
    )
    app.state.notification_service = NotificationService(
        app.state.db, app.state.price_provider, app.state.redis,
        settings.notification_interval_seconds,
    )

    log.info("api hazir | models_dir=%s | device=%s | db=%s | redis=%s",
             settings.models_dir, settings.device or "(runtime)", settings.db_path,
             "connected" if app.state.redis.enabled else "fallback")
    try:
        yield
    finally:
        app.state.notification_service.close()
        app.state.training_manager.close()
        app.state.portfolio_draft_manager.close()
        app.state.db.close()
        app.state.redis.close()


def create_app() -> FastAPI:
    app = FastAPI(
        title="Stock Price Predictor API",
        version="0.1.0",
        summary="model/ ve portfolio/ katmanlarinin ince HTTP kabugu. "
                "Yatirim tavsiyesi degildir; ciktilar tanimlayicidir.",
        lifespan=lifespan,
    )
    install_handlers(app)
    # CORS: tarayici UI'i icin. Yalnizca bilinen kaynaklar (wildcard degil).
    app.add_middleware(
        CORSMiddleware,
        allow_origins=get_settings().cors_origins,
        allow_methods=["GET", "POST", "PATCH", "DELETE"],
        allow_headers=["Content-Type"],
    )
    app.include_router(health.router)
    app.include_router(predict.router)
    app.include_router(portfolio.router)
    app.include_router(portfolio_drafts.router)
    app.include_router(portfolio_evaluations.router)
    app.include_router(market.router)
    app.include_router(tickers.router)
    app.include_router(training.router)
    app.include_router(predictions.router)
    app.include_router(risks.router)
    app.include_router(notifications.router)
    return app


app = create_app()
