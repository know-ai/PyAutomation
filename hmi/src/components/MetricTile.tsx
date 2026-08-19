import clsx from "clsx";
import type { KeyboardEvent, MouseEvent } from "react";
import { Sparkline } from "./Sparkline";
import type { PerfAlarmLifecycle, TileTone } from "../services/performanceAlarms";
import { utilizationColor } from "../services/performanceColors";
import { useTranslation } from "../hooks/useTranslation";

type MetricTileProps = {
  label: string;
  value: string;
  raw?: number | null;
  max?: number;
  threshold?: number | null;
  hint?: string;
  tone?: TileTone;
  lifecycle?: PerfAlarmLifecycle;
  spark?: number[];
  alarmable?: boolean;
  thresholdLabel?: string;
  canConfigure?: boolean;
  variant?: "gauge" | "tile";
  onOpen?: () => void;
  onConfigure?: () => void;
};

const GAUGE_COLORS: Record<TileTone, string> = {
  ok: "#198754",
  warn: "#c9a227",
  error: "#dc3545",
  unknown: "#6c757d",
  shelved: "#6c757d",
};

function polar(cx: number, cy: number, r: number, deg: number): [number, number] {
  const rad = (deg * Math.PI) / 180;
  return [cx + r * Math.cos(rad), cy + r * Math.sin(rad)];
}

function arcPath(cx: number, cy: number, r: number, start: number, end: number): string {
  const [x0, y0] = polar(cx, cy, r, start);
  const [x1, y1] = polar(cx, cy, r, end);
  const large = end - start > 180 ? 1 : 0;
  return `M ${x0.toFixed(2)} ${y0.toFixed(2)} A ${r} ${r} 0 ${large} 1 ${x1.toFixed(2)} ${y1.toFixed(2)}`;
}

export function MetricGauge({
  raw,
  max = 100,
  threshold,
  tone = "unknown",
}: {
  raw?: number | null;
  max?: number;
  threshold?: number | null;
  tone?: TileTone;
}) {
  const ratio = raw == null || max <= 0 ? 0 : Math.max(0, Math.min(1, Number(raw) / max));
  const cx = 60;
  const cy = 54;
  const radius = 42;
  const start = 210;
  const sweep = 237.6;
  const segments = 36;
  const redAt = threshold != null && threshold > 0 ? Number(threshold) : max;
  const filled = Math.round(segments * ratio);
  const shelved = tone === "shelved";
  const pieces = Array.from({ length: segments }, (_, index) => {
    const a0 = start + (sweep * index) / segments;
    const a1 = start + (sweep * (index + 1)) / segments + 0.35;
    const valueAt = ((index + 0.5) / segments) * max;
    return {
      d: arcPath(cx, cy, radius, a0, a1),
      color: shelved ? GAUGE_COLORS.shelved : utilizationColor(valueAt, redAt),
      active: index < filled,
    };
  });
  const tip = polar(cx, cy, radius, start + sweep * ratio);
  return (
    <svg className="perf-gauge" viewBox="0 0 120 78" aria-hidden="true">
      {pieces.map((piece, index) => (
        <path
          key={index}
          className={piece.active ? undefined : "perf-gauge__idle"}
          d={piece.d}
          fill="none"
          stroke={piece.active ? piece.color : undefined}
          strokeWidth={piece.active ? 8 : 6}
          strokeLinecap="butt"
          opacity={piece.active ? 1 : 0.7}
        />
      ))}
      {filled > 0 ? <circle cx={tip[0]} cy={tip[1]} r="4" fill={pieces[Math.max(0, filled - 1)].color} /> : null}
    </svg>
  );
}

export function MetricTile({
  label,
  value,
  raw,
  max,
  threshold,
  hint,
  tone = "unknown",
  lifecycle = "normal",
  spark,
  alarmable = false,
  thresholdLabel,
  canConfigure = false,
  variant = "tile",
  onOpen,
  onConfigure,
}: MetricTileProps) {
  const { t } = useTranslation();
  const clickable = Boolean(onOpen);
  const status =
    lifecycle === "unack"
      ? t("performance.badgeActive")
      : lifecycle === "ack"
        ? t("performance.badgeAck")
        : lifecycle === "shelved"
          ? t("performance.badgeShelved")
          : alarmable
            ? t("performance.badgeOk")
            : null;

  const onKeyDown = (event: KeyboardEvent<HTMLElement>) => {
    if (!onOpen) return;
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      onOpen();
    }
  };

  const openConfigure = (event: MouseEvent) => {
    event.stopPropagation();
    onConfigure?.();
  };

  return (
    <article
      className={clsx(
        "perf-tile",
        `perf-tile--${tone}`,
        variant === "gauge" && "perf-tile--gauge",
        alarmable && "perf-tile--alarmable",
        clickable && "perf-tile--clickable"
      )}
      role={clickable ? "button" : undefined}
      tabIndex={clickable ? 0 : undefined}
      onClick={onOpen}
      onKeyDown={onKeyDown}
      aria-label={alarmable ? `${label}. ${status || ""}. ${thresholdLabel || ""}` : label}
    >
      <header className="perf-tile__head">
        <span className="perf-tile__label">{label}</span>
        <span className="perf-tile__tools">
          {alarmable ? (
            <i
              className="bi bi-bell perf-tile__mark"
              title={thresholdLabel ? t("performance.thresholdHint", { value: thresholdLabel }) : t("performance.alarmable")}
              aria-hidden="true"
            />
          ) : (
            <i className="bi bi-info-circle perf-tile__mark perf-tile__mark--info" title={t("performance.informative")} aria-hidden="true" />
          )}
          {canConfigure && onConfigure ? (
            <button
              type="button"
              className="perf-tile__gear"
              title={t("performance.alarmConfigure")}
              aria-label={t("performance.alarmConfigure")}
              onClick={openConfigure}
            >
              <i className="bi bi-gear" aria-hidden="true" />
            </button>
          ) : null}
        </span>
      </header>
      {variant === "gauge" && raw != null ? <MetricGauge raw={raw} max={max} threshold={threshold} tone={tone} /> : null}
      <span className="perf-tile__value">{value}</span>
      {status ? (
        <span className={clsx("perf-badge", `perf-badge--${lifecycle === "normal" ? "ok" : lifecycle}`)}>
          <span className={clsx("perf-badge__dot", lifecycle === "unack" && "perf-badge__dot--live")} />
          {status}
        </span>
      ) : null}
      {thresholdLabel ? <span className="perf-tile__threshold">{t("performance.thresholdLine", { value: thresholdLabel })}</span> : null}
      {spark && spark.length > 1 ? <Sparkline values={spark} tone={tone} /> : null}
      {hint ? <span className="perf-tile__hint">{hint}</span> : null}
    </article>
  );
}
