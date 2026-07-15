"use client";

import { useState } from "react";
import { useAsync } from "@/lib/useAsync";
import { getForecast, getModels, getPositions, listPortfolios, saveRisk } from "@/lib/api";
import { money, pct, num } from "@/lib/format";
import { CorrelationWarning } from "@/components/CorrelationWarning";
import { ForecastBand } from "@/components/ForecastBand";
import { Empty, ErrorView, Loading } from "@/components/States";
import type {
  ModelsResponse,
  PortfolioForecastResponse,
  PositionsResponse,
} from "@/lib/types";
import { SortHeader } from "@/components/SortHeader";
import { useSortable } from "@/lib/useSortable";

interface RiskData {
  forecast: PortfolioForecastResponse;
  positions: PositionsResponse;
  models: ModelsResponse;
}

async function load(id: string): Promise<RiskData> {
  const [forecast, positions, models] = await Promise.all([
    getForecast(id),
    getPositions(id),
    getModels(),
  ]);
  return { forecast, positions, models };
}

export default function RiskPage() {
  const list = useAsync(listPortfolios, []);
  const [id, setId] = useState<string>("");

  return (
    <div>
      <h1>Portföy Riski</h1>
      <p className="lead">
        Portföy düzeyinde 1 günlük değer aralığı. Yeterli ortak geçmiş varsa
        pozisyonlar arası korelasyon hesaba katılır; kullanılan yöntem sonuçta gösterilir.
      </p>

      {list.status === "loading" && <Loading />}
      {list.status === "error" && <ErrorView error={list.error} />}
      {list.status === "ready" &&
        (list.data.portfolios.length === 0 ? (
          <Empty message="Henüz portföy yok. Portföy sayfasından oluşturabilirsiniz." />
        ) : (
          <RiskSection
            options={list.data.portfolios.map((p) => ({ id: p.id, label: `${p.name} (${p.kind})` }))}
            id={id || list.data.portfolios[0].id}
            onSelect={setId}
          />
        ))}
    </div>
  );
}

function RiskSection({
  options,
  id,
  onSelect,
}: {
  options: { id: string; label: string }[];
  id: string;
  onSelect: (id: string) => void;
}) {
  const state = useAsync(() => load(id), [id]);
  return (
    <div>
      <label className="field" style={{ maxWidth: 320 }}>
        Portföy
        <select value={id} onChange={(e) => onSelect(e.target.value)}>
          {options.map((o) => (
            <option key={o.id} value={o.id}>
              {o.label}
            </option>
          ))}
        </select>
      </label>

      {state.status === "loading" && <Loading />}
      {state.status === "error" && <ErrorView error={state.error} />}
      {state.status === "ready" && <RiskView data={state.data} portfolioId={id} />}
    </div>
  );
}

function RiskView({ data, portfolioId }: { data: RiskData; portfolioId: string }) {
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const f = data.forecast;
  const held = Object.keys(
    data.positions.positions.reduce<Record<string, true>>(
      (acc, p) => ((acc[p.ticker] = true), acc),
      {},
    ),
  );
  const coverageByTicker = new Map(data.models.models.map((m) => [m.ticker, m]));
  const calibration = held.map((ticker) => ({ ticker, model: coverageByTicker.get(ticker) }));
  const table = useSortable(calibration, {
    ticker: (row) => row.ticker,
    coverage: (row) => row.model?.coverage,
    target: (row) => row.model?.nominal_cov,
    skill: (row) => row.model?.skill_score,
  }, "ticker");

  if (held.length === 0) {
    return <Empty message="Açık pozisyon olmadığı için portföy riski hesaplanmadı." />;
  }

  return (
    <div>
      {/* A4: warning BEFORE the band and non-silenceable */}
      <CorrelationWarning text={f.warning} />

      <p className="muted small">
        Yöntem: {f.method === "historical_correlation" ? "Tarihsel korelasyon" : "İhtiyatlı korelasyon varsayımı"}
      </p>

      <div className="stat-tiles">
        <div className="stat-tile">
          <div className="label">Güncel değer</div>
          <div className="value mono">{money(f.current_value)}</div>
        </div>
        <div className="stat-tile">
          <div className="label">1 günlük aralık (p90 − p10)</div>
          <div className="value mono">{money(f.values.p90 - f.values.p10)}</div>
        </div>
      </div>

      <ForecastBand
        anchorLabel="bugün"
        targetLabel="yarın"
        anchor={f.current_value}
        lower={f.values.p10}
        median={f.values.p50}
        upper={f.values.p90}
        format={(x) => money(x)}
        caption="Portföyün 1 günlük değer aralığı"
      />

      {f.periods && Object.keys(f.periods).length > 0 && <div className="grid-3 period-overview">
        {Object.values(f.periods).map((period) => <section className="card" key={period.trading_days}>
          <h2>{period.label}</h2>
          <div className="big-number">{money(period.values.p50)}</div>
          <p className="muted small">{period.trading_days} işlem günü medyan değeri</p>
          <dl className="metric-grid">
            <div><dt>p10</dt><dd>{money(period.values.p10)}</dd></div>
            <div><dt>p50</dt><dd>{money(period.values.p50)}</dd></div>
            <div><dt>p90</dt><dd>{money(period.values.p90)}</dd></div>
            <div><dt>Risk</dt><dd>{pct(period.uncertainty_pct)}</dd></div>
          </dl>
        </section>)}
      </div>}

      <h2>Pozisyon kalibrasyonu</h2>
      <div className="table-scroll">
        <table className="data-table">
          <thead>
            <tr>
              <SortHeader label="Sembol" column="ticker" active={table.key === "ticker"} direction={table.direction} onSort={table.sort} left />
              <SortHeader label="Kapsama" column="coverage" active={table.key === "coverage"} direction={table.direction} onSort={table.sort} />
              <SortHeader label="Hedef" column="target" active={table.key === "target"} direction={table.direction} onSort={table.sort} />
              <SortHeader label="skill_score" column="skill" active={table.key === "skill"} direction={table.direction} onSort={table.sort} />
            </tr>
          </thead>
          <tbody>
            {table.sorted.map(({ ticker: t, model: m }) => {
              return (
                <tr key={t}>
                  <th scope="row">{t}</th>
                  <td>{m ? pct(m.coverage, 1) : "—"}</td>
                  <td>{m ? pct(m.nominal_cov, 0) : "—"}</td>
                  <td>{m ? num(m.skill_score, 4) : "model yok"}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <p className="muted small">
        Kapsama hedefin altındaysa risk olduğundan düşük gösterilir. Bu tablo
        yalnızca açıklama amaçlıdır; işlem önerisi değildir.
      </p>

      {f.correlation && <CorrelationTable matrix={f.correlation} />}

      <button className="btn primary" disabled={saving || saved} onClick={async () => {
        setSaving(true);
        try { await saveRisk(portfolioId); setSaved(true); }
        finally { setSaving(false); }
      }}>
        {saving ? "Kaydediliyor…" : saved ? "Risk kaydedildi" : "Riski Kaydet"}
      </button>
    </div>
  );
}

function CorrelationTable({ matrix }: { matrix: Record<string, Record<string, number>> }) {
  const tickers = Object.keys(matrix);
  return (
    <div className="table-scroll">
      <h2>Korelasyon matrisi</h2>
      <table className="data-table">
        <thead><tr><th className="left">Sembol</th>{tickers.map((ticker) => <th key={ticker}>{ticker}</th>)}</tr></thead>
        <tbody>{tickers.map((row) => (
          <tr key={row}><th scope="row">{row}</th>{tickers.map((column) => <td key={column}>{num(matrix[row][column], 3)}</td>)}</tr>
        ))}</tbody>
      </table>
    </div>
  );
}
