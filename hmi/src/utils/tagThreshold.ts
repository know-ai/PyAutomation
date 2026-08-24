/**
 * Resuelve umbrales de alarma/proceso para tendencias en tiempo real.
 */
import type { Machine } from "../services/machines";
import type { Tag } from "../services/tags";

export function parseThresholdValue(raw: unknown): number | null {
  if (raw == null) return null;
  if (typeof raw === "number") {
    return Number.isFinite(raw) ? raw : null;
  }
  if (typeof raw === "object") {
    const obj = raw as Record<string, unknown>;
    if ("value" in obj) {
      return parseThresholdValue(obj.value);
    }
  }
  const parsed = Number(raw);
  return Number.isFinite(parsed) ? parsed : null;
}

/** Umbral válido para dibujar (excluye 0 = sin configurar). */
export function isDisplayableThreshold(value: number | null | undefined): value is number {
  return value != null && Number.isFinite(value) && value !== 0;
}

export function extractMachineThreshold(machine: Machine): number | null {
  const row = machine as Record<string, unknown>;
  for (const key of ["active_detection_threshold", "threshold"]) {
    const value = parseThresholdValue(row[key]);
    if (isDisplayableThreshold(value)) {
      return value;
    }
  }
  return null;
}

function tagMatchesMachine(tagName: string, machineName: string): boolean {
  if (!machineName) return false;
  return (
    tagName === machineName ||
    tagName.startsWith(`${machineName}.`) ||
    tagName.endsWith(`.${machineName}`) ||
    tagName.includes(`.${machineName}.`)
  );
}

/**
 * Umbral por tag: preferir ``liveTag.threshold`` (socket) y resolver por máquina suscrita.
 */
export function resolveTagThreshold(
  tagName: string,
  machines: Record<string, Machine>,
  liveTag?: Tag | null
): number | null {
  const fromTag = parseThresholdValue(liveTag?.threshold);
  if (isDisplayableThreshold(fromTag)) {
    return fromTag;
  }

  for (const machine of Object.values(machines)) {
    const threshold = extractMachineThreshold(machine);
    if (!isDisplayableThreshold(threshold)) continue;

    const subs = (machine as Record<string, unknown>).subscribed_tags;
    if (subs && typeof subs === "object" && tagName in subs) {
      return threshold;
    }

    if (tagMatchesMachine(tagName, machine.name)) {
      return threshold;
    }
  }

  return null;
}
