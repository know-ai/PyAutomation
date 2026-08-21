import type { Alarm } from "./alarms";
import api from "./api";
import type { PerfAlarmCatalogEntry, PerfAlarmKey, PerfAlarmsCatalog } from "./performance";
import { canViewOpsAdmin } from "../utils/access";

export type PerformanceAlarmConfig = PerfAlarmsCatalog & {
  enabled?: boolean;
  debounce_count?: number;
  alarms?: PerfAlarmCatalogEntry[];
};

export type PerfAlarmLifecycle = "normal" | "unack" | "ack" | "shelved" | "other";

export type TileTone = "ok" | "warn" | "error" | "unknown" | "shelved";

export function alarmNameMatches(alarmName: string | undefined, catalogName: string | undefined, key: string): boolean {
  const name = String(alarmName || "");
  if (!name) return false;
  if (catalogName && name === catalogName) return true;
  return name === `ALM.PERF.${key.toUpperCase()}` || name.endsWith(`.ALM.PERF.${key.toUpperCase()}`) || name.endsWith(`ALM.PERF.${key.toUpperCase()}`);
}

export function lifecycleOf(alarm: Alarm | undefined): PerfAlarmLifecycle {
  if (!alarm) return "normal";
  const state = alarm.state;
  const raw =
    typeof state === "object"
      ? `${state.mnemonic || ""} ${state.state || ""} ${state.acknowledge_status || ""}`
      : String(state || "");
  const normalized = raw.toLowerCase();
  if (normalized.includes("shelv") || normalized.includes("shlvd")) return "shelved";
  if (normalized.includes("unack")) return "unack";
  if (normalized.includes("ack")) return "ack";
  if (normalized.includes("normal") || normalized.includes("norm")) return "normal";
  return "other";
}

export function toneFromLifecycle(life: PerfAlarmLifecycle, fallback: TileTone = "unknown"): TileTone {
  if (life === "unack") return "error";
  if (life === "ack") return "warn";
  if (life === "shelved") return "shelved";
  return fallback;
}

export function canConfigurePerformanceAlarms(role?: string | null): boolean {
  return canViewOpsAdmin(role);
}

export function formatThresholdLabel(threshold?: number | null, unit?: string): string {
  if (threshold == null || Number.isNaN(Number(threshold))) return "";
  const suffix = unit ? ` ${unit}` : "";
  return `${Number(threshold).toLocaleString(undefined, { maximumFractionDigits: 1 })}${suffix}`;
}

export function previewExceeds(value: number | null | undefined, threshold: number | null | undefined): boolean {
  if (value == null || threshold == null) return false;
  return Number(value) >= Number(threshold);
}

export async function getPerformanceAlarmConfig(): Promise<PerformanceAlarmConfig> {
  const { data } = await api.get("/settings/performance", { timeout: 4000 });
  return data as PerformanceAlarmConfig;
}

export async function updatePerformanceAlarmConfig(
  payload: PerformanceAlarmConfig
): Promise<PerformanceAlarmConfig> {
  const { data } = await api.put("/settings/performance", payload, { timeout: 8000 });
  return data as PerformanceAlarmConfig;
}

export const PERF_ALARM_UNITS: Record<PerfAlarmKey, string> = {
  cpu: "%",
  disk: "%",
  saf_queue: "",
  saf_lag: "ms",
  metrics_age: "ms",
  db_conn: "",
  http_5xx: "/min",
};
