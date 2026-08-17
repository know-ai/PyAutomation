export type DisplayDensity = "auto" | "workstation" | "control" | "wall";

export const DISPLAY_DENSITY_STORAGE_KEY = "pyautomation.displayDensity";

export const DISPLAY_DENSITY_SCALES: Record<Exclude<DisplayDensity, "auto">, number> = {
  workstation: 1,
  control: 1.28,
  wall: 1.52,
};

const DENSITIES: DisplayDensity[] = ["auto", "workstation", "control", "wall"];

export function isDisplayDensity(value: unknown): value is DisplayDensity {
  return typeof value === "string" && DENSITIES.includes(value as DisplayDensity);
}

export function loadDisplayDensityFromStorage(): DisplayDensity {
  try {
    const saved = localStorage.getItem(DISPLAY_DENSITY_STORAGE_KEY);
    if (isDisplayDensity(saved)) return saved;
  } catch (_e) {
    // ignore
  }
  return "auto";
}

export function persistDisplayDensity(mode: DisplayDensity) {
  try {
    localStorage.setItem(DISPLAY_DENSITY_STORAGE_KEY, mode);
  } catch (_e) {
    // ignore
  }
}

/**
 * Escala automática: no toca 1920×1080 de escritorio.
 * Sube en lienzos nativos 2K/4K (TVs sin scaling del SO).
 */
export function computeAutoScale(): number {
  if (typeof window === "undefined") return 1;
  const width = window.innerWidth;
  const height = window.innerHeight;
  const dpr = window.devicePixelRatio || 1;
  const nativeCanvas = dpr <= 1.2;

  if (nativeCanvas && width >= 3840 && height >= 2000) return DISPLAY_DENSITY_SCALES.wall;
  if (nativeCanvas && width >= 2560 && height >= 1400) return DISPLAY_DENSITY_SCALES.control;
  if (width >= 3840) return 1.18;
  if (width >= 3000) return 1.1;
  return 1;
}

export function resolveDisplayScale(mode: DisplayDensity): number {
  if (mode === "auto") return computeAutoScale();
  return DISPLAY_DENSITY_SCALES[mode];
}

export function applyDisplayDensityToDom(mode: DisplayDensity, scale = resolveDisplayScale(mode)) {
  if (typeof document === "undefined") return;
  const html = document.documentElement;
  html.setAttribute("data-hmi-density", mode);
  html.style.setProperty("--hmi-ui-scale", String(scale));
}

export function readUiScale(): number {
  if (typeof document === "undefined") return 1;
  const raw = getComputedStyle(document.documentElement).getPropertyValue("--hmi-ui-scale");
  const scale = Number.parseFloat(raw);
  return Number.isFinite(scale) && scale > 0 ? scale : 1;
}
