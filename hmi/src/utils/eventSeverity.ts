/**
 * Event journal severity badges.
 *
 * Documented scale in this product:
 * - Priority 1–5: 1 is highest urgency (ISA 18.2 / EEMUA 191 response time)
 * - Criticity 1–5: 5 is highest consequence (IEC 61511 / ISO 31000 risk matrix)
 * - 0: unclassified
 *
 * Palettes stay distinct so the two columns are readable side by side:
 * priority uses the ISA 101 alarm-priority ladder (red → gray),
 * criticity uses a magenta-to-green consequence ladder.
 */

const toLevel = (value: unknown): number | null => {
  if (value == null || value === "") return null;
  const n = typeof value === "number" ? value : Number(value);
  if (!Number.isFinite(n)) return null;
  return Math.trunc(n);
};

export function eventPriorityBadgeClass(value: unknown): string {
  const n = toLevel(value);
  if (n === 1) return "event-severity-badge event-priority-badge--1";
  if (n === 2) return "event-severity-badge event-priority-badge--2";
  if (n === 3) return "event-severity-badge event-priority-badge--3";
  if (n === 4) return "event-severity-badge event-priority-badge--4";
  if (n === 5) return "event-severity-badge event-priority-badge--5";
  if (n === 0) return "event-severity-badge event-priority-badge--0";
  return "event-severity-badge event-priority-badge--unknown";
}

export function eventCriticityBadgeClass(value: unknown): string {
  const n = toLevel(value);
  if (n === 5) return "event-severity-badge event-criticity-badge--5";
  if (n === 4) return "event-severity-badge event-criticity-badge--4";
  if (n === 3) return "event-severity-badge event-criticity-badge--3";
  if (n === 2) return "event-severity-badge event-criticity-badge--2";
  if (n === 1) return "event-severity-badge event-criticity-badge--1";
  if (n === 0) return "event-severity-badge event-criticity-badge--0";
  return "event-severity-badge event-criticity-badge--unknown";
}

export function eventSeverityHintKey(kind: "priority" | "criticity", value: unknown): string {
  const n = toLevel(value);
  if (n != null && n >= 0 && n <= 5) {
    return `events.${kind}Hint.${n}`;
  }
  return `events.${kind}Hint.unknown`;
}
