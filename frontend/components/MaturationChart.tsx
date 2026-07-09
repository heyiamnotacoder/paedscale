"use client";

interface Props {
  tm50Weeks: number;
  hill: number;
  pmaWeeks: number;
  pathwayName: string;
}

const WIDTH = 640;
const HEIGHT = 220;
const PAD_LEFT = 50;
const PAD_RIGHT = 16;
const PAD_TOP = 16;
const PAD_BOTTOM = 28;
const MAX_PMA = 200;

function maturationFraction(pma: number, tm50: number, hill: number): number {
  if (pma <= 0) return 0;
  return Math.pow(pma, hill) / (Math.pow(tm50, hill) + Math.pow(pma, hill));
}

export default function MaturationChart({ tm50Weeks, hill, pmaWeeks, pathwayName }: Props) {
  const plotWidth = WIDTH - PAD_LEFT - PAD_RIGHT;
  const plotHeight = HEIGHT - PAD_TOP - PAD_BOTTOM;

  const points: string[] = [];
  const steps = 60;
  for (let i = 0; i <= steps; i++) {
    const pma = (i / steps) * MAX_PMA;
    const mf = maturationFraction(pma, tm50Weeks, hill);
    const x = PAD_LEFT + (pma / MAX_PMA) * plotWidth;
    const y = PAD_TOP + (1 - mf) * plotHeight;
    points.push(`${x.toFixed(1)},${y.toFixed(1)}`);
  }

  const caseX = PAD_LEFT + (Math.min(pmaWeeks, MAX_PMA) / MAX_PMA) * plotWidth;
  const caseMf = maturationFraction(pmaWeeks, tm50Weeks, hill);
  const caseY = PAD_TOP + (1 - caseMf) * plotHeight;

  return (
    <div className="chart">
      <svg
        viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
        role="img"
        aria-label={`Maturation curve for ${pathwayName}: fraction of adult pathway activity versus postmenstrual age`}
      >
        {[0, 0.25, 0.5, 0.75, 1].map((f) => {
          const y = PAD_TOP + (1 - f) * plotHeight;
          return <line key={f} className="gridline" x1={PAD_LEFT} y1={y} x2={WIDTH - PAD_RIGHT} y2={y} />;
        })}
        <line className="axis" x1={PAD_LEFT} y1={HEIGHT - PAD_BOTTOM} x2={WIDTH - PAD_RIGHT} y2={HEIGHT - PAD_BOTTOM} />
        <line className="axis" x1={PAD_LEFT} y1={PAD_TOP} x2={PAD_LEFT} y2={HEIGHT - PAD_BOTTOM} />

        <text className="alab" x={14} y={HEIGHT - PAD_BOTTOM + 4}>
          0%
        </text>
        <text className="alab" x={10} y={PAD_TOP + 4}>
          100%
        </text>
        <text className="alab" x={PAD_LEFT} y={HEIGHT - 6}>
          0 wk PMA
        </text>
        <text className="alab" x={WIDTH - PAD_RIGHT - 60} y={HEIGHT - 6}>
          {MAX_PMA} wk PMA
        </text>

        <polyline className="curve" points={points.join(" ")} />

        <circle cx={caseX} cy={caseY} r={5} fill="#0E7A6B" />
        <line
          x1={caseX}
          y1={caseY}
          x2={caseX}
          y2={HEIGHT - PAD_BOTTOM}
          stroke="#0E7A6B"
          strokeDasharray="3 3"
          strokeWidth={1}
        />
      </svg>
      <p style={{ fontSize: "0.82rem", color: "var(--ink-3)", marginTop: 8 }}>
        This case sits at {(caseMf * 100).toFixed(0)}% of adult {pathwayName} activity at {pmaWeeks} weeks PMA
        (TM50 = {tm50Weeks} wk, Hill = {hill}).
      </p>
    </div>
  );
}
