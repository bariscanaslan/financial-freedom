"use client";

// Positions table: shares + current value + daily/weekly/monthly change.
// Change percentages come from the API (portfolio/positions.py); the UI does NOT
// compute them. Empty holdings -> "no open positions". null change -> "—" (not 0).

import { money, pct, shares, signedPct, signClass } from "@/lib/format";
import type { PositionsResponse } from "@/lib/types";
import { Empty } from "./States";
import { useSortable } from "@/lib/useSortable";
import { SortHeader } from "./SortHeader";

export function PositionsTable({ data }: { data: PositionsResponse }) {
  const { sorted, sort, key, direction } = useSortable(data.positions, {
    ticker: (row) => row.ticker, shares: (row) => row.shares,
    price: (row) => row.price, value: (row) => row.value, weight: (row) => row.weight,
    daily: (row) => row.change_1d, weekly: (row) => row.change_1w,
    monthly: (row) => row.change_1m,
  }, "value");
  if (data.positions.length === 0) {
    return <Empty message="Bu portföyde açık pozisyon yok." />;
  }
  return (
    <div className="table-scroll">
      <table className="data-table" data-testid="positions-table">
        <thead>
          <tr>
            <SortHeader label="Sembol" column="ticker" active={key === "ticker"} direction={direction} onSort={sort} left />
            <SortHeader label="Adet" column="shares" active={key === "shares"} direction={direction} onSort={sort} />
            <SortHeader label="Fiyat" column="price" active={key === "price"} direction={direction} onSort={sort} />
            <SortHeader label="Değer" column="value" active={key === "value"} direction={direction} onSort={sort} />
            <SortHeader label="Ağırlık" column="weight" active={key === "weight"} direction={direction} onSort={sort} />
            <SortHeader label="Günlük" column="daily" active={key === "daily"} direction={direction} onSort={sort} />
            <SortHeader label="Haftalık" column="weekly" active={key === "weekly"} direction={direction} onSort={sort} />
            <SortHeader label="Aylık" column="monthly" active={key === "monthly"} direction={direction} onSort={sort} />
          </tr>
        </thead>
        <tbody>
          {sorted.map((p) => (
            <tr key={p.ticker}>
              <th scope="row">{p.ticker}</th>
              <td>{shares(p.shares)}</td>
              <td>{money(p.price)}</td>
              <td>{money(p.value)}</td>
              <td>{pct(p.weight, 1)}</td>
              <td className={signClass(p.change_1d)}>{signedPct(p.change_1d)}</td>
              <td className={signClass(p.change_1w)}>{signedPct(p.change_1w)}</td>
              <td className={signClass(p.change_1m)}>{signedPct(p.change_1m)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
