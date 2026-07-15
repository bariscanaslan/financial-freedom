"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { applyPortfolioDraft, getPortfolioDraftStatus, startPortfolioDraft, updatePortfolioDraft } from "@/lib/api";
import { money, pct, simpleReturn } from "@/lib/format";
import type { PortfolioDraft, PortfolioDraftJob, PortfolioKind } from "@/lib/types";

export default function PortfolioBuilderPage() {
  const [name, setName] = useState("Model Destekli Portföyüm");
  const [amount, setAmount] = useState("10000");
  const [risk, setRisk] = useState("balanced");
  const [horizon, setHorizon] = useState("monthly");
  const [count, setCount] = useState("5");
  const [draft, setDraft] = useState<PortfolioDraft | null>(null);
  const [job, setJob] = useState<PortfolioDraftJob | null>(null);
  const [weights, setWeights] = useState<Record<string, string>>({});
  const [feedback, setFeedback] = useState("");
  const [kind, setKind] = useState<PortfolioKind>("simulated");
  const [created, setCreated] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!job || job.status === "completed" || job.status === "failed") return;
    const timer = window.setInterval(async () => {
      try {
        const current = await getPortfolioDraftStatus(job.id);
        setJob(current);
        if (current.status === "completed" && current.draft) { loadDraft(current.draft); setBusy(false); }
        if (current.status === "failed") { setError(current.error ?? "Taslak oluşturulamadı."); setBusy(false); }
      } catch (err) { setError(err instanceof Error ? err.message : "Taslak durumu alınamadı."); setBusy(false); }
    }, 750);
    return () => window.clearInterval(timer);
  }, [job?.id, job?.status]);

  function loadDraft(value: PortfolioDraft) {
    setDraft(value); setFeedback(value.feedback);
    setWeights(Object.fromEntries(value.allocations.map((item) => [item.ticker, (item.weight * 100).toFixed(2)])));
  }
  async function generate(event: React.FormEvent) {
    event.preventDefault(); setBusy(true); setError(null); setCreated(null);
    try { setDraft(null); setJob(await startPortfolioDraft({ name, investment_amount: Number(amount), risk_preference: risk, horizon, max_positions: Number(count) })); }
    catch (err) { setError(err instanceof Error ? err.message : "Taslak oluşturulamadı."); setBusy(false); }
  }
  async function save() {
    if (!draft) return; setBusy(true); setError(null);
    try { loadDraft(await updatePortfolioDraft(draft.id, { allocations: Object.fromEntries(Object.entries(weights).map(([ticker, value]) => [ticker, Number(value)])), feedback })); }
    catch (err) { setError(err instanceof Error ? err.message : "Taslak güncellenemedi."); }
    finally { setBusy(false); }
  }
  async function apply() {
    if (!draft) return; setBusy(true); setError(null);
    try { const portfolio = await applyPortfolioDraft(draft.id, kind); setCreated(portfolio.id); }
    catch (err) { setError(err instanceof Error ? err.message : "Portföy oluşturulamadı."); }
    finally { setBusy(false); }
  }

  return <div>
    <h1>Akıllı Portföy Oluşturucu</h1>
    <p className="lead">Tercihlerinizi ve eğitilmiş ticker modellerini kullanarak düzenlenebilir bir portföy taslağı üretin.</p>
    <section className="card" aria-labelledby="portfolio-parameters-title">
      <h2 id="portfolio-parameters-title">Parametreleri nasıl seçmelisiniz?</h2>
      <div className="grid-3">
        <div>
          <h3>Risk tercihi</h3>
          <p className="muted small">Model belirsizliği yüksek hisselere ne kadar tolerans gösterileceğini belirler. Düşük risk daha dar tahmin aralıklarını, Dengeli orta seviyeyi, Yüksek risk ise daha geniş aralıkları kabul eder. Kaybetme toleransınız düşükse Düşük risk seçin.</p>
        </div>
        <div>
          <h3>Yatırım vadesi</h3>
          <p className="muted small">Tahminlerin kaç işlem günlük model çıktısıyla değerlendirileceğini belirler. Paraya ihtiyaç duyacağınız tarihe en yakın vadeyi seçin. Seçilen vadeyi desteklemeyen veya o vadede kalite eşiğini geçmeyen modeller portföye alınmaz.</p>
        </div>
        <div>
          <h3>Pozisyon sayısı</h3>
          <p className="muted small">Taslakta bulunabilecek en fazla farklı hisse sayısıdır. Daha yüksek sayı çeşitlendirmeyi artırabilir; ancak kalite eşiğini geçen model sayısı daha azsa taslak seçtiğiniz sayıdan az pozisyon içerebilir.</p>
        </div>
      </div>
      <p className="note">Bu tercihler kaybı engellemez; yalnızca model adaylarının filtrelenmesini ve ağırlıklandırılmasını değiştirir.</p>
    </section>
    <form className="card builder portfolio-builder-form" onSubmit={generate}>
      <div className="portfolio-builder-fields">
        <label className="field">Portföy adı<input value={name} onChange={(e) => setName(e.target.value)} required /></label>
        <label className="field">Yatırım tutarı (USD)<input inputMode="decimal" value={amount} onChange={(e) => setAmount(e.target.value)} required /></label>
        <label className="field">Risk tercihi<select value={risk} onChange={(e) => setRisk(e.target.value)}><option value="conservative">Düşük risk</option><option value="balanced">Dengeli</option><option value="aggressive">Yüksek risk</option></select></label>
        <label className="field">Yatırım vadesi<select value={horizon} onChange={(e) => setHorizon(e.target.value)}><option value="daily">Günlük</option><option value="weekly">Haftalık</option><option value="monthly">1 ay</option><option value="quarterly">3 ay</option><option value="half_year">6 ay</option><option value="yearly">1 yıl</option><option value="two_year">2 yıl</option></select></label>
        <label className="field">Pozisyon sayısı<select value={count} onChange={(e) => setCount(e.target.value)}>{[2,3,4,5,6,7,8,9,10].map((n) => <option key={n}>{n}</option>)}</select></label>
        <button className="btn primary" disabled={busy}>{busy ? "Hesaplanıyor…" : "Taslak Oluştur"}</button>
      </div>
    </form>
    {error && <p className="note neg" role="alert">{error}</p>}
    {job && job.status !== "completed" && <section className="card" style={{ marginTop: "1rem" }} aria-live="polite">
      <h2>Taslak hazırlanıyor</h2>
      <p><strong>{job.stage}</strong></p>
      <progress value={Math.round(job.progress * 100)} max={100} aria-label="Portföy oluşturma ilerlemesi" />
      <p className="muted small">%{Math.round(job.progress * 100)} · İncelenen model: {job.processed_models}/{job.total_models || "—"}</p>
      {job.events.length > 0 && <div className="draft-event-log" aria-label="Model değerlendirme günlüğü">{job.events.map((event, index) => <div key={`${index}-${event}`} className="muted small">{event}</div>)}</div>}
    </section>}
    {draft && <section className="card" style={{ marginTop: "1rem" }}>
      <h2>{draft.name}</h2><p className="note">{draft.disclaimer}</p>
      <div className="table-scroll"><table className="data-table portfolio-draft-table"><thead><tr><th className="left">Sembol</th><th>Şirket</th><th>Ağırlık (%)</th><th>Tutar</th><th>Medyan getiri</th><th>Belirsizlik</th></tr></thead><tbody>
        {draft.allocations.map((item) => <tr key={item.ticker}><th scope="row">{item.ticker}</th><td>{item.name ?? "—"}</td><td><input aria-label={`${item.ticker} ağırlığı`} inputMode="decimal" value={weights[item.ticker] ?? ""} onChange={(e) => setWeights({ ...weights, [item.ticker]: e.target.value })} /></td><td>{money(item.amount)}</td><td>{pct(simpleReturn(item.expected_return))}</td><td>{pct(item.uncertainty_pct)}</td></tr>)}
      </tbody></table></div>
      <label className="field" style={{ marginTop: "1rem" }}>Geri bildiriminiz<textarea value={feedback} onChange={(e) => setFeedback(e.target.value)} placeholder="Bu taslakla ilgili tercihinizi veya değişiklik nedeninizi yazın." rows={3} /></label>
      <div className="form-row portfolio-builder-actions"><button type="button" className="btn" disabled={busy} onClick={save}>Düzenlemeleri ve Geri Bildirimi Kaydet</button><label className="field">Portföy türü<select value={kind} onChange={(e) => setKind(e.target.value as PortfolioKind)}><option value="simulated">Simülasyon</option><option value="actual">Gerçek</option></select></label><button type="button" className="btn primary" disabled={busy || Boolean(created)} onClick={apply}>Portföye Dönüştür</button></div>
      {created && <p className="note pos">Portföy oluşturuldu. <Link href="/portfolio">Portföyü görüntüle</Link></p>}
    </section>}
  </div>;
}
