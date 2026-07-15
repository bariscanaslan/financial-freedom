// Summary card for one portfolio: current total value + portfolio-level metrics.
// All numbers come from the API (/positions, /metrics); the UI does not recompute.

import { money, pct, signedPct, num, signClass } from "@/lib/format";
import type { MetricsResponse, PositionsResponse } from "@/lib/types";

interface Props {
  title: string;
  positions: PositionsResponse | null;
  metrics: MetricsResponse | null;
}

export function PortfolioValueCard({ title, positions, metrics }: Props) {
  const total = positions?.total_value ?? null;
  return (
    <div className="card" data-testid="value-card">
      <h3>{title}</h3>
      <div className="big-number">
        {total === null ? <span className="muted">veri yok</span> : money(total)}
      </div>
      {positions && (
        <p className="muted small">
          nakit {money(positions.cash)} · {positions.positions.length} pozisyon
          {positions.as_of ? ` · ${positions.as_of}` : ""}
        </p>
      )}
      {metrics && (
        <dl className="metric-grid">
          <div>
            <dt>Toplam getiri (TWR)</dt>
            <dd className={signClass(metrics.total_return)}>
              {signedPct(metrics.total_return)}
            </dd>
          </div>
          <div>
            <dt>Yıllıklandırılmış oynaklık</dt>
            <dd>{pct(metrics.ann_vol)}</dd>
          </div>
          <div>
            <dt>Sharpe</dt>
            <dd>{num(metrics.sharpe)}</dd>
          </div>
          <div>
            <dt>En yüksek düşüş</dt>
            <dd className="neg">{pct(metrics.max_drawdown)}</dd>
          </div>
        </dl>
      )}
    </div>
  );
}
