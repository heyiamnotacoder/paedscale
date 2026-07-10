"use client";

import type { PathwayOut } from "@/lib/types";

interface Props {
  pathways: PathwayOut[];
  pmaWeeks: number;
}

const WIDTH = 640;
const HEIGHT = 240;
const PAD_LEFT = 50;
const PAD_RIGHT = 16;
const PAD_TOP = 16;
const PAD_BOTTOM = 30;
const MAX_PMA = 200;
const COLORS = ["#0E7A6B", "#B9760A", "#2E6FB0", "#8E44AD", "#C0392B", "#16A085"];

function mf(pma: number, tm50: number, hill: number): number {
  if (pma <= 0) return 0;
  return Math.pow(pma, hill) / (Math.pow(tm50, hill) + Math.pow(pma, hill));
}

export default function MaturationChart({ pathways, pmaWeeks }: Props) {
  const plotW = WIDTH - PAD_LEFT - PAD_RIGHT;
  const plotH = HEIGHT - PAD_TOP - PAD_BOTTOM;
  const curves = pathways.filter((p) => p.tm50_weeks != null && p.hill != null);
  const caseX = PAD_LEFT + (Math.min(pmaWeeks, MAX_PMA) / MAX_PMA) * plotW;

  return (
    <div className="chart">
      <svg viewBox={`0 0 ${WIDTH} ${HEIGHT}`} role="img" aria-label="Maturation curves per elimination pathway">
        {[0, 0.25, 0.5, 0.75, 1].map((f) => {
          const y = PAD_TOP + (1 - f) * plotH;
          return <line key={f} className="gridline" x1={PAD_LEFT} y1={y} x2={WIDTH - PAD_RIGHT} y2={y} />;
        })}
        <line className="axis" x1={PAD_LEFT} y1={HEIGHT - PAD_BOTTOM} x2={WIDTH - PAD_RIGHT} y2={HEIGHT - PAD_BOTTOM} />
        <line className="axis" x1={PAD_LEFT} y1={PAD_TOP} x2={PAD_LEFT} y2={HEIGHT - PAD_BOTTOM} />
        <text className="alab" x={14} y={HEIGHT - PAD_BOTTOM + 4}>0%</text>
        <text className="alab" x={10} y={PAD_TOP + 4}>100%</text>
        <text className="alab" x={PAD_LEFT} y={HEIGHT - 8}>0 wk</text>
        <text className="alab" x={WIDTH - PAD_RIGHT - 40} y={HEIGHT - 8}>{MAX_PMA} wk PMA</text>

        {curves.map((p, idx) => {
          const color = COLORS[idx % COLORS.length];
          const pts: string[] = [];
          for (let i = 0; i <= 60; i++) {
            const pma = (i / 60) * MAX_PMA;
            const y = PAD_TOP + (1 - mf(pma, p.tm50_weeks!, p.hill!)) * plotH;
            pts.push(`${(PAD_LEFT + (pma / MAX_PMA) * plotW).toFixed(1)},${y.toFixed(1)}`);
          }
          const cy = PAD_TOP + (1 - mf(pmaWeeks, p.tm50_weeks!, p.hill!)) * plotH;
          return (
            <g key={p.name}>
              <polyline points={pts.join(" ")} fill="none" stroke={color} strokeWidth={2.4} strokeLinecap="round" />
              <circle cx={caseX} cy={cy} r={4} fill={color} />
            </g>
          );
        })}
        <line x1={caseX} y1={PAD_TOP} x2={caseX} y2={HEIGHT - PAD_BOTTOM} stroke="#6A828D" strokeDasharray="3 3" strokeWidth={1} />
      </svg>
      <div className="chart-legend">
        {curves.map((p, idx) => (
          <span key={p.name}>
            <i style={{ background: COLORS[idx % COLORS.length] }} /> {p.name}
          </span>
        ))}
      </div>
      <p className="chart-caption">Vertical line = this case at {pmaWeeks} wk PMA. Dots mark each pathway&apos;s maturation there.</p>
    </div>
  );
}
