import { API_BASE_URL } from "../config/constants";

export const PROCESS_RESTART_EVENT = "pyautomation:process-restart";
export const DEFAULT_RESTART_ETA_S = 95;

const STORAGE_KEY = "pyautomation.processRestart";
const STALE_MS = 15 * 60 * 1000;

export type ProcessRestartSession = {
  startedAt: number;
  etaMs: number;
  sawDown: boolean;
};

function emitChange(): void {
  window.dispatchEvent(new Event(PROCESS_RESTART_EVENT));
}

export function readProcessRestart(): ProcessRestartSession | null {
  try {
    const raw = sessionStorage.getItem(STORAGE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as ProcessRestartSession;
    if (!parsed?.startedAt || !parsed?.etaMs) return null;
    if (Date.now() - parsed.startedAt > STALE_MS) {
      sessionStorage.removeItem(STORAGE_KEY);
      return null;
    }
    return parsed;
  } catch {
    return null;
  }
}

export function isProcessRestartActive(): boolean {
  return readProcessRestart() !== null;
}

export function beginProcessRestart(etaS?: number): void {
  const seconds =
    typeof etaS === "number" && Number.isFinite(etaS) && etaS > 0
      ? etaS
      : DEFAULT_RESTART_ETA_S;
  const session: ProcessRestartSession = {
    startedAt: Date.now(),
    etaMs: Math.round(seconds * 1000),
    sawDown: false,
  };
  try {
    sessionStorage.setItem(STORAGE_KEY, JSON.stringify(session));
  } catch {
    // ignore quota / private mode
  }
  emitChange();
}

export function markProcessRestartSawDown(): void {
  const current = readProcessRestart();
  if (!current || current.sawDown) return;
  try {
    sessionStorage.setItem(
      STORAGE_KEY,
      JSON.stringify({ ...current, sawDown: true })
    );
  } catch {
    // ignore
  }
}

export function clearProcessRestart(): void {
  try {
    sessionStorage.removeItem(STORAGE_KEY);
  } catch {
    // ignore
  }
  emitChange();
}

export async function pingProcessHealth(): Promise<boolean> {
  const ctrl = new AbortController();
  const timer = window.setTimeout(() => ctrl.abort(), 2500);
  try {
    const res = await fetch(`${API_BASE_URL}/health/ping`, {
      method: "GET",
      cache: "no-store",
      signal: ctrl.signal,
    });
    return res.ok;
  } catch {
    return false;
  } finally {
    window.clearTimeout(timer);
  }
}
