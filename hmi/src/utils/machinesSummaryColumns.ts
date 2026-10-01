import type { Machine } from "../services/machines";

export const LOCKED_SUMMARY_COLUMNS = ["name", "state"] as const;
export const DEFAULT_SUMMARY_COLUMNS = [
  "name",
  "state",
  "criticity",
  "description",
  "classification",
];

const HIDDEN_COLUMN_KEYS = new Set([
  "actions",
  "identifier",
  "sample_overrides",
  "signal_modes",
  "has_domain_config",
]);

const KEY_PATTERN = /^[A-Za-z_][A-Za-z0-9_]*$/;

export function isSummaryColumnValue(value: unknown): boolean {
  if (value == null) return true;
  if (Array.isArray(value)) return false;
  if (typeof value === "object") return "value" in (value as object);
  return typeof value === "string" || typeof value === "number" || typeof value === "boolean";
}

export function uniqueMachineColumnKeys(machines: Machine[]): string[] {
  const found = new Set<string>(DEFAULT_SUMMARY_COLUMNS);
  for (const machine of machines) {
    for (const [key, value] of Object.entries(machine)) {
      if (!KEY_PATTERN.test(key) || HIDDEN_COLUMN_KEYS.has(key)) continue;
      if (isSummaryColumnValue(value)) found.add(key);
    }
  }
  const extras = Array.from(found)
    .filter((key) => !DEFAULT_SUMMARY_COLUMNS.includes(key))
    .sort((left, right) => left.localeCompare(right));
  return [...DEFAULT_SUMMARY_COLUMNS, ...extras];
}

export function normalizeSummaryColumns(raw: string[] | null | undefined, available: string[]): string[] {
  const allowed = new Set(available.length > 0 ? available : DEFAULT_SUMMARY_COLUMNS);
  const source = raw && raw.length > 0 ? raw : DEFAULT_SUMMARY_COLUMNS;
  const columns: string[] = [...LOCKED_SUMMARY_COLUMNS];
  const seen = new Set<string>(columns);
  for (const item of source) {
    const key = String(item || "").trim();
    if (!key || seen.has(key) || !allowed.has(key)) continue;
    seen.add(key);
    columns.push(key);
  }
  return columns;
}
