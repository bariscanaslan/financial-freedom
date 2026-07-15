"use client";

import { useEffect, useState } from "react";
import { getPortfolioEvaluation, listPortfolioEvaluations, refreshAllMarketCaches } from "@/lib/api";
import { money, pct, signedPct } from "@/lib/format";
import type { PortfolioEvaluation, PortfolioEvaluationSummary } from "@/lib/types";
import { SortHeader } from "@/components/SortHeader";
import { useSortable } from "@/lib/useSortable";
import { ErrorView, Loading } from "@/components/States";

const HORIZONS: Record<string, string> = { daily: "Günlük", weekly: "Haftalık", monthly: "1 ay",
  quarterly: "3 ay", half_year: "6 ay", yearly: "1 yıl", two_year: "2 yıl" };

export default function PortfolioReportsPage() {
  const [items, setItems] = useState<PortfolioEvaluationSummary[] | null>(null);
  const [selected, setSelected] = useState("");
  const [report, setReport] = useState<PortfolioEvaluation | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [refreshing, setRefreshing] = useState(false);
  const [refreshMessage, setRefreshMessage] = useState<string | null>(null);
  useEffect(() => { listPortfolioEvaluations().then((data) => { setItems(data.evaluations); if (data.evaluations[0]) setSelected(data.evaluations[0].id); }).catch(setError); }, []);
  useEffect(() => { if (!selected) return; setReport(null); getPortfolioEvaluation(selected).then(setReport).catch(setError); }, [selected]);
  if (error) return <ErrorView error={error} />;
  if (!items) return <Loading />;
  async function refreshAll() {
    setRefreshing(true); setRefreshMessage(null); setError(null);
    try {
      const result = await refreshAllMarketCaches();
      setRefreshMessage(`${result.refreshed}/${result.total} cache yenilendi${result.failed.length ? `; başarısız: ${result.failed.join(", ")}` : "."}`);
      if (selected) setReport(await getPortfolioEvaluation(selected));
    } catch (err) { setError(err); }
    finally { setRefreshing(false); }
  }
  return <div><div className="form-row" style={{ justifyContent: "space-between", alignItems: "center" }}><h1>Portföy Tahmin–Gerçekleşen Raporu</h1><div className="cache-refresh-control"><button className="btn" onClick={refreshAll} disabled={refreshing}>{refreshing ? "Tüm cache’ler yenileniyor…" : "Tüm Cache’leri Güncelle"}</button>{refreshing && <progress aria-label="Tüm cache’leri güncelleme ilerlemesi" />}</div></div>
    <p className="lead">Portföy oluşturulduğu anda kaydedilen tahminleri, sonradan gerçekleşen günlük kapanış değerleriyle karşılaştırın.</p>
    {refreshMessage && <p className="note pos" role="status">{refreshMessage}</p>}
    {items.length === 0 ? <p className="card">Henüz değerlendirme kaydı yok. Yeni bir model destekli taslağı portföye dönüştürdüğünüzde rapor otomatik oluşur.</p> : <>
      <label className="field" style={{ maxWidth: 520 }}>Rapor<select value={selected} onChange={(event) => setSelected(event.target.value)}>{items.map((item) => <option key={item.id} value={item.id}>{item.portfolio_name} · {HORIZONS[item.horizon] ?? item.horizon} · {new Date(item.created_at).toLocaleString("tr-TR")}</option>)}</select></label>
      {!report ? <Loading /> : <Report report={report} />}
    </>}
  </div>;
}

function Report({ report }: { report: PortfolioEvaluation }) {
  const table = useSortable(report.points, { date: (row) => row.date, actual: (row) => row.actual_value,
    p10: (row) => row.predicted_p10, p50: (row) => row.predicted_p50, p90: (row) => row.predicted_p90,
    error: (row) => row.error_pct, covered: (row) => row.covered }, "date");
  const metric = (key: string) => report.metrics[key];
  function download() {
    const header = "Tarih,Gerçek Değer,Tahmin p10,Tahmin p50,Tahmin p90,Hata %,Aralık İçinde\n";
    const rows = report.points.map((row) => [row.date,row.actual_value,row.predicted_p10,row.predicted_p50,row.predicted_p90,row.error_pct,row.covered].join(",")).join("\n");
    const url = URL.createObjectURL(new Blob([header + rows], { type: "text/csv;charset=utf-8" }));
    const link = document.createElement("a"); link.href = url; link.download = `${report.portfolio_name}-karsilastirma.csv`; link.click(); URL.revokeObjectURL(url);
  }
  return <section style={{ marginTop: "1rem" }}><div className="form-row" style={{ justifyContent: "space-between" }}><div><h2>{report.portfolio_name}</h2><p className="muted small">Başlangıç: {new Date(report.as_of).toLocaleDateString("tr-TR")} · Vade: {HORIZONS[report.horizon] ?? report.horizon}</p></div><button className="btn" onClick={download} disabled={!report.points.length}>CSV Raporu İndir</button></div>
    <div className="stat-tiles">
      <Tile label="Gözlem" value={String(metric("observations") ?? 0)} /><Tile label="MAPE" value={pct(metric("mape"))} />
      <Tile label="RMSE" value={money(metric("rmse"))} /><Tile label="Aralık kapsaması" value={pct(metric("coverage"))} />
      <Tile label="Yön doğruluğu" value={pct(metric("directional_accuracy"))} /><Tile label="Gerçekleşen getiri" value={signedPct(metric("realized_return"))} />
      <Tile label="Tahmin edilen getiri" value={signedPct(metric("predicted_return"))} /><Tile label="Gerçekleşen volatilite" value={pct(metric("realized_volatility"))} />
      <Tile label="Maksimum düşüş" value={signedPct(metric("max_drawdown"))} /><Tile label="Ortalama sapma" value={signedPct(metric("bias_pct"))} />
      <Tile label="Ortalama risk aralığı" value={pct(metric("average_interval_width_pct"))} /><Tile label="Alt sınır ihlali" value={String(metric("lower_breaches") ?? 0)} /><Tile label="Üst sınır ihlali" value={String(metric("upper_breaches") ?? 0)} />
    </div><p className="note">{report.note}</p>
    <div className="table-scroll"><table className="data-table"><thead><tr>
      <SortHeader label="Tarih" column="date" active={table.key === "date"} direction={table.direction} onSort={table.sort} left />
      <SortHeader label="Gerçek değer" column="actual" active={table.key === "actual"} direction={table.direction} onSort={table.sort} />
      <SortHeader label="p10" column="p10" active={table.key === "p10"} direction={table.direction} onSort={table.sort} />
      <SortHeader label="p50" column="p50" active={table.key === "p50"} direction={table.direction} onSort={table.sort} />
      <SortHeader label="p90" column="p90" active={table.key === "p90"} direction={table.direction} onSort={table.sort} />
      <SortHeader label="Hata" column="error" active={table.key === "error"} direction={table.direction} onSort={table.sort} />
      <SortHeader label="Kapsama" column="covered" active={table.key === "covered"} direction={table.direction} onSort={table.sort} />
    </tr></thead><tbody>{table.sorted.map((row) => <tr key={row.date}><th scope="row">{new Date(row.date).toLocaleDateString("tr-TR")}</th><td>{money(row.actual_value)}</td><td>{money(row.predicted_p10)}</td><td>{money(row.predicted_p50)}</td><td>{money(row.predicted_p90)}</td><td>{signedPct(row.error_pct)}</td><td>{row.covered ? "İçinde" : "Dışında"}</td></tr>)}</tbody></table></div>
  </section>;
}
function Tile({ label, value }: { label: string; value: string }) { return <div className="stat-tile"><div className="label">{label}</div><div className="value">{value}</div></div>; }
