"use client";

// Market overview: high-traffic NASDAQ tickers with latest price + period change.
// Values come from the API (/market/overview); change cells carry a +/- sign so
// meaning is never color-alone.

import { money, signedPct, signClass } from "@/lib/format";
import type { MarketRow } from "@/lib/types";
import { useSortable } from "@/lib/useSortable";
import { SortHeader } from "./SortHeader";

export function MarketTable({ rows }: { rows: MarketRow[] }) {
  const { sorted, sort, key, direction } = useSortable(rows, {
    ticker: (row) => row.ticker, price: (row) => row.price,
    daily: (row) => row.change_1d, weekly: (row) => row.change_1w,
    monthly: (row) => row.change_1m, model: (row) => row.has_model,
  }, "ticker");
  return (
    <div className="table-scroll">
      <table className="data-table" data-testid="market-table">
        <thead>
          <tr>
            <SortHeader label="Sembol" column="ticker" active={key === "ticker"} direction={direction} onSort={sort} left />
            <SortHeader label="Fiyat" column="price" active={key === "price"} direction={direction} onSort={sort} />
            <SortHeader label="Günlük" column="daily" active={key === "daily"} direction={direction} onSort={sort} />
            <SortHeader label="Haftalık" column="weekly" active={key === "weekly"} direction={direction} onSort={sort} />
            <SortHeader label="Aylık" column="monthly" active={key === "monthly"} direction={direction} onSort={sort} />
            <SortHeader label="Model" column="model" active={key === "model"} direction={direction} onSort={sort} left />
          </tr>
        </thead>
        <tbody>
          {sorted.map((r) => (
            <tr key={r.ticker}>
              <th scope="row">{r.ticker}</th>
              <td>{money(r.price)}</td>
              <td className={signClass(r.change_1d)}>{signedPct(r.change_1d)}</td>
              <td className={signClass(r.change_1w)}>{signedPct(r.change_1w)}</td>
              <td className={signClass(r.change_1m)}>{signedPct(r.change_1m)}</td>
              <td className="left">
                {r.has_model ? (
                  <span className="chip accent">model var</span>
                ) : (
                  <span className="chip">—</span>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
