"use client";

import Link from "next/link";
import { useState } from "react";
import { deletePrediction, listPredictions } from "@/lib/api";
import { money, signedPct, simpleReturn } from "@/lib/format";
import { useAsync } from "@/lib/useAsync";
import { Empty, ErrorView, Loading } from "@/components/States";
import type { SavedPrediction } from "@/lib/types";
import { SortHeader } from "@/components/SortHeader";
import { useSortable } from "@/lib/useSortable";

export default function PredictionsPage() {
  const state = useAsync(listPredictions, []);
  return (
    <div>
      <h1>Kaydedilen Tahminler</h1>
      <p className="lead">
        Geçmiş tahmin anlık görüntülerini dönemlere göre izleyin. Kayıtlar,
        ileride gerçekleşen sonuçlarla karşılaştırılmak üzere değiştirilmeden saklanır.
      </p>
      {state.status === "loading" && <Loading />}
      {state.status === "error" && <ErrorView error={state.error} />}
      {state.status === "ready" && (state.data.predictions.length === 0
        ? <Empty message="Henüz kaydedilmiş tahmin yok." />
        : <PredictionTable rows={state.data.predictions} />)}
    </div>
  );
}

function PredictionTable({ rows }: { rows: SavedPrediction[] }) {
  const [items, setItems] = useState(rows);
  const flattened = items.flatMap((row) => {
    const periods = row.forecast.periods && Object.keys(row.forecast.periods).length
      ? Object.values(row.forecast.periods)
      : [{
          label: "Günlük", trading_days: 1, returns: row.forecast.returns,
          prices: row.forecast.prices, uncertainty: row.forecast.uncertainty,
          uncertainty_pct: row.forecast.uncertainty_pct,
        }];
    return periods.map((period) => ({ row, period }));
  });
  const table = useSortable(flattened, {
    ticker: (item) => item.row.ticker,
    reference: (item) => item.row.as_of,
    created: (item) => item.row.created_at,
    period: (item) => item.period.trading_days,
    p10: (item) => item.period.prices.p10,
    p50: (item) => item.period.prices.p50,
    p90: (item) => item.period.prices.p90,
    return: (item) => item.period.returns.p50,
  }, "created");

  async function remove(row: SavedPrediction) {
    if (!window.confirm(`${row.ticker} tahminini silmek istediğinizden emin misiniz?`)) return;
    await deletePrediction(row.id);
    setItems((current) => current.filter((item) => item.id !== row.id));
  }

  return (
    <div className="table-scroll">
      <table className="data-table">
        <thead>
          <tr>
            <SortHeader label="Sembol" column="ticker" active={table.key === "ticker"} direction={table.direction} onSort={table.sort} left />
            <SortHeader label="Referans tarihi" column="reference" active={table.key === "reference"} direction={table.direction} onSort={table.sort} />
            <SortHeader label="Kayıt tarihi" column="created" active={table.key === "created"} direction={table.direction} onSort={table.sort} />
            <SortHeader label="Dönem" column="period" active={table.key === "period"} direction={table.direction} onSort={table.sort} />
            <SortHeader label="p10 fiyat" column="p10" active={table.key === "p10"} direction={table.direction} onSort={table.sort} />
            <SortHeader label="p50 fiyat" column="p50" active={table.key === "p50"} direction={table.direction} onSort={table.sort} />
            <SortHeader label="p90 fiyat" column="p90" active={table.key === "p90"} direction={table.direction} onSort={table.sort} />
            <SortHeader label="p50 getiri" column="return" active={table.key === "return"} direction={table.direction} onSort={table.sort} />
            <th>İşlem</th>
          </tr>
        </thead>
        <tbody>
          {table.sorted.map(({ row, period }) => (
              <tr key={`${row.id}-${period.trading_days}`}>
                <th scope="row">{row.ticker}</th>
                <td>{new Date(row.as_of).toLocaleDateString("tr-TR")}</td>
                <td>{new Date(row.created_at).toLocaleString("tr-TR")}</td>
                <td>{period.label}</td>
                <td>{money(period.prices.p10)}</td><td>{money(period.prices.p50)}</td>
                <td>{money(period.prices.p90)}</td><td>{signedPct(simpleReturn(period.returns.p50))}</td>
                <td>
                  <div className="form-row" style={{ margin: 0, flexWrap: "nowrap" }}>
                    <Link className="btn sm" href={`/predictions/${row.id}`}>Detay</Link>
                    <button className="btn danger sm" onClick={() => remove(row)}>Sil</button>
                  </div>
                </td>
              </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
