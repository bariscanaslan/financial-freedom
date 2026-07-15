"use client";

import Link from "next/link";
import { useAsync } from "@/lib/useAsync";
import {
  getMarketOverview,
  getMetrics,
  getPositions,
  getReport,
  listPortfolios,
} from "@/lib/api";
import { money, signedPct } from "@/lib/format";
import { MarketTable } from "@/components/MarketTable";
import { PortfolioValueCard } from "@/components/PortfolioValueCard";
import { ErrorView, Loading } from "@/components/States";
import type {
  MarketOverviewResponse,
  MetricsResponse,
  PortfolioKind,
  PortfolioSummary,
  PositionsResponse,
  ReportResponse,
} from "@/lib/types";
import { SortHeader } from "@/components/SortHeader";
import { useSortable } from "@/lib/useSortable";

interface Slot {
  portfolio: PortfolioSummary;
  positions: PositionsResponse;
  metrics: MetricsResponse | null;
  report: ReportResponse | null;
}

interface DashData {
  actual: Slot | null;
  sim: Slot | null;
  market: MarketOverviewResponse;
}

async function slot(p: PortfolioSummary, withReport: boolean): Promise<Slot> {
  const [positions, metrics, report] = await Promise.all([
    getPositions(p.id),
    getMetrics(p.id).catch(() => null),
    withReport ? getReport(p.id).catch(() => null) : Promise.resolve(null),
  ]);
  return { portfolio: p, positions, metrics, report };
}

async function load(): Promise<DashData> {
  const [list, market] = await Promise.all([listPortfolios(), getMarketOverview()]);
  const first = (k: PortfolioKind) => list.portfolios.find((p) => p.kind === k) ?? null;
  const a = first("actual");
  const s = first("simulated");
  const [actual, sim] = await Promise.all([
    a ? slot(a, true) : Promise.resolve(null),
    s ? slot(s, false) : Promise.resolve(null),
  ]);
  return { actual, sim, market };
}

export default function Dashboard() {
  const state = useAsync(load, []);
  return (
    <div>
      <h1>Genel Bakış</h1>
      <p className="lead">
        Portföylerinizin SPY karşılaştırma ölçütüne göre özeti ve bugün en çok
        işlem gören NASDAQ hisseleri.
      </p>
      {state.status === "loading" && <Loading />}
      {state.status === "error" && <ErrorView error={state.error} />}
      {state.status === "ready" && <DashboardView data={state.data} />}
    </div>
  );
}

function DashboardView({ data }: { data: DashData }) {
  const aTotal = data.actual?.positions.total_value ?? null;
  const sTotal = data.sim?.positions.total_value ?? null;
  const diff = aTotal !== null && sTotal !== null ? aTotal - sTotal : null;

  const report = data.actual?.report ?? null;
  const bench = report?.rows.find((r) => r.portfolio.startsWith("benchmark"));
  const actualRow = report?.rows.find((r) => r.portfolio === "actual");
  const comparison = bench && actualRow ? [
    { name: "gerçek", value: actualRow.total_return },
    { name: bench.portfolio, value: bench.total_return },
  ] : [];
  const comparisonTable = useSortable(comparison, {
    portfolio: (row) => row.name,
    return: (row) => row.value,
  }, "portfolio");

  return (
    <>
      <h2>Portföyleriniz</h2>
      {data.actual || data.sim ? (
        <>
          <div className="grid-2">
            <PortfolioValueCard
              title={data.actual?.portfolio.name ?? "Gerçek"}
              positions={data.actual?.positions ?? null}
              metrics={data.actual?.metrics ?? null}
            />
            <PortfolioValueCard
              title={data.sim?.portfolio.name ?? "Simülasyon"}
              positions={data.sim?.positions ?? null}
              metrics={data.sim?.metrics ?? null}
            />
          </div>
          {diff !== null && (
            <p className="muted" style={{ marginTop: "1rem" }}>
              Fark (gerçek − simülasyon): <strong>{money(diff)}</strong>
            </p>
          )}
          {bench && actualRow && (
            <div className="table-scroll">
              <table className="data-table" style={{ marginTop: "1rem" }}>
                <thead>
                  <tr>
                    <SortHeader label="Portföy" column="portfolio" active={comparisonTable.key === "portfolio"} direction={comparisonTable.direction} onSort={comparisonTable.sort} left />
                    <SortHeader label="Toplam getiri (TWR)" column="return" active={comparisonTable.key === "return"} direction={comparisonTable.direction} onSort={comparisonTable.sort} />
                  </tr>
                </thead>
                <tbody>
                  {comparisonTable.sorted.map((row) => (
                    <tr key={row.name}>
                      <th scope="row">{row.name}</th>
                      <td>{signedPct(row.value)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </>
      ) : (
        <p className="muted">
          Henüz portföy yok. Burada takip etmek için bir <Link href="/portfolio">portföy oluşturun</Link>.
        </p>
      )}

      <h2>NASDAQ piyasa özeti</h2>
      <MarketTable rows={data.market.rows} />
      <p className="muted small">
        Son fiyat ile 1/5/21 işlem günlük değişimler yfinance üzerinden alınır.
        &quot;Model var&quot; etiketi, eğitilmiş tahmin modeli bulunan hisseleri gösterir.
      </p>
    </>
  );
}
