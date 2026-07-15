"use client";

import { useEffect, useState } from "react";
import {
  ApiError,
  getTrainingCatalog,
  getTrainingDevice,
  getTrainingStatus,
  refreshMarketCache,
  startTraining,
} from "@/lib/api";
import type { TrainingJobResponse } from "@/lib/types";
import { useAsync } from "@/lib/useAsync";
import { ErrorView, Loading } from "@/components/States";
import { SortHeader } from "@/components/SortHeader";
import { useSortable } from "@/lib/useSortable";

const TICKER_RE = /^[A-Z][A-Z0-9.\-]{0,9}$/;
const TERMINAL = new Set(["completed", "failed"]);

function number(value: unknown, digits = 6): string {
  return typeof value === "number" ? value.toFixed(digits) : "—";
}

export default function TrainPage() {
  const [ticker, setTicker] = useState("");
  const [horizon, setHorizon] = useState("21");
  const [device, setDevice] = useState<string | null>(null);
  const [job, setJob] = useState<TrainingJobResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [refreshing, setRefreshing] = useState(false);
  const [cacheMessage, setCacheMessage] = useState<string | null>(null);
  const catalog = useAsync(getTrainingCatalog, []);

  useEffect(() => {
    getTrainingDevice().then((data) => setDevice(data.device)).catch(() => {
      setError("Eğitim cihazı bilgisi alınamadı.");
    });
  }, []);

  useEffect(() => {
    if (!job || TERMINAL.has(job.status)) return;
    const timer = window.setInterval(async () => {
      try {
        setJob(await getTrainingStatus(job.id));
      } catch {
        setError("Eğitim durumu güncellenemedi.");
      }
    }, 1000);
    return () => window.clearInterval(timer);
  }, [job?.id, job?.status]);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    const value = ticker.trim().toUpperCase();
    if (!TICKER_RE.test(value)) {
      setError("Geçerli bir hisse sembolü girin (ör. AAPL). ");
      return;
    }
    setError(null);
    try {
      setJob(await startTraining(value, Number(horizon)));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Eğitim başlatılamadı.");
    }
  }

  async function refreshCache() {
    const value = ticker.trim().toUpperCase();
    if (!TICKER_RE.test(value)) {
      setError("Cache yenilemek için geçerli bir hisse sembolü seçin."); return;
    }
    setRefreshing(true); setError(null); setCacheMessage(null);
    try {
      const result = await refreshMarketCache(value);
      setCacheMessage(`${result.ticker} cache yenilendi: ${result.first_date} – ${result.last_date} (${result.rows} satır).`);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Cache yenilenemedi.");
    } finally { setRefreshing(false); }
  }

  const running = job !== null && !TERMINAL.has(job.status);

  return (
    <div>
      <h1>Model Eğitimi</h1>
      <p className="lead">
        Bir hisse sembolü girerek QuantileLSTM eğitimini başlatın. Eğitim yalnızca
        veri kalite kontrolleri geçilirse çalışır; test verisi eğitim sırasında kullanılmaz.
      </p>

      <div className="stat-tiles">
        <div className="stat-tile">
          <div className="label">Eğitim cihazı</div>
          <div className="value mono">{device ?? "Belirleniyor…"}</div>
        </div>
      </div>

      <form className="search" onSubmit={submit}>
        <input
          aria-label="Eğitilecek hisse sembolü"
          placeholder="AAPL"
          value={ticker}
          disabled={running}
          onChange={(event) => setTicker(event.target.value)}
        />
        <label className="field">Model ufku<select value={horizon} disabled={running} onChange={(event) => setHorizon(event.target.value)}><option value="21">1 ay</option><option value="63">3 ay</option><option value="126">6 ay</option><option value="252">1 yıl</option><option value="504">2 yıl</option></select></label>
        <button type="submit" className="btn primary" disabled={running || !device}>
          {running ? "Eğitiliyor…" : "Eğit"}
        </button>
        <button type="button" className="btn" onClick={refreshCache} disabled={running || refreshing}>
          {refreshing ? "Cache yenileniyor…" : "Cache Yenile"}
        </button>
      </form>

      {error && <p className="state error" role="alert">{error}</p>}
      {cacheMessage && <p className="note pos" role="status">{cacheMessage}</p>}
      {job && <TrainingStatus job={job} />}

      <h2>NASDAQ-100 Şirketleri</h2>
      <p className="muted small">
        Liste 2026-07 kataloğudur. Model durumu yerel model kayıtlarından canlı hesaplanır.
      </p>
      <input
        aria-label="Şirket veya hisse ara"
        placeholder="Şirket veya sembol ara"
        value={query}
        onChange={(event) => setQuery(event.target.value)}
        style={{ width: "100%", maxWidth: 420 }}
      />
      {catalog.status === "loading" && <Loading />}
      {catalog.status === "error" && <ErrorView error={catalog.error} />}
      {catalog.status === "ready" && (
        <CatalogTable
          rows={catalog.data.tickers.filter((row) =>
            `${row.ticker} ${row.name}`.toLocaleLowerCase("tr-TR")
              .includes(query.toLocaleLowerCase("tr-TR")),
          )}
          onSelect={(value) => {
            setTicker(value);
            window.scrollTo({ top: 0, behavior: "smooth" });
          }}
        />
      )}
    </div>
  );
}

function CatalogTable({
  rows,
  onSelect,
}: {
  rows: { ticker: string; name: string; has_model: boolean; last_trained_at: string | null }[];
  onSelect: (ticker: string) => void;
}) {
  const { sorted, sort, key, direction } = useSortable(rows, {
    ticker: (row) => row.ticker,
    name: (row) => row.name,
    model: (row) => row.has_model,
    trained: (row) => row.last_trained_at,
  }, "ticker");
  return (
    <div className="table-scroll">
      <table className="data-table">
        <thead>
          <tr>
            <SortHeader label="Sembol" column="ticker" active={key === "ticker"} direction={direction} onSort={sort} left />
            <SortHeader label="Şirket" column="name" active={key === "name"} direction={direction} onSort={sort} left />
            <SortHeader label="Model durumu" column="model" active={key === "model"} direction={direction} onSort={sort} left />
            <SortHeader label="Son eğitim" column="trained" active={key === "trained"} direction={direction} onSort={sort} left />
            <th>İşlem</th>
          </tr>
        </thead>
        <tbody>
          {sorted.map((row) => (
            <tr key={row.ticker}>
              <th scope="row">{row.ticker}</th>
              <td className="left">{row.name}</td>
              <td className="left">
                <span className={`chip ${row.has_model ? "pos" : ""}`}>
                  {row.has_model ? "Model var" : "Model yok"}
                </span>
              </td>
              <td className="left">{row.last_trained_at ? new Date(row.last_trained_at).toLocaleString("tr-TR") : "—"}</td>
              <td><button className="btn sm" onClick={() => onSelect(row.ticker)}>Seç</button></td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function TrainingStatus({ job }: { job: TrainingJobResponse }) {
  const latest = job.history.at(-1);
  const progress = Math.round((job.progress ?? 0) * 100);
  const history = useSortable(job.history, {
    epoch: (row) => row.epoch,
    train: (row) => row.train_loss,
    validation: (row) => row.val_loss,
  }, "epoch");

  return (
    <section aria-live="polite">
      <h2>{job.ticker} eğitim durumu</h2>
      <div className="card">
        <div className="form-row" style={{ justifyContent: "space-between" }}>
          <strong>{job.stage}</strong>
          <span className={`chip ${job.status === "completed" ? "pos" : ""}`}>
            {statusLabel(job.status)}
          </span>
        </div>
        <progress value={progress} max={100} aria-label="Eğitim ilerlemesi" />
        <p className="muted small">%{progress} · cihaz: {job.device}</p>
        {job.error && <p className="state error">{job.error}</p>}
      </div>

      <div className="stat-tiles">
        <Stat label="Parametre" value={job.parameters?.toLocaleString("tr-TR") ?? "—"} />
        <Stat label="Epoch" value={latest ? `${latest.epoch} / ${latest.max_epochs}` : "—"} />
        <Stat label="Train loss" value={number(latest?.train_loss)} />
        <Stat label="Validation loss" value={number(latest?.val_loss)} />
        <Stat label="En iyi epoch" value={job.best_epoch?.toString() ?? "—"} />
        <Stat label="En iyi validation loss" value={number(job.best_val_loss)} />
      </div>

      {job.history.length > 0 && (
        <div className="table-scroll">
          <table className="data-table">
            <thead><tr>
              <SortHeader label="Epoch" column="epoch" active={history.key === "epoch"} direction={history.direction} onSort={history.sort} left />
              <SortHeader label="Train loss" column="train" active={history.key === "train"} direction={history.direction} onSort={history.sort} />
              <SortHeader label="Validation loss" column="validation" active={history.key === "validation"} direction={history.direction} onSort={history.sort} />
            </tr></thead>
            <tbody>
              {history.sorted.slice(-20).map((row) => (
                <tr key={row.epoch}>
                  <th scope="row">{row.epoch}</th>
                  <td>{number(row.train_loss)}</td>
                  <td>{number(row.val_loss)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {job.metrics && (
        <>
          <h2>Test sonuçları</h2>
          <div className="stat-tiles">
            <Stat label="RMSE" value={number(job.metrics.rmse_ret)} />
            <Stat label="Pinball loss" value={number(job.metrics.pinball)} />
            <Stat label="Kapsama" value={number(job.metrics.coverage, 3)} />
            <Stat label="skill_score" value={number(job.metrics.skill_score, 4)} />
          </div>
          <p className="muted small">Model kaydı: {job.model_path}</p>
        </>
      )}
    </section>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return <div className="stat-tile"><div className="label">{label}</div><div className="value mono">{value}</div></div>;
}

function statusLabel(status: TrainingJobResponse["status"]): string {
  return {
    queued: "Kuyrukta",
    preparing: "Hazırlanıyor",
    training: "Eğitiliyor",
    evaluating: "Değerlendiriliyor",
    completed: "Tamamlandı",
    failed: "Başarısız",
  }[status];
}
