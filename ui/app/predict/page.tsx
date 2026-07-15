"use client";

import { useEffect, useState } from "react";
import { ApiError, getModels, predict, savePrediction } from "@/lib/api";
import { money, pct, signedPct, signClass, simpleReturn } from "@/lib/format";
import { RiskBadge } from "@/components/RiskBadge";
import { ErrorView, ModelMissing } from "@/components/States";
import type { ForecastResponse } from "@/lib/types";

const TICKER_RE = /^[A-Z][A-Z0-9.\-]{0,9}$/;

type View =
  | { status: "idle" }
  | { status: "loading" }
  | { status: "missing"; ticker: string }
  | { status: "error"; error: unknown }
  | { status: "ready"; data: ForecastResponse };

export default function PredictPage() {
  const [ticker, setTicker] = useState("");
  const [view, setView] = useState<View>({ status: "idle" });
  const [inputError, setInputError] = useState<string | null>(null);
  const [trainedTickers, setTrainedTickers] = useState<string[]>([]);

  useEffect(() => {
    getModels().then((response) => {
      setTrainedTickers([...new Set(
        response.models.map((model) => model.ticker).filter((value): value is string => Boolean(value)),
      )].sort());
    }).catch(() => setInputError("Eğitilmiş model listesi alınamadı."));
  }, []);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    const t = ticker.trim().toUpperCase();
    // Client-side pre-check -- the real gate is the API (this only warns early).
    if (!TICKER_RE.test(t)) {
      setInputError("Geçersiz hisse sembolü biçimi (ör. AAPL). ");
      return;
    }
    if (trainedTickers.length > 0 && !trainedTickers.includes(t)) {
      setInputError("Yalnızca eğitilmiş modeli bulunan bir hisse seçebilirsiniz.");
      return;
    }
    setInputError(null);
    setView({ status: "loading" });
    try {
      const data = await predict(t);
      setView({ status: "ready", data });
    } catch (err) {
      if (err instanceof ApiError && err.isModelMissing) {
        setView({ status: "missing", ticker: t });
      } else {
        setView({ status: "error", error: err });
      }
    }
  }

  return (
    <div>
      <h1>Tahmin</h1>
      <p className="lead">
        Bir NASDAQ hisse sembolü girin. Çıktı bir işlem önerisi değil,
        p10/p50/p90 dağılımıdır. Eğitilmiş model olmadan tahmin üretilmez.
      </p>

      <form className="search" onSubmit={submit}>
        <input
          aria-label="Hisse sembolü"
          placeholder="Eğitilmiş model ara"
          list="trained-model-tickers"
          value={ticker}
          onChange={(e) => setTicker(e.target.value)}
        />
        <datalist id="trained-model-tickers">
          {trainedTickers.map((value) => <option key={value} value={value} />)}
        </datalist>
        <button type="submit" className="btn primary">Tahmin et</button>
      </form>
      {inputError && <p className="note neg">{inputError}</p>}

      {view.status === "loading" && <p className="state muted">Hesaplanıyor…</p>}
      {view.status === "missing" && <ModelMissing ticker={view.ticker} />}
      {view.status === "error" && <ErrorView error={view.error} />}
      {view.status === "ready" && <ForecastResult data={view.data} />}
    </div>
  );
}

function ForecastResult({ data }: { data: ForecastResponse }) {
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const periods = data.periods && Object.keys(data.periods).length > 0
    ? Object.values(data.periods)
    : [{
        label: "Günlük", trading_days: 1, returns: data.returns,
        prices: data.prices, uncertainty: data.uncertainty,
        uncertainty_pct: data.uncertainty_pct,
      }];

  async function save() {
    setSaving(true);
    setSaveError(null);
    try {
      await savePrediction(data.ticker);
      setSaved(true);
    } catch {
      setSaveError("Tahmin kaydedilemedi.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div>
      <h2>
        {data.ticker} · {data.as_of}
      </h2>

      <div className="stat-tiles">
        <div className="stat-tile">
          <div className="label">Referans fiyat</div>
          <div className="value mono">{money(data.anchor_price)}</div>
        </div>
      </div>

      <div className="grid-3 period-overview">
        {periods.map((period) => (
          <section className="card" key={period.trading_days}>
            <h2>{period.label}</h2>
            <div className={`big-number ${signClass(period.returns.p50)}`}>{signedPct(simpleReturn(period.returns.p50))}</div>
            <p className="muted small">Medyan getiri · {period.trading_days} işlem günü</p>
            <dl className="metric-grid">
              <div><dt>p10 fiyat</dt><dd>{money(period.prices.p10)}</dd></div>
              <div><dt>p50 fiyat</dt><dd>{money(period.prices.p50)}</dd></div>
              <div><dt>p90 fiyat</dt><dd>{money(period.prices.p90)}</dd></div>
              <div><dt>Risk aralığı</dt><dd>{pct(period.uncertainty_pct)}</dd></div>
            </dl>
          </section>
        ))}
      </div>

      <div className="table-scroll">
        <table className="data-table">
          <caption className="muted" style={{ textAlign: "left" }}>
            Getiri alanı (modelin gerçekten tahmin ettiği değer)
          </caption>
          <tbody>
            <tr><th scope="row" className="left">p10</th><td className={signClass(data.returns.p10)}>{signedPct(simpleReturn(data.returns.p10))}</td></tr>
            <tr><th scope="row" className="left">p50 (medyan)</th><td className={signClass(data.returns.p50)}>{signedPct(simpleReturn(data.returns.p50))}</td></tr>
            <tr><th scope="row" className="left">p90</th><td className={signClass(data.returns.p90)}>{signedPct(simpleReturn(data.returns.p90))}</td></tr>
            <tr>
              <th scope="row" className="left">risk (p90 − p10)</th>
              <td>{money(data.uncertainty)} ({pct(data.uncertainty_pct)})</td>
            </tr>
          </tbody>
        </table>
      </div>

      <RiskBadge meta={data.meta} />
      <p className="muted small">{data.meta.note}</p>
      <button className="btn primary" onClick={save} disabled={saving || saved}>
        {saving ? "Kaydediliyor…" : saved ? "Tahmin kaydedildi" : "Tahmini Kaydet"}
      </button>
      {saveError && <p className="note neg">{saveError}</p>}
    </div>
  );
}
