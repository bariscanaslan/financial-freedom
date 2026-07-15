"use client";

import { useEffect, useState } from "react";
import { createWatchlistAlert, deleteWatchlistAlert, getWatchlistQuote, listWatchlist } from "@/lib/api";
import { money } from "@/lib/format";
import type { WatchlistAlert } from "@/lib/types";

const SUGGESTIONS = [1, 3, 5, 10];

export default function WatchlistPage() {
  const [alerts, setAlerts] = useState<WatchlistAlert[]>([]);
  const [ticker, setTicker] = useState("");
  const [direction, setDirection] = useState<"above" | "below">("above");
  const [target, setTarget] = useState("");
  const [quote, setQuote] = useState<number | null>(null);
  const [email, setEmail] = useState(true);
  const [telegram, setTelegram] = useState(true);
  const [message, setMessage] = useState("");
  const load = () => listWatchlist().then((data) => setAlerts(data.alerts)).catch(() => setMessage("Takip listesi yüklenemedi."));
  useEffect(() => { load(); }, []);

  async function findQuote() {
    setMessage("");
    try { const result = await getWatchlistQuote(ticker.trim().toUpperCase()); setTicker(result.ticker); setQuote(result.price); setTarget(result.price.toFixed(2)); }
    catch { setMessage("Güncel fiyat alınamadı."); }
  }
  function suggest(percent: number) {
    if (quote === null) return;
    const factor = direction === "above" ? 1 + percent / 100 : 1 - percent / 100;
    setTarget((quote * factor).toFixed(2));
  }
  async function add(e: React.FormEvent) {
    e.preventDefault(); setMessage("");
    try { await createWatchlistAlert({ ticker: ticker.trim().toUpperCase(), direction, target_price: Number(target), email_enabled: email, telegram_enabled: telegram });
      setTarget(""); setQuote(null); setMessage("Takip alarmı eklendi."); await load();
    } catch { setMessage("Takip alarmı eklenemedi."); }
  }
  async function remove(id: string) { if (!window.confirm("Bu takip alarmını silmek istediğinizden emin misiniz?")) return; await deleteWatchlistAlert(id); await load(); }

  return <div>
    <h1>Takip Listesi</h1>
    <p className="lead">Bir hissenin belirlediğiniz fiyatın üzerine çıkması veya altına düşmesi halinde seçtiğiniz kanallardan bir kez bildirim alın.</p>
    <form className="card watchlist-form" onSubmit={add}>
      <div className="form-row">
        <label className="field">Sembol<input value={ticker} onChange={(e) => setTicker(e.target.value.toUpperCase())} placeholder="AAPL" required /></label>
        <button type="button" className="btn primary sm" onClick={findQuote}>Güncel fiyatı getir</button>
        <label className="field">Koşul<select value={direction} onChange={(e) => setDirection(e.target.value as "above" | "below")}><option value="above">Fiyat yükselirse</option><option value="below">Fiyat düşerse</option></select></label>
        <label className="field">Hedef fiyat<input type="number" min="0.01" step="0.01" value={target} onChange={(e) => setTarget(e.target.value)} required /></label>
      </div>
      {quote !== null && <div className="suggestion-row"><span>Güncel: {money(quote)}</span>{SUGGESTIONS.map((value) => <button type="button" className="btn sm" key={value} onClick={() => suggest(value)}>%{value}</button>)}</div>}
      <div className="form-row"><label className="check-row"><input type="checkbox" checked={email} onChange={(e) => setEmail(e.target.checked)} /> E-posta</label><label className="check-row"><input type="checkbox" checked={telegram} onChange={(e) => setTelegram(e.target.checked)} /> Telegram</label><button className="btn primary">Takibe ekle</button></div>
      {message && <p className="note" role="status">{message}</p>}
    </form>
    <div className="table-scroll"><table className="data-table"><thead><tr><th className="left">Sembol</th><th>Koşul</th><th>Hedef</th><th>Son fiyat</th><th>Kanallar</th><th>Durum</th><th>İşlem</th></tr></thead><tbody>
      {alerts.map((alert) => <tr key={alert.id}><td className="left"><strong>{alert.ticker}</strong></td><td>{alert.direction === "above" ? "Üzerine çıkarsa" : "Altına düşerse"}</td><td>{money(alert.target_price)}</td><td>{money(alert.last_price)}</td><td>{[alert.email_enabled && "E-posta", alert.telegram_enabled && "Telegram"].filter(Boolean).join(" · ") || "—"}</td><td><span className={`chip ${alert.active ? "accent" : ""}`}>{alert.active ? "İzleniyor" : "Tetiklendi"}</span></td><td><button className="btn danger sm" onClick={() => remove(alert.id)}>Sil</button></td></tr>)}
    </tbody></table></div>
  </div>;
}
