"use client";

import { useParams, useRouter } from "next/navigation";
import { deletePrediction, getPrediction } from "@/lib/api";
import { money, pct, signedPct, signClass, simpleReturn } from "@/lib/format";
import { useAsync } from "@/lib/useAsync";
import { ForecastBand } from "@/components/ForecastBand";
import { ErrorView, Loading } from "@/components/States";

export default function PredictionDetailPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const state = useAsync(() => getPrediction(params.id), [params.id]);

  async function remove() {
    if (!window.confirm("Bu tahmini silmek istediğinizden emin misiniz?")) return;
    await deletePrediction(params.id);
    router.push("/predictions");
  }

  if (state.status === "loading") return <Loading />;
  if (state.status === "error") return <ErrorView error={state.error} />;

  const row = state.data;
  const forecast = row.forecast;
  const periods = forecast.periods && Object.keys(forecast.periods).length
    ? Object.values(forecast.periods)
    : [{
        label: "Günlük", trading_days: 1, returns: forecast.returns,
        prices: forecast.prices, uncertainty: forecast.uncertainty,
        uncertainty_pct: forecast.uncertainty_pct,
      }];

  return (
    <div>
      <div className="form-row" style={{ justifyContent: "space-between", alignItems: "center" }}>
        <div>
          <h1>{row.ticker} Tahmin Detayı</h1>
          <p className="muted small">
            Referans: {new Date(row.as_of).toLocaleDateString("tr-TR")} · Kayıt: {new Date(row.created_at).toLocaleString("tr-TR")}
          </p>
        </div>
        <button className="btn danger" onClick={remove}>Tahmini Sil</button>
      </div>

      <div className="stat-tiles">
        <div className="stat-tile"><div className="label">Referans fiyat</div><div className="value">{money(forecast.anchor_price)}</div></div>
        <div className="stat-tile"><div className="label">skill_score</div><div className="value">{forecast.meta.skill_score?.toFixed(4) ?? "—"}</div></div>
        <div className="stat-tile"><div className="label">Kapsama</div><div className="value">{pct(forecast.meta.coverage)}</div></div>
      </div>

      {periods.map((period) => (
        <section key={period.trading_days}>
          <h2>{period.label} tahmin</h2>
          <div className="stat-tiles">
            <div className="stat-tile"><div className="label">Medyan getiri</div><div className={`value ${signClass(period.returns.p50)}`}>{signedPct(simpleReturn(period.returns.p50))}</div></div>
            <div className="stat-tile"><div className="label">Belirsizlik</div><div className="value">{pct(period.uncertainty_pct)}</div></div>
          </div>
          <ForecastBand
            anchorLabel="referans"
            targetLabel={`${period.trading_days} işlem günü`}
            anchor={forecast.anchor_price}
            lower={period.prices.p10}
            median={period.prices.p50}
            upper={period.prices.p90}
            format={money}
            caption={`${period.label} tahmin aralığı`}
          />
        </section>
      ))}
    </div>
  );
}
