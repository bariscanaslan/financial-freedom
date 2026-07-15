"""Model destekli portföy taslakları; karar kullanıcıya aittir."""
from __future__ import annotations

import math
import pandas as pd
from fastapi import APIRouter, Depends

from api.config import Settings
from api.deps import get_db, get_model_cache, get_portfolio_draft_manager, get_price_provider, settings_dep
from api.errors import BadRequest, NotFound
from api.routers.portfolio import MARKET_TZ, _resolve_buy
from api.routers.predict import build_forecast
from api.schemas import (
    PortfolioDraftApply, PortfolioDraftJobResponse, PortfolioDraftRequest, PortfolioDraftResponse,
    PortfolioDraftUpdate, PortfolioSummary,
)
from api.services.nasdaq_catalog import NASDAQ_100
from portfolio.events import Event, EventType
from portfolio.simulate import invest_cash

router = APIRouter(prefix="/portfolio-drafts", tags=["portfolio-drafts"])
DISCLAIMER = "Bu taslak model çıktılarından üretilen tanımlayıcı bir senaryodur; yatırım tavsiyesi değildir."


def _generate(body: PortfolioDraftRequest, cache, prices, db, progress=None) -> dict:
    names = dict(NASDAQ_100)
    period_key = body.horizon
    candidates = []
    latest = set()
    summaries = []
    for summary in cache.summaries():
        ticker = summary.get("ticker")
        if ticker and ticker in names and ticker not in latest:
            latest.add(ticker)
            summaries.append(summary)
    for index, summary in enumerate(summaries, 1):
        ticker = summary.get("ticker")
        try:
            forecast = build_forecast(ticker, cache, prices, db)
        except Exception:  # bozuk/verisi eksik model diğer adayları engellemez
            if progress: progress(index, len(summaries), f"{ticker} tahmini hazırlanamadı; atlandı.")
            continue
        period = forecast.periods.get(period_key)
        if not period:
            if progress: progress(index, len(summaries), f"{ticker} seçilen vadeyi desteklemiyor.")
            continue
        expected = float(period["returns"]["p50"])
        uncertainty = max(float(period["prices"]["p90"] - period["prices"]["p10"]) / forecast.anchor_price, 1e-6)
        metrics = (cache.meta(ticker).get("test_metrics") or {}).get("horizon_metrics", {}).get(period_key, {})
        skill = metrics.get("skill_score", summary.get("skill_score"))
        current_metrics = metrics.get("aggregation") == "root_sum_square"
        coverage = metrics.get("coverage") if current_metrics else summary.get("coverage")
        nominal = metrics.get("nominal_cov") if current_metrics else summary.get("nominal_cov")
        skill_value = float(skill) if skill is not None else 0.0
        days = int(period["trading_days"])
        base_limit = {"conservative": 0.35, "balanced": 0.60, "aggressive": 1.00}[body.risk_preference]
        absolute_limit = {"conservative": 1.00, "balanced": 1.50, "aggressive": 2.50}[body.risk_preference]
        max_uncertainty = min(base_limit * math.sqrt(days / 21), absolute_limit)
        failures = []
        if skill_value < 0.01:
            failures.append(f"skill {skill_value:+.3f} < +0.010")
        if uncertainty > max_uncertainty:
            failures.append(f"belirsizlik %{uncertainty * 100:.1f} > %{max_uncertainty * 100:.1f}")
        if failures:
            if progress: progress(index, len(summaries), f"{ticker} elendi: {', '.join(failures)}.")
            continue
        if coverage is None or nominal is None or abs(float(coverage) - float(nominal)) > 0.15:
            detail = "metrik yok" if coverage is None or nominal is None else f"kapsama sapması {abs(float(coverage) - float(nominal)):.3f} > 0.150"
            if progress: progress(index, len(summaries), f"{ticker} elendi: {detail}.")
            continue
        penalty = {"conservative": 1.5, "balanced": 0.8, "aggressive": 0.3}[body.risk_preference]
        score = expected + 0.15 * skill_value - penalty * uncertainty
        candidates.append((score, ticker, expected, uncertainty, skill))
        if progress: progress(index, len(summaries), f"{ticker} aday listeye eklendi.")
    if len(candidates) < 2:
        raise BadRequest("Seçilen vadede beceri, kalibrasyon ve belirsizlik eşiklerini geçen en az iki model gerekir. Modelleri seçilen vadede yeniden eğitin.")
    selected = sorted(candidates, reverse=True)[:body.max_positions]
    raw = [1.0 / item[3] if body.risk_preference == "conservative" else max(item[0] - selected[-1][0] + 0.01, 0.01) for item in selected]
    total = sum(raw)
    allocations = [{
        "ticker": item[1], "name": names.get(item[1]), "weight": weight / total,
        "amount": body.investment_amount * weight / total, "expected_return": item[2],
        "uncertainty_pct": item[3], "skill_score": item[4],
    } for item, weight in zip(selected, raw)]
    return {**body.model_dump(), "allocations": allocations, "feedback": "", "disclaimer": DISCLAIMER}


@router.post("/generate", response_model=PortfolioDraftJobResponse)
def start_generation(body: PortfolioDraftRequest, manager=Depends(get_portfolio_draft_manager)):
    return PortfolioDraftJobResponse(**manager.start(body))


@router.get("/generate/{job_id}", response_model=PortfolioDraftJobResponse)
def generation_status(job_id: str, manager=Depends(get_portfolio_draft_manager)):
    return PortfolioDraftJobResponse(**manager.get(job_id))


@router.post("", response_model=PortfolioDraftResponse)
def create_draft(body: PortfolioDraftRequest, cache=Depends(get_model_cache),
                 prices=Depends(get_price_provider), db=Depends(get_db)):
    return PortfolioDraftResponse(**db.save_portfolio_draft(_generate(body, cache, prices, db)))


@router.get("/{draft_id}", response_model=PortfolioDraftResponse)
def get_draft(draft_id: str, db=Depends(get_db)):
    row = db.get_portfolio_draft(draft_id)
    if row is None:
        raise NotFound("Portföy taslağı bulunamadı.")
    return PortfolioDraftResponse(**row)


@router.patch("/{draft_id}", response_model=PortfolioDraftResponse)
def update_draft(draft_id: str, body: PortfolioDraftUpdate, db=Depends(get_db)):
    current = db.get_portfolio_draft(draft_id)
    if current is None:
        raise NotFound("Portföy taslağı bulunamadı.")
    known = {item["ticker"]: item for item in current["allocations"]}
    if set(body.allocations) != set(known) or any(value < 0 for value in body.allocations.values()):
        raise BadRequest("Taslak sembolleri için geçerli ağırlıklar gönderin.")
    total = sum(body.allocations.values())
    if total <= 0:
        raise BadRequest("Toplam ağırlık sıfır olamaz.")
    current["allocations"] = [{**known[ticker], "weight": value / total,
        "amount": current["investment_amount"] * value / total} for ticker, value in body.allocations.items()]
    current["feedback"] = body.feedback
    payload = {key: value for key, value in current.items() if key not in {"id", "created_at", "updated_at"}}
    return PortfolioDraftResponse(**db.update_portfolio_draft(draft_id, payload))


@router.post("/{draft_id}/apply", response_model=PortfolioSummary)
def apply_draft(draft_id: str, body: PortfolioDraftApply, db=Depends(get_db),
                prices=Depends(get_price_provider), cache=Depends(get_model_cache),
                settings: Settings = Depends(settings_dep)):
    draft = db.get_portfolio_draft(draft_id)
    if draft is None:
        raise NotFound("Portföy taslağı bulunamadı.")
    resolved = []
    for item in draft["allocations"]:
        hit = _resolve_buy(prices.recent(item["ticker"])[settings.price_col], None)
        if hit is None:
            raise BadRequest(f"{item['ticker']} için fiyat verisi yok.")
        forecast = build_forecast(item["ticker"], cache, prices, db)
        if draft["horizon"] not in forecast.periods:
            raise BadRequest(f"{item['ticker']} seçilen vadeyi artık desteklemiyor.")
        resolved.append((item, hit, forecast))
    portfolio = db.create_portfolio(draft["name"], body.kind)
    positions = []
    for item, (day, price), forecast in resolved:
        timestamp = pd.Timestamp(day).tz_localize(MARKET_TZ)
        db.append_event(Event(portfolio["id"], EventType.DEPOSIT, timestamp, cash=item["amount"], note="draft funding"))
        event = invest_cash(portfolio["id"], item["ticker"], item["amount"], price, timestamp, note=f"draft {draft_id}")
        if event:
            db.append_event(event)
            positions.append({"ticker": item["ticker"], "shares": event.quantity,
                "initial_price": event.price, "initial_value": event.quantity * event.price,
                "weight": item["weight"], "forecast": forecast.model_dump()})
    as_of = max(position["forecast"]["as_of"] for position in positions)
    db.save_portfolio_evaluation(portfolio["id"], {
        "portfolio_name": portfolio["name"], "as_of": as_of,
        "horizon": draft["horizon"], "risk_preference": draft["risk_preference"],
        "investment_amount": draft["investment_amount"], "positions": positions,
    })
    return PortfolioSummary(**portfolio)
