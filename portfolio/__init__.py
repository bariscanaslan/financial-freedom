"""
Portfolyo katmani: event log + degerleme + performans + simulasyon.

Bu katman tahmin URETMEZ; pozisyonlari tutar, degerler ve model/predict.py'nin
ciktisini portfolyoya UYGULAR. Bir yatirim tavsiyesi urunu degildir.

Tasarim ozeti:
  - Event log tek gercek kaynaktir (snapshot degil); durum replay ile turer.
  - actual ve simulated AYNI Portfolio sinifi, farkli portfolio_id.
  - Islem maliyeti/slippage zorunlu; simulasyon fee'siz calisirsa uyarir.
  - Getiri her zaman benchmark ile birlikte (TWR, net-of-fees).
"""
from .config import BASE_CURRENCY, BENCHMARK_TICKER
from .events import Event, EventType, cash_delta, external_flow
from .forecast_link import PortfolioForecast, portfolio_forecast
from .metrics import Performance, performance
from .portfolio import Portfolio, PositionState
from .positions import Position, PositionsView, positions_view
from .report import build_report, render
from .simulate import buy_and_hold_from_flows, invest_cash, make_buy, make_sell
from .store import EventStore
from .valuation import value_series

__all__ = [
    "Event", "EventType", "cash_delta", "external_flow",
    "EventStore",
    "Portfolio", "PositionState",
    "Position", "PositionsView", "positions_view",
    "value_series",
    "Performance", "performance",
    "make_buy", "make_sell", "invest_cash", "buy_and_hold_from_flows",
    "PortfolioForecast", "portfolio_forecast",
    "build_report", "render",
    "BASE_CURRENCY", "BENCHMARK_TICKER",
]
