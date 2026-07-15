"""
Portfolio endpoints -- thin HTTP shell over portfolio/ + the SQLite registry.

Portfolios are user-created rows in the DB (registry). Within a portfolio the
event log stays append-only (a correction is a reversing event); deleting a
whole portfolio is a registry operation. Isolation: every item route goes
through require_portfolio (validates the id and 404s if unknown); on writes the
event.portfolio_id is forced from the path, never the body.
"""
from __future__ import annotations

import math

import pandas as pd
from fastapi import APIRouter, Depends

from portfolio.events import Event, EventType
from portfolio.metrics import daily_returns, performance
from portfolio.portfolio import Portfolio
from portfolio.positions import positions_view
from portfolio.report import build_report
from portfolio.simulate import buy_and_hold_from_flows, invest_cash
from portfolio.valuation import value_series

from api.config import Settings, get_settings
from api.deps import (
    get_db,
    get_model_cache,
    get_price_provider,
    require_portfolio,
    settings_dep,
)
from api.errors import BadRequest
from api.schemas import (
    EventAppendResponse,
    EventIn,
    InvestRequest,
    MetricsResponse,
    PortfolioCreate,
    PortfolioForecastResponse,
    PortfoliosResponse,
    PortfolioSummary,
    PositionResponse,
    PositionRow,
    PositionsResponse,
    ReportResponse,
    SimulateRequest,
    TradeRequest,
    TradeResponse,
    TradesResponse,
    ValuePoint,
    ValueSeriesResponse,
)

router = APIRouter(prefix="/portfolios", tags=["portfolio"])

MARKET_TZ = "America/New_York"


# --------------------------------------------------------------- helpers
def _f(x) -> float | None:
    """NaN/None -> None (JSON validity). Otherwise float."""
    if x is None:
        return None
    try:
        xf = float(x)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(xf) else xf


def _portfolio(db, pid: str) -> Portfolio:
    return Portfolio(pid, db.events_for(pid))


def _position_response(pf: Portfolio, pid: str) -> PositionResponse:
    st = pf.replay()
    return PositionResponse(
        portfolio_id=pid,
        as_of=(str(st.as_of.date()) if st.as_of is not None else None),
        holdings=st.holdings,
        cash=st.cash,
    )


def _resolve_buy(price: pd.Series, date: str | None):
    """Buy day + price: first trading day >= date, or the latest available."""
    p = price.dropna()
    if p.empty:
        return None
    if date is None:
        return p.index[-1], float(p.iloc[-1])
    fut = p.loc[p.index >= pd.Timestamp(date)]
    if fut.empty:
        return None
    return fut.index[0], float(fut.iloc[0])


# ------------------------------------------------------------ registry
@router.get("", response_model=PortfoliosResponse)
def list_portfolios(db=Depends(get_db)) -> PortfoliosResponse:
    rows = [PortfolioSummary(**r) for r in db.list_portfolios()]
    return PortfoliosResponse(count=len(rows), portfolios=rows)


@router.post("", response_model=PortfolioSummary)
def create_portfolio(body: PortfolioCreate, db=Depends(get_db)) -> PortfolioSummary:
    row = db.create_portfolio(body.name, body.kind)
    return PortfolioSummary(**row)


@router.delete("/{portfolio_id}")
def delete_portfolio(
    pid: str = Depends(require_portfolio),
    db=Depends(get_db),
) -> dict:
    db.delete_portfolio(pid)
    return {"portfolio_id": pid, "deleted": True}


# --------------------------------------------------------------- invest
@router.post("/{portfolio_id}/invest", response_model=PositionResponse)
def invest(
    body: InvestRequest,
    pid: str = Depends(require_portfolio),
    db=Depends(get_db),
    prices=Depends(get_price_provider),
    settings: Settings = Depends(settings_dep),
) -> PositionResponse:
    # Cash amount per ticker -> DEPOSIT + BUY at the real market fill price.
    # Model-independent: prices come from the market data cache, not a model.
    for entry in body.entries:
        df = prices.recent(entry.ticker)
        hit = _resolve_buy(df[settings.price_col], body.date)
        if hit is None:
            raise BadRequest(f"no price data for {entry.ticker}")
        day, ref = hit
        ts = pd.Timestamp(day).tz_localize(MARKET_TZ)
        db.append_event(Event(pid, EventType.DEPOSIT, ts, cash=entry.cash))
        buy = invest_cash(pid, entry.ticker, entry.cash, ref, ts,
                          note="invest")
        if buy is not None:
            db.append_event(buy)
    return _position_response(_portfolio(db, pid), pid)


@router.post("/{portfolio_id}/trades", response_model=TradeResponse)
def create_trade(
    body: TradeRequest,
    pid: str = Depends(require_portfolio),
    db=Depends(get_db), prices=Depends(get_price_provider),
    settings: Settings = Depends(settings_dep),
) -> TradeResponse:
    frame = prices.recent(body.ticker)
    hit = _resolve_buy(frame[settings.price_col], body.date)
    if hit is None:
        raise BadRequest(f"no price data for {body.ticker}")
    day, ref = hit
    ts = pd.Timestamp(day).tz_localize(MARKET_TZ)
    if body.side == "BUY":
        db.append_event(Event(pid, EventType.DEPOSIT, ts, cash=body.amount,
                              note="trade funding"))
        event = invest_cash(pid, body.ticker, body.amount, ref, ts, note="portfolio edit")
        if event is None:
            raise BadRequest("Alım tutarı işlem maliyetini karşılamıyor.")
    else:
        state = _portfolio(db, pid).replay()
        held = state.holdings.get(body.ticker, 0.0)
        if body.amount > held + 1e-9:
            raise BadRequest(f"Yetersiz pozisyon: mevcut {held:.6f} adet")
        from portfolio.simulate import make_sell
        event = make_sell(pid, body.ticker, body.amount, ref, ts, note="portfolio edit")
    db.append_event(event)
    return TradeResponse(
        side=event.type.value, timestamp=event.timestamp.isoformat(), ticker=event.ticker,
        quantity=event.quantity, price=event.price, fees=event.fees,
        cash_value=event.quantity * event.price,
    )


@router.get("/{portfolio_id}/trades", response_model=TradesResponse)
def list_trades(pid: str = Depends(require_portfolio), db=Depends(get_db)) -> TradesResponse:
    trades = [event for event in db.events_for(pid) if event.type in {EventType.BUY, EventType.SELL}]
    return TradesResponse(portfolio_id=pid, trades=[TradeResponse(
        side=event.type.value, timestamp=event.timestamp.isoformat(), ticker=event.ticker,
        quantity=event.quantity, price=event.price, fees=event.fees,
        cash_value=event.quantity * event.price,
    ) for event in reversed(trades)])


# ------------------------------------------------------------------- reads
@router.get("/{portfolio_id}", response_model=PositionResponse)
def get_position(
    pid: str = Depends(require_portfolio),
    db=Depends(get_db),
) -> PositionResponse:
    return _position_response(_portfolio(db, pid), pid)


@router.get("/{portfolio_id}/positions", response_model=PositionsResponse)
def get_positions(
    pid: str = Depends(require_portfolio),
    db=Depends(get_db),
    prices=Depends(get_price_provider),
    settings: Settings = Depends(settings_dep),
) -> PositionsResponse:
    pf = _portfolio(db, pid)
    frames = prices.frames_live(pf.tickers())
    view = positions_view(pf, frames, price_col=settings.price_col)
    rows = [
        PositionRow(
            ticker=p.ticker,
            shares=p.shares,
            price=_f(p.price),
            value=_f(p.value),
            weight=_f(p.weight),
            change_1d=_f(p.change_1d),
            change_1w=_f(p.change_1w),
            change_1m=_f(p.change_1m),
        )
        for p in view.positions
    ]
    return PositionsResponse(
        portfolio_id=pid,
        as_of=(str(view.as_of.date()) if view.as_of is not None else None),
        cash=view.cash,
        total_value=_f(view.total_value),
        positions=rows,
    )


@router.get("/{portfolio_id}/value", response_model=ValueSeriesResponse)
def get_value(
    pid: str = Depends(require_portfolio),
    db=Depends(get_db),
    prices=Depends(get_price_provider),
    settings: Settings = Depends(settings_dep),
) -> ValueSeriesResponse:
    pf = _portfolio(db, pid)
    frames = prices.frames(pf.tickers())
    vs = value_series(pf, frames, price_col=settings.price_col)
    if len(vs) > settings.max_value_days:
        vs = vs.iloc[-settings.max_value_days:]
    points = [
        ValuePoint(
            date=str(idx.date()),
            cash=_f(row["cash"]),
            position_value=_f(row["position_value"]),
            total_value=_f(row["total_value"]),
        )
        for idx, row in vs.iterrows()
    ]
    return ValueSeriesResponse(portfolio_id=pid, points=points)


def _benchmark_returns(pf: Portfolio, frames: dict, settings: Settings) -> pd.Series:
    bench_events = buy_and_hold_from_flows(
        pf, settings.benchmark_ticker, frames,
        portfolio_id="benchmark", price_col=settings.price_col,
    )
    bench = Portfolio("benchmark", bench_events)
    bvs = value_series(bench, frames, price_col=settings.price_col)
    return daily_returns(bvs["total_value"], bvs["external_flow"])


@router.get("/{portfolio_id}/metrics", response_model=MetricsResponse)
def get_metrics(
    pid: str = Depends(require_portfolio),
    db=Depends(get_db),
    prices=Depends(get_price_provider),
    settings: Settings = Depends(settings_dep),
) -> MetricsResponse:
    pf = _portfolio(db, pid)
    frames = prices.frames(pf.tickers() + [settings.benchmark_ticker])
    vs = value_series(pf, frames, price_col=settings.price_col)
    bench_returns = _benchmark_returns(pf, frames, settings)
    perf = performance(vs, pid, benchmark_returns=bench_returns)
    return MetricsResponse(
        portfolio_id=pid,
        n_days=perf.n_days,
        total_return=perf.total_return,
        ann_return=perf.ann_return,
        ann_vol=perf.ann_vol,
        sharpe=_f(perf.sharpe),
        max_drawdown=perf.max_drawdown,
        beta=_f(perf.beta),
        alpha=_f(perf.alpha),
    )


@router.get("/{portfolio_id}/report", response_model=ReportResponse)
def get_report(
    pid: str = Depends(require_portfolio),
    db=Depends(get_db),
    prices=Depends(get_price_provider),
    settings: Settings = Depends(settings_dep),
) -> ReportResponse:
    pf = _portfolio(db, pid)
    frames = prices.frames(pf.tickers() + [settings.benchmark_ticker])
    df = build_report(pf, None, frames, benchmark_ticker=settings.benchmark_ticker,
                      price_col=settings.price_col)
    rows = [{k: _f(v) if isinstance(v, float) else v for k, v in r.items()}
            for r in df.to_dict("records")]
    return ReportResponse(portfolio_id=pid, rows=rows)


# ------------------------------------------------------------------- simulate
@router.post("/{portfolio_id}/simulate", response_model=ReportResponse)
def simulate(
    req: SimulateRequest,
    pid: str = Depends(require_portfolio),
    db=Depends(get_db),
    prices=Depends(get_price_provider),
    settings: Settings = Depends(settings_dep),
) -> ReportResponse:
    pf = _portfolio(db, pid)
    tickers = pf.tickers() + [req.target_ticker, settings.benchmark_ticker]
    frames = prices.frames(tickers)

    fee_kw = {}
    if req.slippage_bps is not None:
        fee_kw["slippage_bps"] = req.slippage_bps
    if req.commission_bps is not None:
        fee_kw["commission_bps"] = req.commission_bps

    sim_events = buy_and_hold_from_flows(
        pf, req.target_ticker, frames, portfolio_id=f"{pid}__sim",
        price_col=settings.price_col, **fee_kw,
    )
    simulated = Portfolio(f"{pid}__sim", sim_events)
    df = build_report(pf, simulated, frames, benchmark_ticker=settings.benchmark_ticker,
                      price_col=settings.price_col)
    rows = [{k: _f(v) if isinstance(v, float) else v for k, v in r.items()}
            for r in df.to_dict("records")]
    return ReportResponse(portfolio_id=pid, rows=rows)


# ------------------------------------------------------------------- forecast
def build_portfolio_forecast(pid, db, cache, prices) -> PortfolioForecastResponse:
    from model.predict import predict as run_predict
    from portfolio.forecast_link import portfolio_forecast, return_correlation

    pf = _portfolio(db, pid)
    state = pf.replay()
    frames = prices.frames(list(state.holdings))
    forecasts = {}
    for ticker in state.holdings:
        model = cache.get(ticker)
        try:
            forecasts[ticker] = run_predict(model, frames[ticker], ticker=ticker)
        except ValueError as exc:
            raise BadRequest(str(exc))

    corr = return_correlation(frames)
    pfc = portfolio_forecast(state, forecasts, correlation=corr)
    return PortfolioForecastResponse(
        portfolio_id=pid, as_of=pfc.as_of, current_value=pfc.current_value,
        cash=pfc.cash, quantiles=list(pfc.quantiles), values=pfc.values,
        returns=pfc.returns, warning=pfc.warning, method=pfc.method,
        correlation=pfc.correlation, periods=pfc.periods,
    )


@router.get("/{portfolio_id}/forecast", response_model=PortfolioForecastResponse)
def get_forecast(
    pid: str = Depends(require_portfolio),
    db=Depends(get_db),
    cache=Depends(get_model_cache),
    prices=Depends(get_price_provider),
) -> PortfolioForecastResponse:
    return build_portfolio_forecast(pid, db, cache, prices)


# --------------------------------------------------------------- append event
@router.post("/{portfolio_id}/events", response_model=EventAppendResponse)
def append_event(
    body: EventIn,
    pid: str = Depends(require_portfolio),
    db=Depends(get_db),
) -> EventAppendResponse:
    # portfolio_id forced from the PATH -- the body is not trusted (isolation).
    try:
        event = Event(
            portfolio_id=pid,
            type=body.type,
            timestamp=body.timestamp,
            ticker=body.ticker,
            quantity=body.quantity,
            price=body.price,
            cash=body.cash,
            fees=body.fees,
            note=body.note,
        )
    except ValueError as e:
        raise BadRequest(str(e))

    db.append_event(event)
    pf = _portfolio(db, pid)
    return EventAppendResponse(
        portfolio_id=pid,
        appended=body,
        position=_position_response(pf, pid),
    )
