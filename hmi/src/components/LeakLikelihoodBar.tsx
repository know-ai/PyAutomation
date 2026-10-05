import type { Machine } from "../services/machines";
import { useTranslation } from "../hooks/useTranslation";

function readNumber(raw: unknown): number | null {
  if (typeof raw === "number" && Number.isFinite(raw)) return raw;
  if (typeof raw === "string" && raw.trim() !== "") {
    const parsed = Number(raw);
    return Number.isFinite(parsed) ? parsed : null;
  }
  if (raw && typeof raw === "object" && "value" in raw) {
    return readNumber((raw as { value?: unknown }).value);
  }
  return null;
}

function clampPercent(value: number): number {
  return Math.min(100, Math.max(0, value));
}

function isPercentUnit(unit: unknown): boolean {
  const text = String(unit ?? "").trim().toLowerCase();
  return text === "" || text === "%" || text === "percent" || text === "percentage";
}

/** Percent where leak_likelihood crossing it declares a leak. Statistic thresholds use another scale. */
export function leakThresholdPercent(machine: Machine): number | null {
  const mode = String(machine.detection_threshold_mode ?? "").toLowerCase();
  const activeUnit = machine.active_detection_threshold_unit;
  if (mode === "statistic" || String(activeUnit ?? "").trim().toLowerCase() === "adim") {
    return null;
  }
  const active = readNumber(machine.active_detection_threshold);
  if (active != null && isPercentUnit(activeUnit)) return clampPercent(active);

  const threshold = machine.threshold;
  const unit = threshold && typeof threshold === "object" ? (threshold as { unit?: unknown }).unit : undefined;
  if (!isPercentUnit(unit)) return null;
  const value = readNumber(threshold);
  return value == null ? null : clampPercent(value);
}

/** Green holds, then yellow, orange exactly at the leak threshold, then red. */
export function leakLikelihoodGradient(threshold: number | null): string {
  const orange = threshold == null ? 66 : clampPercent(threshold);
  const span = Math.max(6, Math.min(16, orange * 0.18));
  const yellow = Math.max(0, orange - span);
  const green = Math.min(yellow, yellow * 0.45);
  return `linear-gradient(90deg, #15803d 0%, #15803d ${green}%, #eab308 ${yellow}%, #f97316 ${orange}%, #b91c1c 100%)`;
}

function formatPercent(value: number, locale: string): string {
  const text = clampPercent(value).toLocaleString(locale === "es" ? "es-PE" : "en-US", {
    minimumFractionDigits: 0,
    maximumFractionDigits: 1,
  });
  return `${text}%`;
}

export function LeakLikelihoodBar({ machine }: { machine: Machine }) {
  const { t, locale } = useTranslation();
  if (machine.leak_likelihood == null) return <>-</>;

  const raw = readNumber(machine.leak_likelihood);
  const value = clampPercent(raw ?? 0);
  const threshold = leakThresholdPercent(machine);
  const label = formatPercent(value, locale);
  const thresholdLabel = threshold == null ? null : formatPercent(threshold, locale);

  return (
    <div
      className="leak-likelihood"
      role="meter"
      aria-valuemin={0}
      aria-valuemax={100}
      aria-valuenow={Math.round(value * 10) / 10}
      aria-label={t("machines.leakLikelihoodMeter", { value: label })}
      style={{
        ["--leak-pct" as string]: String(value),
        ["--leak-gradient" as string]: leakLikelihoodGradient(threshold),
        ["--leak-threshold" as string]: threshold == null ? "0" : String(threshold),
      }}
    >
      <div className="leak-likelihood-shell">
        <div className="leak-likelihood-scale" />
        <div className="leak-likelihood-fill" />
        <span className="leak-likelihood-value">
          <span>{label}</span>
        </span>
      </div>
      {thresholdLabel != null && (
        <span
          className="leak-likelihood-mark"
          title={t("machines.leakLikelihoodThresholdMark", { value: thresholdLabel })}
        />
      )}
    </div>
  );
}
