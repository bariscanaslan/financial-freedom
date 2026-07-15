"""
Pydantic request/response modelleri. GIRDI DOGRULAMA burada yapilir.

Guvenlik notlari:
  - Request govdelerinde extra="forbid": tanimsiz alan (ornegin model_path,
    portfolio_id enjeksiyonu) 422 ile REDDEDILIR. Dosya yolu disaridan gelmez.
  - Ticker regex ile dogrulanir; ham string alt katmana gecmez.
  - Miktar/fiyat/nakit negatif ve absurd degerlere karsi sinirlidir.
"""
from __future__ import annotations

import re

from pydantic import BaseModel, ConfigDict, Field, field_validator

TICKER_RE = re.compile(r"^[A-Z][A-Z0-9.\-]{0,9}$")

# Statik ust sinirlar (absurd deger reddi). Ayrica router settings ile de bakar.
_MAX_QTY = 1e9
_MAX_PRICE = 1e7
_MAX_CASH = 1e12


def _validate_ticker(v: str) -> str:
    v = v.strip().upper()
    if not TICKER_RE.match(v):
        raise ValueError("invalid ticker format")
    return v


# ------------------------------------------------------------------- predict
class PredictRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ticker: str

    @field_validator("ticker")
    @classmethod
    def _ticker(cls, v: str) -> str:
        return _validate_ticker(v)


class CacheRefreshRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ticker: str

    @field_validator("ticker")
    @classmethod
    def _ticker(cls, value: str) -> str:
        return _validate_ticker(value)


class CacheRefreshResponse(BaseModel):
    ticker: str
    rows: int
    first_date: str
    last_date: str


class CacheRefreshAllResponse(BaseModel):
    total: int
    refreshed: int
    failed: list[str]


class ExchangeRateResponse(BaseModel):
    base: str
    quote: str
    rate: float
    as_of: str
    source: str


class ModelMeta(BaseModel):
    """Tanimlayici model metasi (A2). 'Guvenilir' anlamina GELMEZ."""
    ticker: str | None = None
    saved_at: str | None = None
    skill_score: float | None = None
    coverage: float | None = None
    nominal_cov: float | None = None
    git_commit: str | None = None
    note: str = (
        "Descriptive metric. A positive skill_score alone does not mean "
        "'reliable'; the README states the model does not meaningfully beat naive."
    )


class ForecastResponse(BaseModel):
    ticker: str
    as_of: str
    anchor_price: float
    quantiles: list[float]
    returns: dict[str, float]     # A3: p10/p50/p90 birlikte
    prices: dict[str, float]
    uncertainty: float            # p90-p10 (fiyat) = risk sinyali
    uncertainty_pct: float
    periods: dict[str, dict]
    meta: ModelMeta


class SavedPredictionResponse(BaseModel):
    id: str
    ticker: str
    as_of: str
    created_at: str
    forecast: ForecastResponse


class SavedPredictionsResponse(BaseModel):
    count: int
    predictions: list[SavedPredictionResponse]


class ModelSummary(BaseModel):
    ticker: str | None = None
    saved_at: str | None = None
    skill_score: float | None = None
    coverage: float | None = None
    nominal_cov: float | None = None


class ModelsResponse(BaseModel):
    count: int
    models: list[ModelSummary]


# ---------------------------------------------------------------- training
class TrainingRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ticker: str
    horizon: int = 21

    @field_validator("ticker")
    @classmethod
    def _ticker(cls, v: str) -> str:
        return _validate_ticker(v)

    @field_validator("horizon")
    @classmethod
    def _training_horizon(cls, value: int) -> int:
        if value not in {21, 63, 126, 252, 504}:
            raise ValueError("horizon must be 21, 63, 126, 252 or 504")
        return value


class TrainingDeviceResponse(BaseModel):
    device: str


class TrainingTicker(BaseModel):
    ticker: str
    name: str
    has_model: bool
    last_trained_at: str | None = None


class TrainingCatalogResponse(BaseModel):
    as_of: str
    count: int
    tickers: list[TrainingTicker]


class TrainingJobResponse(BaseModel):
    id: str
    ticker: str
    status: str
    stage: str
    device: str
    created_at: str
    started_at: str | None = None
    finished_at: str | None = None
    config: dict = Field(default_factory=dict)
    progress: float | None = None
    history: list[dict] = Field(default_factory=list)
    metrics: dict | None = None
    model_path: str | None = None
    error: str | None = None
    parameters: int | None = None
    train_samples: int | None = None
    val_samples: int | None = None
    test_samples: int | None = None
    best_epoch: int | None = None
    best_val_loss: float | None = None


# ----------------------------------------------------------------- portfolio
class PositionResponse(BaseModel):
    portfolio_id: str
    as_of: str | None = None
    holdings: dict[str, float]
    cash: float


class PositionRow(BaseModel):
    ticker: str
    shares: float
    price: float | None = None
    value: float | None = None
    weight: float | None = None
    change_1d: float | None = None
    change_1w: float | None = None
    change_1m: float | None = None


class PositionsResponse(BaseModel):
    portfolio_id: str
    as_of: str | None = None
    cash: float
    total_value: float | None = None   # eksik fiyat varsa None (0 degil)
    positions: list[PositionRow]


class ValuePoint(BaseModel):
    date: str
    cash: float | None = None
    position_value: float | None = None
    total_value: float | None = None


class ValueSeriesResponse(BaseModel):
    portfolio_id: str
    points: list[ValuePoint]


class MetricsResponse(BaseModel):
    portfolio_id: str
    n_days: int
    total_return: float
    ann_return: float
    ann_vol: float
    sharpe: float | None = None
    max_drawdown: float
    beta: float | None = None
    alpha: float | None = None


class ReportResponse(BaseModel):
    portfolio_id: str
    rows: list[dict]


class EventIn(BaseModel):
    """
    Eklenecek event. portfolio_id BURADA YOK -- path'ten zorlanir (izolasyon +
    traversal). extra="forbid": fazladan alan reddedilir.
    """
    model_config = ConfigDict(extra="forbid")

    type: str
    timestamp: str
    ticker: str | None = None
    quantity: float = Field(0.0, ge=0.0, le=_MAX_QTY)
    price: float = Field(0.0, ge=0.0, le=_MAX_PRICE)
    cash: float = Field(0.0, ge=0.0, le=_MAX_CASH)
    fees: float = Field(0.0, ge=0.0, le=_MAX_CASH)
    note: str = ""

    @field_validator("type")
    @classmethod
    def _type(cls, v: str) -> str:
        # Gecerli event tipleri (torch'suz import).
        from portfolio.events import EventType
        try:
            return EventType(v.upper()).value
        except ValueError:
            raise ValueError(f"invalid event type: {v}")

    @field_validator("ticker")
    @classmethod
    def _ticker(cls, v: str | None) -> str | None:
        return None if v is None else _validate_ticker(v)


class EventAppendResponse(BaseModel):
    portfolio_id: str
    appended: EventIn
    position: PositionResponse


class SimulateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    target_ticker: str
    slippage_bps: float | None = Field(None, ge=0.0, le=1000.0)
    commission_bps: float | None = Field(None, ge=0.0, le=1000.0)

    @field_validator("target_ticker")
    @classmethod
    def _ticker(cls, v: str) -> str:
        return _validate_ticker(v)


class PortfolioForecastResponse(BaseModel):
    portfolio_id: str
    as_of: str
    current_value: float
    cash: float
    quantiles: list[float]
    values: dict[str, float]
    returns: dict[str, float]
    warning: str          # A4: korelasyon ihmali -- susturulamaz
    method: str = "comonotonic"
    correlation: dict[str, dict[str, float]] | None = None
    periods: dict[str, dict] = Field(default_factory=dict)


class RiskSaveRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    portfolio_id: str


class SavedRiskResponse(BaseModel):
    id: str
    portfolio_id: str
    created_at: str
    risk: PortfolioForecastResponse


class SavedRisksResponse(BaseModel):
    count: int
    risks: list[SavedRiskResponse]


# ------------------------------------------------------ portfolio registry
_KINDS = ("actual", "simulated")


class PortfolioCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=80)
    kind: str

    @field_validator("kind")
    @classmethod
    def _kind(cls, v: str) -> str:
        v = v.strip().lower()
        if v not in _KINDS:
            raise ValueError("kind must be 'actual' or 'simulated'")
        return v


class PortfolioSummary(BaseModel):
    id: str
    name: str
    kind: str
    base_currency: str = "USD"
    created_at: str | None = None


class PortfoliosResponse(BaseModel):
    count: int
    portfolios: list[PortfolioSummary]


class InvestEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ticker: str
    cash: float = Field(gt=0.0, le=_MAX_CASH)

    @field_validator("ticker")
    @classmethod
    def _ticker(cls, v: str) -> str:
        return _validate_ticker(v)


class InvestRequest(BaseModel):
    """Build/extend a portfolio by cash amount per ticker at a given date."""
    model_config = ConfigDict(extra="forbid")
    entries: list[InvestEntry] = Field(min_length=1, max_length=50)
    date: str | None = None    # ISO date; None -> latest available price


class TradeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    side: str
    ticker: str
    amount: float = Field(gt=0.0, le=_MAX_CASH)
    date: str | None = None

    @field_validator("side")
    @classmethod
    def _side(cls, value: str) -> str:
        value = value.strip().upper()
        if value not in {"BUY", "SELL"}:
            raise ValueError("side must be BUY or SELL")
        return value

    @field_validator("ticker")
    @classmethod
    def _trade_ticker(cls, value: str) -> str:
        return _validate_ticker(value)


class TradeResponse(BaseModel):
    side: str
    timestamp: str
    ticker: str
    quantity: float
    price: float
    fees: float
    cash_value: float


class TradesResponse(BaseModel):
    portfolio_id: str
    trades: list[TradeResponse]


class PortfolioDraftRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=80)
    investment_amount: float = Field(gt=0.0, le=_MAX_CASH)
    risk_preference: str
    horizon: str
    max_positions: int = Field(default=5, ge=2, le=10)

    @field_validator("risk_preference")
    @classmethod
    def _risk(cls, value: str) -> str:
        value = value.lower()
        if value not in {"conservative", "balanced", "aggressive"}:
            raise ValueError("invalid risk preference")
        return value

    @field_validator("horizon")
    @classmethod
    def _horizon(cls, value: str) -> str:
        value = value.lower()
        if value not in {"daily", "weekly", "monthly", "quarterly", "half_year", "yearly", "two_year"}:
            raise ValueError("invalid horizon")
        return value


class PortfolioDraftAllocation(BaseModel):
    ticker: str
    name: str | None = None
    weight: float = Field(ge=0.0, le=1.0)
    amount: float = Field(ge=0.0)
    expected_return: float
    uncertainty_pct: float
    skill_score: float | None = None


class PortfolioDraftResponse(BaseModel):
    id: str
    created_at: str
    updated_at: str
    name: str
    investment_amount: float
    risk_preference: str
    horizon: str
    max_positions: int
    allocations: list[PortfolioDraftAllocation]
    feedback: str = ""
    disclaimer: str


class PortfolioDraftJobResponse(BaseModel):
    id: str
    status: str
    stage: str
    progress: float
    processed_models: int
    total_models: int
    created_at: str
    finished_at: str | None = None
    draft: PortfolioDraftResponse | None = None
    error: str | None = None
    events: list[str] = Field(default_factory=list)


class PortfolioDraftUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    allocations: dict[str, float]
    feedback: str = Field(default="", max_length=1000)


class PortfolioDraftApply(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: str = "simulated"

    @field_validator("kind")
    @classmethod
    def _draft_kind(cls, value: str) -> str:
        value = value.lower()
        if value not in _KINDS:
            raise ValueError("invalid portfolio kind")
        return value


class PortfolioEvaluationSummary(BaseModel):
    id: str
    portfolio_id: str
    portfolio_name: str
    created_at: str
    as_of: str
    horizon: str


class PortfolioEvaluationsResponse(BaseModel):
    count: int
    evaluations: list[PortfolioEvaluationSummary]


class PortfolioEvaluationPoint(BaseModel):
    date: str
    actual_value: float
    predicted_p10: float
    predicted_p50: float
    predicted_p90: float
    error_pct: float
    covered: bool


class PortfolioEvaluationResponse(PortfolioEvaluationSummary):
    risk_preference: str
    investment_amount: float
    positions: list[dict]
    points: list[PortfolioEvaluationPoint]
    metrics: dict[str, float | int | None]
    note: str


# ---------------------------------------------------------- market overview
class MarketRow(BaseModel):
    ticker: str
    price: float | None = None
    change_1d: float | None = None
    change_1w: float | None = None
    change_1m: float | None = None
    has_model: bool = False


class MarketOverviewResponse(BaseModel):
    count: int
    rows: list[MarketRow]


# ------------------------------------------------------- tracked tickers
class TrackedTicker(BaseModel):
    ticker: str
    first_used: str | None = None
    last_used: str | None = None
    use_count: int = 0


class TickersResponse(BaseModel):
    count: int
    tickers: list[TrackedTicker]


# ----------------------------------------------------------- notifications
class NotificationSettingsUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email: str = Field(default="", max_length=320)
    resend_api_key: str = Field(default="", max_length=500)
    resend_from_email: str = Field(default="", max_length=320)
    telegram_bot_token: str = Field(default="", max_length=500)
    telegram_chat_id: str = Field(default="", max_length=100)
    email_enabled: bool = False
    telegram_enabled: bool = False


class NotificationSettingsResponse(BaseModel):
    email: str
    resend_from_email: str
    telegram_chat_id: str
    email_enabled: bool
    telegram_enabled: bool
    has_resend_api_key: bool
    has_telegram_bot_token: bool
    updated_at: str | None = None


class PortfolioAlertUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    threshold_pct: float = Field(gt=0, le=100)
    email_enabled: bool = False
    telegram_enabled: bool = False
    enabled: bool = True


class PortfolioAlertResponse(PortfolioAlertUpdate):
    portfolio_id: str
    updated_at: str


class WatchlistAlertCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ticker: str
    direction: str
    target_price: float = Field(gt=0, le=_MAX_PRICE)
    email_enabled: bool = False
    telegram_enabled: bool = False

    @field_validator("ticker")
    @classmethod
    def _ticker(cls, value: str) -> str:
        return _validate_ticker(value)

    @field_validator("direction")
    @classmethod
    def _direction(cls, value: str) -> str:
        if value not in {"above", "below"}:
            raise ValueError("invalid direction")
        return value


class WatchlistAlertResponse(WatchlistAlertCreate):
    id: str
    active: bool
    last_price: float | None = None
    triggered_at: str | None = None
    created_at: str
    updated_at: str


class WatchlistAlertsResponse(BaseModel):
    count: int
    alerts: list[WatchlistAlertResponse]
