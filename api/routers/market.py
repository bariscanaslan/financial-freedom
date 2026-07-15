"""
GET /market/overview -- curated NASDAQ tickers with latest price + period change.
Cache-first (12h TTL); a cold ticker hits yfinance once then persists.
"""
from __future__ import annotations

import pandas as pd
from fastapi import APIRouter, Depends

from api.config import Settings
from api.deps import get_model_cache, get_price_provider, settings_dep
from api.errors import BadRequest
from api.schemas import CacheRefreshAllResponse, CacheRefreshRequest, CacheRefreshResponse, ExchangeRateResponse, MarketOverviewResponse, MarketRow
from api.services.market import NASDAQ_TOP, build_overview

router = APIRouter(prefix="/market", tags=["market"])


@router.get("/fx/usd-try", response_model=ExchangeRateResponse)
def usd_try_rate(prices=Depends(get_price_provider), settings: Settings = Depends(settings_dep)):
    try:
        rate, timestamp = prices.latest_quote("TRY=X")
    except Exception as exc:
        raise BadRequest("USD/TRY kuru alınamadı.") from exc
    if rate <= 0:
        raise BadRequest("USD/TRY kuru bulunamadı.")
    return ExchangeRateResponse(base="USD", quote="TRY", rate=rate,
        as_of=pd.Timestamp(timestamp).isoformat(), source="Yahoo Finance 15m (TRY=X)")


@router.post("/cache/refresh", response_model=CacheRefreshResponse)
def refresh_cache(body: CacheRefreshRequest, prices=Depends(get_price_provider)) -> CacheRefreshResponse:
    try:
        frame = prices.refresh(body.ticker)
    except Exception as exc:  # veri sağlayıcı ayrıntısını HTTP yanıtına sızdırma
        raise BadRequest(f"{body.ticker} piyasa verisi yenilenemedi.") from exc
    if frame.empty:
        raise BadRequest(f"{body.ticker} için piyasa verisi bulunamadı.")
    return CacheRefreshResponse(
        ticker=body.ticker, rows=len(frame),
        first_date=str(frame.index.min().date()), last_date=str(frame.index.max().date()),
    )


@router.post("/cache/refresh-all", response_model=CacheRefreshAllResponse)
def refresh_all_caches(prices=Depends(get_price_provider)) -> CacheRefreshAllResponse:
    tickers = prices.cached_tickers()
    failed = []
    refreshed = 0
    for ticker in tickers:
        try:
            frame = prices.refresh(ticker)
            prices.refresh_intraday(ticker)
            if frame.empty:
                failed.append(ticker)
            else:
                refreshed += 1
        except Exception:  # tek ticker hatası diğer cache'leri durdurmaz
            failed.append(ticker)
    return CacheRefreshAllResponse(total=len(tickers), refreshed=refreshed, failed=failed)


@router.get("/overview", response_model=MarketOverviewResponse)
def overview(
    prices=Depends(get_price_provider),
    cache=Depends(get_model_cache),
    settings: Settings = Depends(settings_dep),
) -> MarketOverviewResponse:
    frames = prices.frames_live(NASDAQ_TOP)
    model_tickers = {s["ticker"] for s in cache.summaries() if s.get("ticker")}
    rows = build_overview(frames, model_tickers, price_col=settings.price_col)
    return MarketOverviewResponse(count=len(rows), rows=[MarketRow(**r) for r in rows])
