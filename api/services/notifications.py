"""15 dakikalık portföy/takip listesi kontrolleri ve bildirim teslimi."""
from __future__ import annotations

import logging
import threading

import httpx

from portfolio.portfolio import Portfolio

log = logging.getLogger("api.notifications")


class NotificationService:
    def __init__(self, db, prices, redis_backend=None, interval_seconds: int = 900):
        self._db, self._prices, self._redis = db, prices, redis_backend
        self._interval = interval_seconds
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._loop, name="notification-monitor", daemon=True)
        self._thread.start()

    def close(self) -> None:
        self._stop.set()
        self._thread.join(timeout=3)

    def _loop(self) -> None:
        if self._stop.wait(15):
            return
        while not self._stop.is_set():
            try:
                self.check_now()
            except Exception:
                log.exception("Bildirim kontrolü başarısız.")
            self._stop.wait(self._interval)

    def check_now(self) -> None:
        lock = self._redis.acquire("notification-monitor", 840) if self._redis else "memory"
        if lock is None:
            return
        try:
            self._check_portfolios()
            self._check_watchlist()
        finally:
            if self._redis:
                self._redis.release("notification-monitor", lock)

    def _check_portfolios(self) -> None:
        portfolios = {row["id"]: row for row in self._db.list_portfolios()}
        for alert in self._db.list_portfolio_alerts():
            pid = alert["portfolio_id"]
            if pid not in portfolios:
                continue
            state = Portfolio(pid, self._db.events_for(pid)).replay()
            for ticker in state.holdings:
                try:
                    current, _ = self._prices.latest_quote(ticker)
                    previous = self._db.get_alert_observation(pid, ticker)
                    if previous is None or previous <= 0:
                        self._db.set_alert_observation(pid, ticker, current)
                        continue
                    change = (current / previous - 1) * 100
                    if abs(change) < alert["threshold_pct"]:
                        self._db.set_alert_observation(pid, ticker, current)
                        continue
                    direction = "yükseldi" if change > 0 else "düştü"
                    subject = f"{portfolios[pid]['name']}: {ticker} hareket uyarısı"
                    message = (f"{ticker}, son 15 dakikalık gözleme göre %{abs(change):.2f} {direction}. "
                               f"Önceki fiyat ${previous:.2f}, güncel fiyat ${current:.2f}.")
                    result = self.send(subject, message, alert, kind="portfolio")
                    if result["status"] in {"sent", "partial"}:
                        self._db.set_alert_observation(pid, ticker, current)
                except Exception as exc:
                    log.warning("%s portföy alarmı kontrol edilemedi: %s", ticker, exc)

    def _check_watchlist(self) -> None:
        for alert in self._db.list_watchlist_alerts(active_only=True):
            try:
                current, _ = self._prices.latest_quote(alert["ticker"])
                reached = (alert["direction"] == "above" and current >= alert["target_price"]) or (
                    alert["direction"] == "below" and current <= alert["target_price"])
                if reached:
                    verb = "üzerine çıktı" if alert["direction"] == "above" else "altına düştü"
                    subject = f"{alert['ticker']} hedef fiyat uyarısı"
                    message = f"{alert['ticker']} ${alert['target_price']:.2f} hedefinin {verb}. Güncel fiyat: ${current:.2f}."
                    result = self.send(subject, message, alert, kind="watchlist")
                    self._db.update_watchlist_observation(
                        alert["id"], current, triggered=result["status"] in {"sent", "partial"})
                else:
                    self._db.update_watchlist_observation(alert["id"], current)
            except Exception as exc:
                log.warning("%s takip alarmı kontrol edilemedi: %s", alert["ticker"], exc)

    def send(self, subject: str, message: str, choices: dict, *, kind: str) -> dict:
        settings = self._db.get_notification_settings(include_secrets=True)
        channels, errors = [], []
        if choices.get("email_enabled") and settings.get("email_enabled"):
            try:
                self._send_email(settings, subject, message)
                channels.append("email")
            except Exception:
                errors.append("E-posta teslim edilemedi. Resend ayarlarını kontrol edin.")
        if choices.get("telegram_enabled") and settings.get("telegram_enabled"):
            try:
                self._send_telegram(settings, subject, message)
                channels.append("telegram")
            except Exception:
                errors.append("Telegram teslim edilemedi. Bot token ve Chat ID'yi kontrol edin.")
        if not channels and not errors:
            errors.append("Seçili bildirim kanalı etkin değil.")
        status = "sent" if channels and not errors else "partial" if channels else "failed"
        self._db.save_notification_event(kind, subject, message, channels, status)
        return {"status": status, "channels": channels, "errors": errors}

    @staticmethod
    def _send_email(settings: dict, subject: str, message: str) -> None:
        if not settings.get("resend_api_key") or not settings.get("email") or not settings.get("resend_from_email"):
            raise ValueError("Resend API anahtarı, gönderen ve alıcı e-posta zorunludur")
        response = httpx.post("https://api.resend.com/emails", timeout=15,
            headers={"Authorization": f"Bearer {settings['resend_api_key']}"},
            json={"from": settings["resend_from_email"], "to": [settings["email"]],
                  "subject": subject, "text": message})
        response.raise_for_status()

    @staticmethod
    def _send_telegram(settings: dict, subject: str, message: str) -> None:
        if not settings.get("telegram_bot_token") or not settings.get("telegram_chat_id"):
            raise ValueError("Telegram bot token ve chat ID zorunludur")
        response = httpx.post(
            f"https://api.telegram.org/bot{settings['telegram_bot_token']}/sendMessage", timeout=15,
            json={"chat_id": settings["telegram_chat_id"], "text": f"{subject}\n\n{message}"})
        response.raise_for_status()
