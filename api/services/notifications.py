"""15 dakikalık portföy/takip listesi kontrolleri ve bildirim teslimi."""
from __future__ import annotations

import logging
import threading
from html import escape

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
                    result = self.send(subject, message, alert, kind="portfolio",
                                       trend="up" if change > 0 else "down")
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
                    result = self.send(subject, message, alert, kind="watchlist",
                                       trend="up" if alert["direction"] == "above" else "down")
                    self._db.update_watchlist_observation(
                        alert["id"], current, triggered=result["status"] in {"sent", "partial"})
                else:
                    self._db.update_watchlist_observation(alert["id"], current)
            except Exception as exc:
                log.warning("%s takip alarmı kontrol edilemedi: %s", alert["ticker"], exc)

    def send(self, subject: str, message: str, choices: dict, *, kind: str,
             trend: str = "neutral") -> dict:
        settings = self._db.get_notification_settings(include_secrets=True)
        channels, errors = [], []
        if choices.get("email_enabled") and settings.get("email_enabled"):
            try:
                self._send_email(settings, subject, message, trend)
                channels.append("email")
            except Exception:
                errors.append("E-posta teslim edilemedi. Resend ayarlarını kontrol edin.")
        if choices.get("telegram_enabled") and settings.get("telegram_enabled"):
            try:
                self._send_telegram(settings, subject, message, trend)
                channels.append("telegram")
            except Exception:
                errors.append("Telegram teslim edilemedi. Bot token ve Chat ID'yi kontrol edin.")
        if not channels and not errors:
            errors.append("Seçili bildirim kanalı etkin değil.")
        status = "sent" if channels and not errors else "partial" if channels else "failed"
        self._db.save_notification_event(kind, subject, message, channels, status)
        return {"status": status, "channels": channels, "errors": errors}

    @staticmethod
    def _send_email(settings: dict, subject: str, message: str, trend: str) -> None:
        if not settings.get("resend_api_key") or not settings.get("email") or not settings.get("resend_from_email"):
            raise ValueError("Resend API anahtarı, gönderen ve alıcı e-posta zorunludur")
        icon = NotificationService._icon(trend)
        response = httpx.post("https://api.resend.com/emails", timeout=15,
            headers={"Authorization": f"Bearer {settings['resend_api_key']}"},
            json={"from": settings["resend_from_email"], "to": [settings["email"]],
                  "subject": f"{icon} {subject}",
                  "html": NotificationService._email_html(subject, message, trend)})
        response.raise_for_status()

    @staticmethod
    def _send_telegram(settings: dict, subject: str, message: str, trend: str) -> None:
        if not settings.get("telegram_bot_token") or not settings.get("telegram_chat_id"):
            raise ValueError("Telegram bot token ve chat ID zorunludur")
        response = httpx.post(
            f"https://api.telegram.org/bot{settings['telegram_bot_token']}/sendMessage", timeout=15,
            json={"chat_id": settings["telegram_chat_id"], "parse_mode": "HTML",
                  "text": NotificationService._telegram_html(subject, message, trend)})
        response.raise_for_status()

    @staticmethod
    def _icon(trend: str) -> str:
        return {"up": "📈", "down": "📉"}.get(trend, "🔔")

    @staticmethod
    def _telegram_html(subject: str, message: str, trend: str) -> str:
        icon = NotificationService._icon(trend)
        return (f"{icon} <b>{escape(subject)}</b>\n\n{escape(message)}\n\n"
                "<i>Financial Freedom · Otomatik piyasa bildirimi</i>")

    @staticmethod
    def _email_html(subject: str, message: str, trend: str) -> str:
        icon = NotificationService._icon(trend)
        accent = "#16a34a" if trend == "up" else "#dc2626" if trend == "down" else "#b91c1c"
        label = "Yükseliş" if trend == "up" else "Düşüş" if trend == "down" else "Bildirim"
        return f"""<!doctype html>
<html lang="tr"><body style="margin:0;background:#f6f7fb;font-family:Inter,Arial,sans-serif;color:#172033">
<table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="padding:32px 12px;background:#f6f7fb"><tr><td align="center">
<table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="max-width:600px;background:#fff;border:1px solid #e3e7ef;border-radius:18px;overflow:hidden;box-shadow:0 12px 32px rgba(23,32,51,.08)">
<tr><td style="padding:22px 26px;background:#b91c1c;color:#fff"><div style="font-size:12px;font-weight:700;letter-spacing:.12em;text-transform:uppercase;opacity:.85">Financial Freedom</div><div style="margin-top:8px;font-size:24px;font-weight:800;line-height:1.25">{icon} {escape(subject)}</div></td></tr>
<tr><td style="padding:26px"><span style="display:inline-block;padding:6px 11px;border-radius:999px;background:{accent}18;color:{accent};font-size:12px;font-weight:800">{icon} {label}</span><p style="margin:18px 0 0;font-size:16px;line-height:1.7;color:#344054">{escape(message)}</p><div style="margin-top:24px;padding:14px 16px;border-left:4px solid #dc2626;border-radius:8px;background:#fff7f7;color:#667085;font-size:12px;line-height:1.55">Bu otomatik bir piyasa takip bildirimidir ve yatırım tavsiyesi değildir.</div></td></tr>
<tr><td style="padding:16px 26px;border-top:1px solid #edf0f5;color:#98a2b3;font-size:11px">Bildirim ayarlarınızı Financial Freedom üzerinden yönetebilirsiniz.</td></tr>
</table></td></tr></table></body></html>"""
