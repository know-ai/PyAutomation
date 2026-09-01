import clsx from "clsx";
import { useEffect, useMemo, useRef, useState } from "react";
import { utilizationColor } from "../services/performanceColors";
import type { TrendPoint } from "../services/performanceTrends";
import { useTranslation } from "../hooks/useTranslation";

type TrendChartProps = {
  label: string;
  points: TrendPoint[];
  currentLabel: string;
  unit?: string;
  threshold?: number | null;
  redAt?: number | null;
  dragHandle?: boolean;
};

function formatTick(value: number): string {
  const abs = Math.abs(value);
  if (abs >= 100) return value.toLocaleString(undefined, { maximumFractionDigits: 0 });
  if (abs >= 10) return value.toLocaleString(undefined, { maximumFractionDigits: 1 });
  return value.toLocaleString(undefined, { maximumFractionDigits: 2 });
}

function niceNum(range: number, round: boolean): number {
  const safe = Math.max(range, 1e-9);
  const exp = Math.floor(Math.log10(safe));
  const f = safe / 10 ** exp;
  let nf: number;
  if (round) {
    if (f < 1.5) nf = 1;
    else if (f < 3) nf = 2;
    else if (f < 7) nf = 5;
    else nf = 10;
  } else if (f <= 1) nf = 1;
  else if (f <= 2) nf = 2;
  else if (f <= 5) nf = 5;
  else nf = 10;
  return nf * 10 ** exp;
}

function yScale(values: number[]): { ticks: number[]; min: number; max: number } {
  if (!values.length) return { ticks: [0, 1], min: 0, max: 1 };
  let minV = Math.min(...values);
  let maxV = Math.max(...values);
  if (minV === maxV) {
    const pad = Math.abs(minV) * 0.1 || 1;
    minV -= pad;
    maxV += pad;
  } else {
    const pad = (maxV - minV) * 0.08;
    minV -= pad;
    maxV += pad;
  }
  if (minV > 0 && minV < (maxV - minV) * 0.45) minV = 0;
  const range = niceNum(maxV - minV, false);
  const step = niceNum(range / 2, true);
  const niceMin = Math.floor(minV / step) * step;
  const niceMax = Math.ceil(maxV / step) * step;
  const ticks: number[] = [];
  for (let value = niceMin; value <= niceMax + step * 0.5; value += step) {
    ticks.push(Number(value.toPrecision(8)));
  }
  return { ticks, min: niceMin, max: niceMax === niceMin ? niceMin + step : niceMax };
}

function formatAgo(ms: number, t: (key: string, params?: Record<string, string | number>) => string): string {
  const seconds = Math.max(0, Math.round(ms / 1000));
  if (seconds < 90) return t("performance.trendAgoSec", { value: seconds });
  return t("performance.trendAgoMin", { value: Math.round(seconds / 60) });
}

export function TrendChart({ label, points, currentLabel, unit = "", threshold, redAt, dragHandle = false }: TrendChartProps) {
  const { t } = useTranslation();
  const wrapRef = useRef<HTMLDivElement | null>(null);
  const [size, setSize] = useState({ w: 320, h: 156 });

  useEffect(() => {
    const el = wrapRef.current;
    if (!el) return undefined;
    const measure = () => setSize({ w: Math.max(160, el.clientWidth), h: Math.max(120, el.clientHeight) });
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  const values = useMemo(() => points.map((point) => point.v), [points]);
  const current = points.length ? points[points.length - 1].v : null;
  const color =
    current == null
      ? "#6c757d"
      : redAt != null || threshold != null
        ? utilizationColor(current, redAt ?? threshold)
        : "#4c6ef5";
  const { ticks, min, max } = yScale(values);
  const span = max - min || 1;
  const t0 = points[0]?.t ?? Date.now();
  const t1 = points[points.length - 1]?.t ?? t0;
  const timeSpan = Math.max(t1 - t0, 1);

  const padL = 42;
  const padR = 10;
  const padT = 8;
  const padB = 22;
  const innerW = Math.max(1, size.w - padL - padR);
  const innerH = Math.max(1, size.h - padT - padB);

  const xOf = (time: number) => padL + ((time - t0) / timeSpan) * innerW;
  const yOf = (value: number) => padT + (1 - (value - min) / span) * innerH;

  const path = points
    .map((point, index) => `${index === 0 ? "M" : "L"}${xOf(point.t).toFixed(1)} ${yOf(point.v).toFixed(1)}`)
    .join(" ");
  const area = points.length
    ? `${path} L${xOf(t1).toFixed(1)} ${padT + innerH} L${xOf(t0).toFixed(1)} ${padT + innerH} Z`
    : "";

  const xLabels = [
    { x: padL, text: formatAgo(t1 - t0, t) },
    { x: padL + innerW / 2, text: formatAgo((t1 - t0) / 2, t) },
    { x: padL + innerW, text: t("performance.trendNow") },
  ];

  return (
    <article className="perf-trend">
      <header className={clsx("perf-trend__head", dragHandle && "lds-card-handle")}>
        <span className="perf-trend__label">{label}</span>
        <strong className="perf-trend__value" style={{ color }}>
          {currentLabel}
        </strong>
      </header>
      <div ref={wrapRef} className="perf-trend__plot">
        <svg
          width={size.w}
          height={size.h}
          viewBox={`0 0 ${size.w} ${size.h}`}
          role="img"
          aria-label={`${label}: ${currentLabel}`}
        >
          {ticks.map((tick) => {
            const y = yOf(tick);
            return (
              <g key={tick}>
                <line className="perf-trend__grid" x1={padL} x2={padL + innerW} y1={y} y2={y} />
                <text className="perf-trend__axis" x={padL - 6} y={y + 3} textAnchor="end">
                  {formatTick(tick)}
                  {unit && tick === ticks[ticks.length - 1] ? ` ${unit}` : ""}
                </text>
              </g>
            );
          })}
          {threshold != null && threshold >= min && threshold <= max ? (
            <line
              className="perf-trend__threshold"
              x1={padL}
              x2={padL + innerW}
              y1={yOf(threshold)}
              y2={yOf(threshold)}
            />
          ) : null}
          {area ? <path d={area} fill={color} opacity="0.12" /> : null}
          {points.length > 1 ? (
            <path d={path} fill="none" stroke={color} strokeWidth="2" strokeLinejoin="round" strokeLinecap="round" />
          ) : null}
          {current != null && points.length ? (
            <circle cx={xOf(t1)} cy={yOf(current)} r="3.2" fill={color} />
          ) : null}
          <line className="perf-trend__axis-line" x1={padL} x2={padL} y1={padT} y2={padT + innerH} />
          <line className="perf-trend__axis-line" x1={padL} x2={padL + innerW} y1={padT + innerH} y2={padT + innerH} />
          {xLabels.map((item, index) => (
            <text
              key={item.text + index}
              className="perf-trend__axis"
              x={item.x}
              y={size.h - 6}
              textAnchor={index === 0 ? "start" : index === 2 ? "end" : "middle"}
            >
              {item.text}
            </text>
          ))}
        </svg>
      </div>
    </article>
  );
}
