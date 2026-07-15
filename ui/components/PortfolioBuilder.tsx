"use client";

// Build a portfolio: name it, then add rows of {ticker, cash amount}. On submit
// we create the portfolio and invest the cash per ticker at the market price
// (the API buys at the real fill price -- model-independent).

import { useState } from "react";
import { createPortfolio, invest } from "@/lib/api";
import type { InvestEntry, PortfolioKind } from "@/lib/types";

interface Props {
  kind: PortfolioKind;
  onCreated: () => void;
}

interface Row {
  ticker: string;
  cash: string;
}

const emptyRow = (): Row => ({ ticker: "", cash: "" });

export function PortfolioBuilder({ kind, onCreated }: Props) {
  const [name, setName] = useState("");
  const [rows, setRows] = useState<Row[]>([emptyRow()]);
  const [date, setDate] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function setRow(i: number, patch: Partial<Row>) {
    setRows((rs) => rs.map((r, j) => (j === i ? { ...r, ...patch } : r)));
  }
  function addRow() {
    setRows((rs) => [...rs, emptyRow()]);
  }
  function removeRow(i: number) {
    setRows((rs) => (rs.length > 1 ? rs.filter((_, j) => j !== i) : rs));
  }

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);

    if (!name.trim()) {
      setError("Portföy adı girin.");
      return;
    }
    const entries: InvestEntry[] = [];
    for (const r of rows) {
      const t = r.ticker.trim().toUpperCase();
      const cash = Number(r.cash);
      if (!t && !r.cash) continue; // skip fully empty row
      if (!t) {
        setError("Her satır için bir hisse sembolü girin.");
        return;
      }
      if (!Number.isFinite(cash) || cash <= 0) {
        setError(`${t} için sıfırdan büyük bir nakit tutarı girin.`);
        return;
      }
      entries.push({ ticker: t, cash });
    }
    if (entries.length === 0) {
      setError("Nakit tutarıyla birlikte en az bir hisse sembolü ekleyin.");
      return;
    }

    setBusy(true);
    try {
      const pf = await createPortfolio(name.trim(), kind);
      await invest(pf.id, { entries, date: date || undefined });
      setName("");
      setRows([emptyRow()]);
      setDate("");
      onCreated();
    } catch (err) {
      setError("Portföy oluşturulamadı. Lütfen tekrar deneyin.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <form className="card builder" onSubmit={submit}>
      <h3>Yeni {kind === "actual" ? "gerçek" : "simülasyon"} portföyü</h3>
      <div className="form-row">
        <label className="field" style={{ flex: 2 }}>
          Ad
          <input
            aria-label="Portföy adı"
            placeholder="Portföyüm"
            value={name}
            onChange={(e) => setName(e.target.value)}
          />
        </label>
        <label className="field">
          Alım tarihi (isteğe bağlı)
          <input
            aria-label="Alım tarihi"
            type="date"
            value={date}
            onChange={(e) => setDate(e.target.value)}
          />
        </label>
      </div>

      {rows.map((r, i) => (
        <div className="entry-row" key={i}>
          <input
            aria-label={`Hisse sembolü ${i + 1}`}
            placeholder="AAPL"
            value={r.ticker}
            onChange={(e) => setRow(i, { ticker: e.target.value })}
          />
          <input
            aria-label={`Nakit ${i + 1}`}
            placeholder="Nakit (USD)"
            inputMode="decimal"
            value={r.cash}
            onChange={(e) => setRow(i, { cash: e.target.value })}
          />
          <button
            type="button"
            className="icon-x"
            aria-label={`${i + 1}. satırı kaldır`}
            onClick={() => removeRow(i)}
          >
            ×
          </button>
        </div>
      ))}

      <div className="form-row">
        <button type="button" className="btn sm" onClick={addRow}>
          + Hisse ekle
        </button>
        <button type="submit" className="btn primary" disabled={busy}>
          {busy ? "Oluşturuluyor…" : "Portföy oluştur"}
        </button>
      </div>

      {error && <p className="note neg" role="alert">{error}</p>}
    </form>
  );
}
