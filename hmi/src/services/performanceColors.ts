export const PERF_GREEN = "#198754";
export const PERF_YELLOW = "#c9a227";
export const PERF_RED = "#dc3545";

function hexToRgb(hex: string): [number, number, number] {
  const raw = hex.replace("#", "");
  const n = parseInt(raw, 16);
  return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
}

function rgbToHex(r: number, g: number, b: number): string {
  return `#${[r, g, b].map((c) => Math.round(c).toString(16).padStart(2, "0")).join("")}`;
}

export function lerpColor(from: string, to: string, t: number): string {
  const clamped = Math.max(0, Math.min(1, t));
  const a = hexToRgb(from);
  const b = hexToRgb(to);
  return rgbToHex(a[0] + (b[0] - a[0]) * clamped, a[1] + (b[1] - a[1]) * clamped, a[2] + (b[2] - a[2]) * clamped);
}

/**
 * Green at idle, amber at ~55 % of the red point, red at/above the threshold.
 */
export function utilizationColor(value: number | null | undefined, redAt: number | null | undefined): string {
  if (value == null || redAt == null || redAt <= 0 || Number.isNaN(Number(value))) return "#6c757d";
  const t = Number(value) / Number(redAt);
  if (t <= 0) return PERF_GREEN;
  if (t >= 1) return PERF_RED;
  if (t <= 0.55) return lerpColor(PERF_GREEN, PERF_YELLOW, t / 0.55);
  return lerpColor(PERF_YELLOW, PERF_RED, (t - 0.55) / 0.45);
}
