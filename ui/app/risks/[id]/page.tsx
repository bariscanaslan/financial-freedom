"use client";

import { useParams, useRouter } from "next/navigation";
import { deleteRisk, getRisk } from "@/lib/api";
import { money, num, pct, signedPct } from "@/lib/format";
import { useAsync } from "@/lib/useAsync";
import { ErrorView, Loading } from "@/components/States";
import { ForecastBand } from "@/components/ForecastBand";
import { CorrelationWarning } from "@/components/CorrelationWarning";

export default function RiskDetailPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const state = useAsync(() => getRisk(params.id), [params.id]);

  async function remove() {
    if (!window.confirm("Bu risk kaydını silmek istediğinizden emin misiniz?")) return;
    await deleteRisk(params.id);
    router.push("/risks");
  }

  if (state.status === "loading") return <Loading />;
  if (state.status === "error") return <ErrorView error={state.error} />;
  const saved = state.data;
  const risk = saved.risk;
  const tickers = risk.correlation ? Object.keys(risk.correlation) : [];

  return <div>
    <div className="form-row" style={{ justifyContent: "space-between", alignItems: "center" }}>
      <div><h1>Risk Detayı</h1><p className="muted small">
        Portföy: {saved.portfolio_id} · Kayıt: {new Date(saved.created_at).toLocaleString("tr-TR")}
      </p></div>
      <button className="btn danger" onClick={remove}>Risk Kaydını Sil</button>
    </div>
    <CorrelationWarning text={risk.warning} />
    <div className="stat-tiles">
      <div className="stat-tile"><div className="label">Güncel değer</div><div className="value">{money(risk.current_value)}</div></div>
      <div className="stat-tile"><div className="label">Medyan getiri</div><div className="value">{signedPct(risk.returns.p50)}</div></div>
      <div className="stat-tile"><div className="label">Risk aralığı</div><div className="value">{pct(risk.returns.p90 - risk.returns.p10)}</div></div>
    </div>
    <ForecastBand anchorLabel="referans" targetLabel="1 işlem günü"
      anchor={risk.current_value} lower={risk.values.p10} median={risk.values.p50}
      upper={risk.values.p90} format={money} caption="Kaydedilmiş portföy risk aralığı" />
    {risk.periods && <div className="grid-3 period-overview">{Object.values(risk.periods).map((period) =>
      <section className="card" key={period.trading_days}><h2>{period.label}</h2>
        <div className="big-number">{money(period.values.p50)}</div>
        <dl className="metric-grid"><div><dt>p10</dt><dd>{money(period.values.p10)}</dd></div>
          <div><dt>p90</dt><dd>{money(period.values.p90)}</dd></div>
          <div><dt>Medyan getiri</dt><dd>{signedPct(period.returns.p50)}</dd></div>
          <div><dt>Risk</dt><dd>{pct(period.uncertainty_pct)}</dd></div></dl>
      </section>)}</div>}
    {risk.correlation && <div className="table-scroll"><h2>Korelasyon matrisi</h2>
      <table className="data-table"><thead><tr><th className="left">Sembol</th>{tickers.map((t) => <th key={t}>{t}</th>)}</tr></thead>
      <tbody>{tickers.map((row) => <tr key={row}><th scope="row">{row}</th>{tickers.map((column) => <td key={column}>{num(risk.correlation![row][column], 3)}</td>)}</tr>)}</tbody></table>
    </div>}
  </div>;
}
