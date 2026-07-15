import { GUIDE, GUIDE_INTRO } from "@/content/guide";

// Server component: renders guide content from a SINGLE SOURCE (content/guide.ts).
export default function GuidePage() {
  return (
    <div>
      <h1>Rehber</h1>
      <p className="lead">{GUIDE_INTRO}</p>
      {GUIDE.map((s) => (
        <section key={s.id} id={s.id} className="guide-section">
          <h2>{s.title}</h2>
          {s.paragraphs.map((p, i) => (
            <p key={i}>{p}</p>
          ))}
        </section>
      ))}
    </div>
  );
}
