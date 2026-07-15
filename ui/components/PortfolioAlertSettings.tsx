"use client";

import { useEffect, useState } from "react";
import { getPortfolioAlert, savePortfolioAlert, testPortfolioAlert } from "@/lib/api";

export function PortfolioAlertSettings({ portfolioId }: { portfolioId: string }) {
  const [threshold, setThreshold] = useState(2);
  const [email, setEmail] = useState(true);
  const [telegram, setTelegram] = useState(true);
  const [enabled, setEnabled] = useState(false);
  const [message, setMessage] = useState("");
  useEffect(() => { getPortfolioAlert(portfolioId).then((alert) => {
    if (!alert) return;
    setThreshold(alert.threshold_pct); setEmail(alert.email_enabled);
    setTelegram(alert.telegram_enabled); setEnabled(alert.enabled);
  }).catch(() => setMessage("Alarm ayarı alınamadı.")); }, [portfolioId]);
  async function save() {
    setMessage("");
    try { await savePortfolioAlert(portfolioId, { threshold_pct: threshold,
      email_enabled: email, telegram_enabled: telegram, enabled }); setMessage("Portföy alarmı kaydedildi."); }
    catch { setMessage("Portföy alarmı kaydedilemedi."); }
  }
  async function test() {
    setMessage("");
    try { const result = await testPortfolioAlert(portfolioId); setMessage(result.status === "sent" ? `Test gönderildi: ${result.channels.join(", ")}` : result.errors.join(" · ")); }
    catch { setMessage("Önce alarmı kaydedin ve bildirim ayarlarını kontrol edin."); }
  }
  return <details className="portfolio-alert-settings">
    <summary>15 dakikalık hareket bildirimi</summary>
    <div className="form-row">
      <label className="check-row"><input type="checkbox" checked={enabled} onChange={(e) => setEnabled(e.target.checked)} /> Alarm etkin</label>
      <label className="field">Değişim eşiği (%)<input type="number" min="0.1" max="100" step="0.1" value={threshold} onChange={(e) => setThreshold(Number(e.target.value))} /></label>
      {[1, 2, 3, 5, 10].map((value) => <button type="button" className="btn sm" key={value} onClick={() => setThreshold(value)}>%{value}</button>)}
      <label className="check-row"><input type="checkbox" checked={email} onChange={(e) => setEmail(e.target.checked)} /> E-posta</label>
      <label className="check-row"><input type="checkbox" checked={telegram} onChange={(e) => setTelegram(e.target.checked)} /> Telegram</label>
      <button type="button" className="btn primary sm" onClick={save}>Kaydet</button>
      <button type="button" className="btn sm" onClick={test}>Test et</button>
    </div>
    <p className="muted small">Her pozisyonun fiyatı önceki 15 dakikalık gözlemle karşılaştırılır. Eşik yukarı veya aşağı yönde aşılırsa bildirim gönderilir.</p>
    {message && <p className="note" role="status">{message}</p>}
  </details>;
}
