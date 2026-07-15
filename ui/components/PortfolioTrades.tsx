"use client";

import { useState } from "react";
import { createTrade } from "@/lib/api";
import { money, shares } from "@/lib/format";
import type { Trade } from "@/lib/types";
import { useSortable } from "@/lib/useSortable";
import { SortHeader } from "./SortHeader";

export function PortfolioTrades({ portfolioId, trades, tickers, onChanged }: {
  portfolioId: string; trades: Trade[]; tickers: { ticker: string; name?: string }[]; onChanged: () => void;
}) {
  const [side, setSide] = useState<"BUY" | "SELL">("BUY");
  const [ticker, setTicker] = useState("");
  const [amount, setAmount] = useState("");
  const [date, setDate] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const table = useSortable(trades, {
    date: (trade) => trade.timestamp, ticker: (trade) => trade.ticker,
    side: (trade) => trade.side, quantity: (trade) => trade.quantity,
    price: (trade) => trade.price, value: (trade) => trade.cash_value,
    fees: (trade) => trade.fees,
  }, "date");

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    const value = Number(amount);
    if (!ticker.trim() || !Number.isFinite(value) || value <= 0) {
      setError("Geçerli bir sembol ve pozitif tutar girin."); return;
    }
    setBusy(true); setError(null);
    try {
      await createTrade(portfolioId, { side, ticker: ticker.trim().toUpperCase(), amount: value, date: date || undefined });
      setTicker(""); setAmount(""); setDate(""); onChanged();
    } catch (err) {
      setError(err instanceof Error ? err.message : "İşlem kaydedilemedi.");
    } finally { setBusy(false); }
  }

  return <div className="card" style={{ marginTop: "1rem" }}>
    <h3>Portföyü düzenle</h3>
    <form className="form-row" onSubmit={submit}>
      <label className="field">İşlem<select value={side} onChange={(e) => setSide(e.target.value as "BUY" | "SELL")}><option value="BUY">Alım</option><option value="SELL">Satım</option></select></label>
      <label className="field">Sembol<select value={ticker} onChange={(e) => setTicker(e.target.value)}><option value="">Sembol seçin</option>{tickers.map((item) => <option key={item.ticker} value={item.ticker}>{item.ticker}{item.name ? ` - ${item.name}` : ""}</option>)}</select></label>
      <label className="field">{side === "BUY" ? "Nakit (USD)" : "Adet"}<input inputMode="decimal" value={amount} onChange={(e) => setAmount(e.target.value)} /></label>
      <label className="field">Tarih (isteğe bağlı)<input type="date" value={date} onChange={(e) => setDate(e.target.value)} /></label>
      <button className="btn primary" disabled={busy}>{busy ? "Kaydediliyor…" : "İşlemi Kaydet"}</button>
    </form>
    {error && <p className="note neg" role="alert">{error}</p>}
    <h3 style={{ marginTop: "1rem" }}>İşlem geçmişi</h3>
    {trades.length === 0 ? <p className="muted small">Henüz işlem yok.</p> : <div className="table-scroll"><table className="data-table">
      <thead><tr>
        <SortHeader label="Tarih" column="date" active={table.key === "date"} direction={table.direction} onSort={table.sort} left />
        <SortHeader label="Sembol" column="ticker" active={table.key === "ticker"} direction={table.direction} onSort={table.sort} />
        <SortHeader label="İşlem" column="side" active={table.key === "side"} direction={table.direction} onSort={table.sort} />
        <SortHeader label="Adet" column="quantity" active={table.key === "quantity"} direction={table.direction} onSort={table.sort} />
        <SortHeader label="Fiyat" column="price" active={table.key === "price"} direction={table.direction} onSort={table.sort} />
        <SortHeader label="Tutar" column="value" active={table.key === "value"} direction={table.direction} onSort={table.sort} />
        <SortHeader label="Masraf" column="fees" active={table.key === "fees"} direction={table.direction} onSort={table.sort} />
      </tr></thead>
      <tbody>{table.sorted.map((trade, index) => <tr key={`${trade.timestamp}-${trade.ticker}-${index}`}>
        <td>{new Date(trade.timestamp).toLocaleDateString("tr-TR")}</td><th scope="row">{trade.ticker}</th>
        <td>{trade.side === "BUY" ? "Alım" : "Satım"}</td><td>{shares(trade.quantity)}</td>
        <td>{money(trade.price)}</td><td>{money(trade.cash_value)}</td><td>{money(trade.fees)}</td>
      </tr>)}</tbody>
    </table></div>}
  </div>;
}
