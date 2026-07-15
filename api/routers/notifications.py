"""Bildirim ayarları, portföy eşikleri ve takip listesi API'si."""
from fastapi import APIRouter, Depends, Request

from api.deps import get_db, get_price_provider, require_portfolio
from api.errors import BadRequest, NotFound
from api.schemas import (
    NotificationSettingsResponse, NotificationSettingsUpdate, NotificationTestRequest,
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
def test_notification(body: NotificationTestRequest, request: Request, db=Depends(get_db)):
    settings = db.get_notification_settings()
    choices = {
        "email_enabled": body.channel in {"all", "email"} and settings["email_enabled"],
        "telegram_enabled": body.channel in {"all", "telegram"} and settings["telegram_enabled"],
    }
    result = request.app.state.notification_service.send(
        "Financial Freedom test bildirimi", "Bildirim ayarlarınız başarıyla çalışıyor.",
        choices, kind="test")
    return result


@router.get("/portfolios/{portfolio_id}/alert", response_model=PortfolioAlertResponse | None)
def get_portfolio_alert(pid: str = Depends(require_portfolio), db=Depends(get_db)):
    return db.get_portfolio_alert(pid)


@router.put("/portfolios/{portfolio_id}/alert", response_model=PortfolioAlertResponse)
def update_portfolio_alert(body: PortfolioAlertUpdate, pid: str = Depends(require_portfolio), db=Depends(get_db)):
    return db.upsert_portfolio_alert(pid, body.model_dump())


@router.post("/portfolios/{portfolio_id}/alert/test")
def test_portfolio_alert(request: Request, pid: str = Depends(require_portfolio), db=Depends(get_db)):
    alert = db.get_portfolio_alert(pid)
    if alert is None:
        raise BadRequest("Önce portföy alarmını kaydedin.")
    portfolio = db.get_portfolio(pid)
    return request.app.state.notification_service.send(
        f"{portfolio['name']} portföy alarmı testi",
        f"%{alert['threshold_pct']:.2f} hareket eşiği için test bildirimi. Gerçek alarm durumu değiştirilmedi.",
        alert, kind="portfolio_test")


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


@router.post("/watchlist/{alert_id}/test")
def test_watchlist_alert(alert_id: str, request: Request, db=Depends(get_db)):
    alert = db.get_watchlist_alert(alert_id)
    if alert is None:
        raise NotFound("watchlist alert not found")
    direction = "üzerine çıkma" if alert["direction"] == "above" else "altına düşme"
    return request.app.state.notification_service.send(
        f"{alert['ticker']} takip alarmı testi",
        f"${alert['target_price']:.2f} hedefine {direction} bildirimi test edildi. Alarm durumu değiştirilmedi.",
        alert, kind="watchlist_test")


@router.delete("/watchlist/{alert_id}")
def delete_watchlist(alert_id: str, db=Depends(get_db)):
    if not db.delete_watchlist_alert(alert_id):
        raise NotFound("watchlist alert not found")
    return {"id": alert_id, "deleted": True}
