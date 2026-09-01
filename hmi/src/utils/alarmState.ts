/**
 * ISA 18.2 lifecycle states + ISA 101 HMI salience for alarm badges.
 *
 * Unacknowledged → red (flashing is reserved for live banners)
 * Acknowledged (still abnormal) → orange, steady
 * RTN Unacknowledged → amber (process normal, ack still required)
 * Normal → green
 * Shelved → cyan (operator suppress)
 * Suppressed By Design → blue-gray
 * Out Of Service → violet (distinct from shelve)
 */

export type AlarmStateLike =
  | string
  | {
      mnemonic?: string;
      state?: string;
      name?: string;
    }
  | null
  | undefined;

const BADGE_BY_KEY: Record<string, string> = {
  unack: "alarm-state-badge alarm-state-badge--unack",
  unacknowledged: "alarm-state-badge alarm-state-badge--unack",
  acked: "alarm-state-badge alarm-state-badge--acked",
  acknowledged: "alarm-state-badge alarm-state-badge--acked",
  rtnun: "alarm-state-badge alarm-state-badge--rtnun",
  "rtn unacknowledged": "alarm-state-badge alarm-state-badge--rtnun",
  "rtn unack": "alarm-state-badge alarm-state-badge--rtnun",
  norm: "alarm-state-badge alarm-state-badge--normal",
  normal: "alarm-state-badge alarm-state-badge--normal",
  shlvd: "alarm-state-badge alarm-state-badge--shelved",
  shelved: "alarm-state-badge alarm-state-badge--shelved",
  dsupr: "alarm-state-badge alarm-state-badge--suppressed",
  "suppressed by design": "alarm-state-badge alarm-state-badge--suppressed",
  suppressed: "alarm-state-badge alarm-state-badge--suppressed",
  oosrv: "alarm-state-badge alarm-state-badge--oos",
  "out of service": "alarm-state-badge alarm-state-badge--oos",
};

const normalize = (value: string): string => value.trim().toLowerCase().replace(/[_-]+/g, " ");

export const ISA_ALARM_STATES = [
  "Normal",
  "Unacknowledged",
  "Acknowledged",
  "RTN Unacknowledged",
  "Shelved",
  "Suppressed By Design",
  "Out Of Service",
] as const;

const STATE_ALIASES: Record<string, string[]> = {
  normal: ["normal", "norm"],
  unacknowledged: ["unacknowledged", "unack"],
  acknowledged: ["acknowledged", "acked"],
  "rtn unacknowledged": ["rtn unacknowledged", "rtn unack", "rtnun"],
  shelved: ["shelved", "shlvd"],
  "suppressed by design": ["suppressed by design", "suppressed", "dsupr"],
  "out of service": ["out of service", "oosrv"],
};

function stateTokens(state: AlarmStateLike): string[] {
  if (state == null || state === "") return [];
  if (typeof state === "object") {
    return [state.mnemonic, state.state, state.name]
      .filter(Boolean)
      .map((value) => normalize(String(value)));
  }
  return [normalize(String(state))];
}

export function alarmStateMatches(state: AlarmStateLike, wanted: string): boolean {
  const needle = normalize(wanted);
  if (!needle) return true;
  const aliases = STATE_ALIASES[needle] || [needle];
  return stateTokens(state).some((token) => aliases.includes(token) || token === needle);
}

export function alarmMatchesSearch(
  alarm: { name?: string; description?: string; display_name?: string; tag?: string },
  query: string
): boolean {
  const needle = query.trim().toLowerCase();
  if (!needle) return true;
  const haystack = [alarm.name, alarm.description, alarm.display_name, alarm.tag]
    .filter(Boolean)
    .join(" ")
    .toLowerCase();
  return haystack.includes(needle);
}

export function isUnacknowledgedAlarm(state: AlarmStateLike): boolean {
  return (
    alarmStateMatches(state, "Unacknowledged") ||
    alarmStateMatches(state, "RTN Unacknowledged")
  );
}

export function isAnnunciatedAlarm(state: AlarmStateLike): boolean {
  return isUnacknowledgedAlarm(state) || alarmStateMatches(state, "Acknowledged");
}

export function alarmStateBadgeClass(state: AlarmStateLike): string {
  if (state == null || state === "") {
    return "alarm-state-badge alarm-state-badge--unknown";
  }
  if (typeof state === "object") {
    const mnemonic = state.mnemonic ? BADGE_BY_KEY[normalize(state.mnemonic)] : undefined;
    if (mnemonic) return mnemonic;
    const named = state.state || state.name;
    if (named) {
      const mapped = BADGE_BY_KEY[normalize(named)];
      if (mapped) return mapped;
    }
    return "alarm-state-badge alarm-state-badge--unknown";
  }
  return BADGE_BY_KEY[normalize(state)] || "alarm-state-badge alarm-state-badge--unknown";
}

export type AlarmDelayPhase = "pending" | "clearing" | null | undefined;

export function formatDelayRemaining(value: unknown): string {
  const n = typeof value === "number" ? value : Number(value);
  if (!Number.isFinite(n)) return "0";
  const rounded = Math.max(0, n);
  return Number.isInteger(rounded) ? String(rounded) : rounded.toFixed(1);
}

export function alarmDelayBadgeClass(phase: AlarmDelayPhase): string | null {
  if (phase === "pending") return "alarm-state-badge alarm-state-badge--pending";
  if (phase === "clearing") return "alarm-state-badge alarm-state-badge--clearing";
  return null;
}

