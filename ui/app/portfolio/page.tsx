"use client";

import { useState } from "react";
import { useAsync } from "@/lib/useAsync";
import {
  deletePortfolio,
  getMetrics,
  getPositions,
  getTrainingCatalog,
  getTrades,
  listPortfolios,
} from "@/lib/api";
import { PortfolioBuilder } from "@/components/PortfolioBuilder";
import { PortfolioValueCard } from "@/components/PortfolioValueCard";
import { PositionsTable } from "@/components/PositionsTable";
import { PortfolioTrades } from "@/components/PortfolioTrades";
import { PortfolioAlertSettings } from "@/components/PortfolioAlertSettings";
import { Empty, ErrorView, Loading } from "@/components/States";
import type {
  MetricsResponse,
  PortfolioKind,
  PortfolioSummary,
  PositionsResponse,
  Trade,
} from "@/lib/types";

const TABS: { kind: PortfolioKind; label: string }[] = [
  { kind: "actual", label: "Gerçek" },
  { kind: "simulated", label: "Simülasyon" },
];

interface Entry {
  portfolio: PortfolioSummary;
  positions: PositionsResponse;
  metrics: MetricsResponse | null;
  trades: Trade[];
}

async function load(kind: PortfolioKind): Promise<Entry[]> {
  const all = await listPortfolios();
  const mine = all.portfolios.filter((p) => p.kind === kind);
  return Promise.all(
    mine.map(async (portfolio) => {
      const [positions, metrics, tradeData] = await Promise.all([
        getPositions(portfolio.id),
        getMetrics(portfolio.id).catch(() => null),
        getTrades(portfolio.id),
      ]);
      return { portfolio, positions, metrics, trades: tradeData.trades };
    }),
  );
}

export default function PortfolioPage() {
  const [kind, setKind] = useState<PortfolioKind>("actual");
  const [refresh, setRefresh] = useState(0);
  const state = useAsync(() => load(kind), [kind, refresh]);
  const catalog = useAsync(getTrainingCatalog, []);
  const reload = () => setRefresh((n) => n + 1);

  async function remove(id: string) {
    await deletePortfolio(id);
    reload();
  }

  return (
    <div>
      <h1>Portföy</h1>
      <p className="lead">
        Hisse sembollerini seçip her biri için nakit tutarı girerek portföyünüzü
        oluşturun; günlük, haftalık ve aylık değişimleri takip edin. Gerçek
        portföy yatırımlarınızı, Simülasyon ise varsayımsal yatırımları gösterir.
      </p>

      <div className="tabs" role="tablist">
        {TABS.map((t) => (
          <button
            key={t.kind}
            role="tab"
            aria-selected={kind === t.kind}
            onClick={() => setKind(t.kind)}
          >
            {t.label}
          </button>
        ))}
      </div>

      <PortfolioBuilder kind={kind} onCreated={reload} />

      {state.status === "loading" && <Loading />}
      {state.status === "error" && <ErrorView error={state.error} />}
      {state.status === "ready" &&
        (state.data.length === 0 ? (
          <Empty message={`Henüz ${kind === "actual" ? "gerçek" : "simülasyon"} portföyü yok. Yukarıdan oluşturabilirsiniz.`} />
        ) : (
          state.data.map((e) => (
            <section key={e.portfolio.id} style={{ marginTop: "1.5rem" }}>
              <div className="form-row" style={{ justifyContent: "space-between", alignItems: "center" }}>
                <h2 style={{ margin: 0 }}>{e.portfolio.name}</h2>
                <button
                  className="btn danger sm"
                  onClick={() => remove(e.portfolio.id)}
                  aria-label={`${e.portfolio.name} portföyünü sil`}
                >
                  Sil
                </button>
              </div>
              <PortfolioValueCard
                title={e.portfolio.name}
                positions={e.positions}
                metrics={e.metrics}
              />
              <PositionsTable data={e.positions} />
              <PortfolioAlertSettings portfolioId={e.portfolio.id} />
              <PortfolioTrades
                portfolioId={e.portfolio.id}
                trades={e.trades}
                tickers={catalog.status === "ready" ? catalog.data.tickers : e.positions.positions}
                onChanged={reload}
              />
            </section>
          ))
        ))}

      <p className="muted small" style={{ marginTop: "1.5rem" }}>
        Günlük, haftalık ve aylık değişimler API&apos;den alınır. Verisi olmayan
        alanlar 0 yerine &quot;—&quot; olarak gösterilir.
      </p>
    </div>
  );
}
