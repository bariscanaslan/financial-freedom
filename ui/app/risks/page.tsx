"use client";

import Link from "next/link";
import { useState } from "react";
import { deleteRisk, listRisks } from "@/lib/api";
import { money, pct } from "@/lib/format";
import { useAsync } from "@/lib/useAsync";
import { Empty, ErrorView, Loading } from "@/components/States";
import { SortHeader } from "@/components/SortHeader";
import { useSortable } from "@/lib/useSortable";
import type { SavedRisk } from "@/lib/types";

export default function RisksPage() {
  const state = useAsync(listRisks, []);
  return (
    <div>
      <h1>Kaydedilen Riskler</h1>
      <p className="lead">Portföy risk analizlerinin tarihsel anlık görüntüleri.</p>
      {state.status === "loading" && <Loading />}
      {state.status === "error" && <ErrorView error={state.error} />}
      {state.status === "ready" && (state.data.risks.length
        ? <RisksTable rows={state.data.risks} />
        : <Empty message="Henüz kaydedilmiş risk analizi yok." />)}
    </div>
  );
}

function RisksTable({ rows }: { rows: SavedRisk[] }) {
  const [items, setItems] = useState(rows);
  const table = useSortable(items, {
    portfolio: (row) => row.portfolio_id,
    created: (row) => row.created_at,
    value: (row) => row.risk.current_value,
    range: (row) => row.risk.values.p90 - row.risk.values.p10,
    method: (row) => row.risk.method,
  }, "created");
  async function remove(row: SavedRisk) {
    if (!window.confirm("Bu risk kaydını silmek istediğinizden emin misiniz?")) return;
    await deleteRisk(row.id);
    setItems((current) => current.filter((item) => item.id !== row.id));
  }
  return (
    <div className="table-scroll"><table className="data-table">
      <thead><tr>
        <SortHeader label="Portföy" column="portfolio" active={table.key === "portfolio"} direction={table.direction} onSort={table.sort} left />
        <SortHeader label="Kayıt tarihi" column="created" active={table.key === "created"} direction={table.direction} onSort={table.sort} />
        <SortHeader label="Güncel değer" column="value" active={table.key === "value"} direction={table.direction} onSort={table.sort} />
        <SortHeader label="Risk aralığı" column="range" active={table.key === "range"} direction={table.direction} onSort={table.sort} />
        <SortHeader label="Yöntem" column="method" active={table.key === "method"} direction={table.direction} onSort={table.sort} />
        <th>İşlem</th>
      </tr></thead>
      <tbody>{table.sorted.map((row) => <tr key={row.id}>
        <th scope="row">{row.portfolio_id}</th>
        <td>{new Date(row.created_at).toLocaleString("tr-TR")}</td>
        <td>{money(row.risk.current_value)}</td>
        <td>{money(row.risk.values.p90 - row.risk.values.p10)} ({pct(row.risk.returns.p90 - row.risk.returns.p10)})</td>
        <td>{row.risk.method === "historical_correlation" ? "Tarihsel korelasyon" : "İhtiyatlı"}</td>
        <td><div className="form-row" style={{ margin: 0, flexWrap: "nowrap" }}>
          <Link className="btn sm" href={`/risks/${row.id}`}>Detay</Link>
          <button className="btn danger sm" onClick={() => remove(row)}>Sil</button>
        </div></td>
      </tr>)}</tbody>
    </table></div>
  );
}
