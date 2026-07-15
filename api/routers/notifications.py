"""Bildirim ayarları, portföy eşikleri ve takip listesi API'si."""
from fastapi import APIRouter, Depends, Request

from api.deps import get_db, get_price_provider, require_portfolio
from api.errors import BadRequest, NotFound
from api.schemas import (
    NotificationSettingsResponse, NotificationSettingsUpdate,
    PortfolioAlertResponse, PortfolioAlertUpdate,
    WatchlistAlertCreate, WatchlistAlertResponse, WatchlistAlertsResponse,
)
from api.schemas import TICKER_RE

router = APIRouter(tags=["notifications"])


@router.get("/notification-settings", response_model=NotificationSettingsResponse)
def get_settings(db=Depends(get_db)):
    return db.get_notification_settings()


@router.put("/notification-settings", response_model=NotificationSettingsResponse)
def update_settings(body: NotificationSettingsUpdate, db=Depends(get_db)):
    return db.save_notification_settings(body.model_dump())


@router.post("/notification-settings/test")
def test_notification(request: Request, db=Depends(get_db)):
    settings = db.get_notification_settings()
    result = request.app.state.notification_service.send(
        "Financial Freedom test bildirimi", "Bildirim ayarlarınız başarıyla çalışıyor.",
        {"email_enabled": settings["email_enabled"], "telegram_enabled": settings["telegram_enabled"]},
        kind="test")
    return result


@router.get("/portfolios/{portfolio_id}/alert", response_model=PortfolioAlertResponse | None)
def get_portfolio_alert(pid: str = Depends(require_portfolio), db=Depends(get_db)):
    return db.get_portfolio_alert(pid)


@router.put("/portfolios/{portfolio_id}/alert", response_model=PortfolioAlertResponse)
def update_portfolio_alert(body: PortfolioAlertUpdate, pid: str = Depends(require_portfolio), db=Depends(get_db)):
    return db.upsert_portfolio_alert(pid, body.model_dump())


@router.get("/watchlist", response_model=WatchlistAlertsResponse)
def list_watchlist(db=Depends(get_db)):
    alerts = db.list_watchlist_alerts()
    return {"count": len(alerts), "alerts": alerts}


@router.get("/watchlist/quote")
def watchlist_quote(ticker: str, prices=Depends(get_price_provider)):
    ticker = ticker.strip().upper()
    if not TICKER_RE.match(ticker):
        raise BadRequest("invalid ticker format")
    price, timestamp = prices.latest_quote(ticker)
    return {"ticker": ticker, "price": price, "as_of": timestamp.isoformat()}


@router.post("/watchlist", response_model=WatchlistAlertResponse)
def create_watchlist(body: WatchlistAlertCreate, db=Depends(get_db), prices=Depends(get_price_provider)):
    row = db.create_watchlist_alert(body.model_dump())
    try:
        price, _ = prices.latest_quote(body.ticker)
        db.update_watchlist_observation(row["id"], price)
    except Exception:
        pass
    return db.get_watchlist_alert(row["id"])


@router.delete("/watchlist/{alert_id}")
def delete_watchlist(alert_id: str, db=Depends(get_db)):
    if not db.delete_watchlist_alert(alert_id):
        raise NotFound("watchlist alert not found")
    return {"id": alert_id, "deleted": True}
