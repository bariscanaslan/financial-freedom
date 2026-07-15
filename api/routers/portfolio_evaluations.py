"""Oluşturulan portföylerin sabit tahmin snapshot'larını gerçeklerle karşılaştırır."""
from __future__ import annotations

import math
import numpy as np
import pandas as pd
from fastapi import APIRouter, Depends

from api.config import Settings
from api.deps import get_db, get_price_provider, settings_dep
from api.errors import NotFound
from api.schemas import (
    PortfolioEvaluationPoint, PortfolioEvaluationResponse,
    PortfolioEvaluationsResponse, PortfolioEvaluationSummary,
)

router = APIRouter(prefix="/portfolio-evaluations", tags=["portfolio-evaluations"])


@router.get("", response_model=PortfolioEvaluationsResponse)
def list_evaluations(db=Depends(get_db)):
    rows = [PortfolioEvaluationSummary(**row) for row in db.list_portfolio_evaluations()]
    return PortfolioEvaluationsResponse(count=len(rows), evaluations=rows)


def _summary(row: dict) -> dict:
    return {key: row[key] for key in ("id", "portfolio_id", "portfolio_name", "created_at", "as_of", "horizon")}


@router.get("/{evaluation_id}", response_model=PortfolioEvaluationResponse)
def evaluation_detail(evaluation_id: str, db=Depends(get_db), prices=Depends(get_price_provider),
                      settings: Settings = Depends(settings_dep)):
    row = db.get_portfolio_evaluation(evaluation_id)
    if row is None:
        raise NotFound("Portföy değerlendirmesi bulunamadı.")
    positions = row["positions"]
    frames = prices.frames_live([position["ticker"] for position in positions])
    start = pd.Timestamp(row["as_of"])
    horizon_days = positions[0]["forecast"]["periods"][row["horizon"]]["trading_days"]
    available = [frame.index[(frame.index >= start)] for frame in frames.values() if not frame.empty]
    dates = available[0] if available else pd.DatetimeIndex([])
    for index in available[1:]:
        dates = dates.intersection(index)
    dates = dates[:horizon_days + 1]
    initial_positions = sum(position["initial_value"] for position in positions)
    cash = max(float(row["investment_amount"]) - initial_positions, 0.0)
    points = []
    for day, date in enumerate(dates):
        actual = cash + sum(position["shares"] * float(frames[position["ticker"]].loc[date, settings.price_col])
                            for position in positions)
        predicted = {}
        for quantile in ("p10", "p50", "p90"):
            value = cash
            for position in positions:
                forecast = position["forecast"]
                milestones = sorted((period["trading_days"], period["prices"][quantile])
                                    for period in forecast["periods"].values()
                                    if period["trading_days"] <= horizon_days)
                xs = np.array([0, *[item[0] for item in milestones]], dtype=float)
                ys = np.array([0.0, *[math.log(item[1] / forecast["anchor_price"]) for item in milestones]])
                log_return = float(np.interp(day, xs, ys))
                value += position["initial_value"] * math.exp(log_return)
            predicted[quantile] = value
        error = (predicted["p50"] / actual - 1.0) if actual else 0.0
        points.append(PortfolioEvaluationPoint(date=str(date.date()), actual_value=actual,
            predicted_p10=predicted["p10"], predicted_p50=predicted["p50"],
            predicted_p90=predicted["p90"], error_pct=error,
            covered=predicted["p10"] <= actual <= predicted["p90"]))
    actuals = np.array([point.actual_value for point in points], dtype=float)
    medians = np.array([point.predicted_p50 for point in points], dtype=float)
    metrics: dict[str, float | int | None] = {"observations": len(points), "mape": None,
        "rmse": None, "coverage": None, "directional_accuracy": None,
        "realized_return": None, "predicted_return": None, "max_drawdown": None,
        "realized_volatility": None, "bias_pct": None, "average_interval_width_pct": None,
        "lower_breaches": 0, "upper_breaches": 0}
    if len(points):
        metrics.update(mape=float(np.mean(np.abs(medians / actuals - 1))),
            rmse=float(np.sqrt(np.mean((medians - actuals) ** 2))),
            coverage=float(np.mean([point.covered for point in points])),
            realized_return=float(actuals[-1] / actuals[0] - 1) if actuals[0] else None,
            predicted_return=float(medians[-1] / medians[0] - 1) if medians[0] else None,
            max_drawdown=float(np.min(actuals / np.maximum.accumulate(actuals) - 1)),
            bias_pct=float(np.mean(medians / actuals - 1)),
            average_interval_width_pct=float(np.mean([(point.predicted_p90 - point.predicted_p10) / point.actual_value for point in points])),
            lower_breaches=sum(point.actual_value < point.predicted_p10 for point in points),
            upper_breaches=sum(point.actual_value > point.predicted_p90 for point in points))
    if len(points) > 1:
        actual_returns = np.diff(actuals) / actuals[:-1]
        predicted_returns = np.diff(medians) / medians[:-1]
        metrics["directional_accuracy"] = float(np.mean(np.sign(actual_returns) == np.sign(predicted_returns)))
        metrics["realized_volatility"] = float(np.std(actual_returns, ddof=1) * np.sqrt(252)) if len(actual_returns) > 1 else None
    return PortfolioEvaluationResponse(**_summary(row), risk_preference=row["risk_preference"],
        investment_amount=row["investment_amount"], positions=positions, points=points, metrics=metrics,
        note="Ara gün tahminleri, kayıtlı vade noktaları arasında log-getiri interpolasyonu ile gösterilir; snapshot sonradan değiştirilmez.")
