/** OPC-style quality helpers for HMI badges (G / U / B). */

export type QualityLabel = "GOOD" | "UNCERTAIN" | "BAD";

export function resolveQualityLabel(
  quality?: number | string | null,
  qualityLabel?: string | null
): QualityLabel {
  if (qualityLabel) {
    const upper = String(qualityLabel).toUpperCase();
    if (upper === "GOOD" || upper === "UNCERTAIN" || upper === "BAD") {
      return upper;
    }
  }
  if (typeof quality === "string") {
    const upper = quality.toUpperCase();
    if (upper === "GOOD" || upper === "UNCERTAIN" || upper === "BAD") {
      return upper;
    }
    const asNum = Number(quality);
    if (!Number.isNaN(asNum)) {
      return resolveQualityLabel(asNum);
    }
    return "GOOD";
  }
  if (quality == null || Number.isNaN(Number(quality))) {
    return "GOOD";
  }
  const q = Number(quality);
  if (q >= 0.99) return "GOOD";
  if (q >= 0.25) return "UNCERTAIN";
  return "BAD";
}

export function qualityBadgeLetter(label: QualityLabel): string {
  return label.charAt(0);
}

export function qualityBadgeTone(label: QualityLabel): string {
  if (label === "GOOD") return "success";
  if (label === "UNCERTAIN") return "warning";
  return "danger";
}

export function formatStaleAge(staleAgeMs?: number | null): string | null {
  if (staleAgeMs == null || Number.isNaN(staleAgeMs) || staleAgeMs < 0) {
    return null;
  }
  if (staleAgeMs < 1000) {
    return `${Math.round(staleAgeMs)} ms`;
  }
  const seconds = staleAgeMs / 1000;
  if (seconds < 60) {
    return `${seconds.toFixed(1)} s`;
  }
  const minutes = seconds / 60;
  if (minutes < 60) {
    return `${minutes.toFixed(1)} min`;
  }
  return `${(minutes / 60).toFixed(1)} h`;
}
