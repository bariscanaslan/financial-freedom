// p10/p50/p90 uncertainty band -- hand-drawn SVG (dependency-light, accessible).
// Single horizon (1 day): a cone from the anchor to the p10-p90 band, with the
// p50 median line. The same numbers are also given as a table below, so meaning
// never depends on color alone.
//
// This component does NO math; values are drawn as given (no risk formula beyond
// p90 - p10, which the caller passes in).

import { ReactNode } from "react";

interface Props {
  anchorLabel: string;
  targetLabel: string;
  anchor: number;
  lower: number; // p10
  median: number; // p50
  upper: number; // p90
  format: (x: number) => string;
  caption?: ReactNode;
}

const W = 560;
const H = 260;
const PAD = { top: 22, right: 128, bottom: 34, left: 20 };

export function ForecastBand({
  anchorLabel,
  targetLabel,
  anchor,
  lower,
  median,
  upper,
  format,
  caption,
}: Props) {
  const lo = Math.min(anchor, lower);
  const hi = Math.max(anchor, upper);
  const span = hi - lo || 1;
  const pad = span * 0.15;
  const yMin = lo - pad;
  const yMax = hi + pad;

  const xL = PAD.left;
  const xR = W - PAD.right;
  const y = (v: number) =>
    PAD.top + (H - PAD.top - PAD.bottom) * (1 - (v - yMin) / (yMax - yMin));

  // Cone: single point on the left (anchor) -> right band [p10, p90]
  const bandPath = `M ${xL} ${y(anchor)} L ${xR} ${y(upper)} L ${xR} ${y(lower)} Z`;

  return (
    <figure className="band" data-testid="forecast-band">
      <svg
        viewBox={`0 0 ${W} ${H}`}
        role="img"
        aria-label={`Belirsizlik aralığı: ${anchorLabel} ${format(anchor)} -> ${targetLabel} p10 ${format(lower)}, p50 ${format(median)}, p90 ${format(upper)}`}
        width="100%"
      >
        {/* anchor reference line */}
        <line x1={xL} y1={y(anchor)} x2={xR} y2={y(anchor)} className="band-anchor" />

        <path d={bandPath} className="band-fill" />
        <line x1={xL} y1={y(anchor)} x2={xR} y2={y(median)} className="band-median" />
        <circle cx={xL} cy={y(anchor)} r={4} className="band-dot" />
        <circle cx={xR} cy={y(median)} r={4} className="band-dot" />

        {/* right-edge value labels */}
        <text x={xR + 8} y={y(upper) + 4} className="band-value">p90 {format(upper)}</text>
        <text x={xR + 8} y={y(median) + 4} className="band-value">p50 {format(median)}</text>
        <text x={xR + 8} y={y(lower) + 4} className="band-value">p10 {format(lower)}</text>

        {/* x labels */}
        <text x={xL} y={H - 10} className="band-axis">{anchorLabel} · {format(anchor)}</text>
        <text x={xR} y={H - 10} className="band-axis" textAnchor="end">{targetLabel}</text>
      </svg>

      {/* Accessibility: not only the chart, a table too */}
      <table className="band-table">
        <caption className="muted">{caption ?? "Belirsizlik aralığı"}</caption>
        <tbody>
          <tr><th scope="row">{anchorLabel} (referans)</th><td>{format(anchor)}</td></tr>
          <tr><th scope="row">p10 (düşük)</th><td>{format(lower)}</td></tr>
          <tr><th scope="row">p50 (medyan)</th><td>{format(median)}</td></tr>
          <tr><th scope="row">p90 (yüksek)</th><td>{format(upper)}</td></tr>
          <tr><th scope="row">risk (p90 − p10)</th><td>{format(upper - lower)}</td></tr>
        </tbody>
      </table>
    </figure>
  );
}
