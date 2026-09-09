/** Canonical Real-Time Trends grid (schema v3). Legacy was 12 cols × rowHeight 40. */

export const GRID_COLS = 48;
export const GRID_ROW_HEIGHT = 10;
export const GRID_MARGIN: [number, number] = [10, 10];
export const MIN_GRID_W = 16;
export const MAX_GRID_W = 48;
export const MIN_GRID_H = 15;
export const MAX_GRID_H = 120;
export const DEFAULT_GRID_W = 24;
export const DEFAULT_GRID_H = 15;

export const LEGACY_GRID_COLS = 12;
export const LEGACY_ROW_HEIGHT = 40;
export const LEGACY_MARGIN_Y = 10;
export const LEGACY_MIN_W = 4;
export const LEGACY_MAX_W = 12;
export const LEGACY_MIN_H = 6;
export const LEGACY_MAX_H = 48;

export type GridMeta = { cols: number; rowHeight: number };

export type LayoutBox = { x: number; y: number; w: number; h: number };

export function isLayoutV3Enabled(): boolean {
  const raw = import.meta.env.VITE_RT_TRENDS_LAYOUT_V3;
  if (raw === "false" || raw === "0" || raw === "off") return false;
  return true;
}

function spanPx(rows: number, rowHeight: number, margin: number): number {
  const n = Math.max(0, rows);
  if (n <= 0) return 0;
  return n * rowHeight + (n - 1) * margin;
}

function rowsFromPx(px: number, rowHeight: number, margin: number): number {
  const step = rowHeight + margin;
  if (step <= 0) return 1;
  return Math.max(1, Math.round((Math.max(0, px) + margin) / step));
}

export function looksLikeLegacyBox(box: LayoutBox, schemaVersion: number, grid?: GridMeta | null): boolean {
  if (grid && grid.cols === GRID_COLS && grid.rowHeight === GRID_ROW_HEIGHT) return false;
  if (schemaVersion >= 3 && grid?.cols === GRID_COLS) return false;
  if (schemaVersion <= 2) return true;
  return box.w <= LEGACY_MAX_W && box.x + box.w <= LEGACY_GRID_COLS;
}

export function migrateBoxToV3(box: LayoutBox): LayoutBox {
  const yPx = box.y * (LEGACY_ROW_HEIGHT + LEGACY_MARGIN_Y);
  const hPx = spanPx(Math.max(box.h, 1), LEGACY_ROW_HEIGHT, LEGACY_MARGIN_Y);
  const yStep = GRID_ROW_HEIGHT + GRID_MARGIN[1];
  return {
    x: Math.round(box.x * (GRID_COLS / LEGACY_GRID_COLS)),
    w: Math.round(box.w * (GRID_COLS / LEGACY_GRID_COLS)),
    y: Math.round(yPx / yStep),
    h: rowsFromPx(hPx, GRID_ROW_HEIGHT, GRID_MARGIN[1]),
  };
}

export function migrateBoxToLegacy(box: LayoutBox): LayoutBox {
  const yPx = box.y * (GRID_ROW_HEIGHT + GRID_MARGIN[1]);
  const hPx = spanPx(Math.max(box.h, 1), GRID_ROW_HEIGHT, GRID_MARGIN[1]);
  const yStep = LEGACY_ROW_HEIGHT + LEGACY_MARGIN_Y;
  return {
    x: Math.round(box.x / (GRID_COLS / LEGACY_GRID_COLS)),
    w: Math.round(box.w / (GRID_COLS / LEGACY_GRID_COLS)),
    y: Math.round(yPx / yStep),
    h: rowsFromPx(hPx, LEGACY_ROW_HEIGHT, LEGACY_MARGIN_Y),
  };
}

function clamp(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value));
}

export function clampBoxV3(box: LayoutBox): LayoutBox {
  const w = clamp(Math.trunc(box.w), MIN_GRID_W, MAX_GRID_W);
  const h = clamp(Math.trunc(box.h), MIN_GRID_H, MAX_GRID_H);
  const x = clamp(Math.trunc(box.x), 0, MAX_GRID_W - MIN_GRID_W);
  const y = clamp(Math.trunc(box.y), 0, 10_000);
  return { x: Math.min(x, MAX_GRID_W - w), y, w, h };
}

export function clampBoxLegacy(box: LayoutBox): LayoutBox {
  const w = clamp(Math.trunc(box.w), LEGACY_MIN_W, LEGACY_MAX_W);
  const h = clamp(Math.trunc(box.h), LEGACY_MIN_H, LEGACY_MAX_H);
  const x = clamp(Math.trunc(box.x), 0, LEGACY_MAX_W - LEGACY_MIN_W);
  const y = clamp(Math.trunc(box.y), 0, 10_000);
  return { x: Math.min(x, LEGACY_MAX_W - w), y, w, h };
}
