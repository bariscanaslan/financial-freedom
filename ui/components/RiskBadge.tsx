// Model honesty indicator. skill_score / coverage shown RAW.
// There is NO green "reliable" badge. skill_score <= MIN_SKILL -> explicit
// warning (guide). coverage below target -> "overconfident".

import { MIN_SKILL } from "@/lib/config";
import { pct, num } from "@/lib/format";
import type { ModelMeta } from "@/lib/types";

export function RiskBadge({ meta }: { meta: ModelMeta }) {
  const skill = meta.skill_score;
  const cov = meta.coverage;
  const nominal = meta.nominal_cov;
  const covGap = cov != null && nominal != null ? cov - nominal : null;

  const beatsNaive = skill != null && skill > MIN_SKILL;
  const covUnder = covGap != null && covGap < -0.05;

  return (
    <div className="risk-badge" data-testid="risk-badge">
      <div className="stat-tiles">
        <div className="stat-tile">
          <div className="label">skill_score</div>
          <div className="value mono">{num(skill, 4)}</div>
        </div>
        <div className="stat-tile">
          <div className="label">kapsama</div>
          <div className="value mono">
            {pct(cov, 1)}
            {nominal != null && (
              <span className="muted small"> / hedef {pct(nominal, 0)}</span>
            )}
          </div>
        </div>
      </div>

      {/* Honesty warnings -- no reassuring language */}
      {skill == null ? (
        <p className="note muted">Bu model için test metriği kaydedilmemiş.</p>
      ) : !beatsNaive ? (
        <p className="note warn" data-testid="skill-warning">
          Bu model, saf (rastgele yürüyüş) tahminini <strong>anlamlı ölçüde
          geçmiyor</strong> (skill_score {"<="} {MIN_SKILL}). Nokta tahminini
          kesinlik olarak değerlendirmeyin; değer belirsizlik aralığındadır.
        </p>
      ) : (
        <p className="note muted">
          skill_score eşiği ({MIN_SKILL}) aştı. Yine de bu tek bir test
          kesitidir; kesinlik değil, bir gözlemdir.
        </p>
      )}

      {covUnder && (
        <p className="note neg" data-testid="coverage-warning">
          Kapsama HEDEFİN ALTINDA: model riski olduğundan düşük gösteriyor.
          Gerçek aralık gösterilenden daha geniş olabilir.
        </p>
      )}
    </div>
  );
}
