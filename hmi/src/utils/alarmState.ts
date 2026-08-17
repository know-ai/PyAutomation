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
