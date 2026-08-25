import { getHistoryBackfill } from "../services/history";
import { loadStationRealtimeTrends } from "../services/workspaceStore";
import { store, type AppDispatch } from "../store/store";
import {
  backfillTagHistory,
  DEFAULT_TIME_SPAN_MINUTES,
  MAX_HISTORY_TIME_MS,
  normalizeTimeSpanMinutes,
  pointTimeMs,
  type TagHistoryPoint,
} from "../store/slices/tagsSlice";

/** Default strip-chart window (2 min). Cap = max UI span (5 min). */
export const DEFAULT_BACKFILL_WINDOW_MS = DEFAULT_TIME_SPAN_MINUTES * 60 * 1000;
export const MAX_BACKFILL_WINDOW_MS = MAX_HISTORY_TIME_MS;
/** Skip backfill for blips shorter than this. */
export const MIN_BACKFILL_GAP_MS = 1_000;
const MIN_INTERVAL_MS = 5_000;
const DEBOUNCE_MS = 300;

let lastRunAt = 0;
let debounceTimer: ReturnType<typeof setTimeout> | null = null;
let abortController: AbortController | null = null;

export function resetTagHistoryBackfillThrottle(): void {
  lastRunAt = 0;
}

/** Largest time-span among station realtime charts (1–5 min). */
export function resolveRealtimeBackfillWindowMs(): number {
  try {
    const charts = loadStationRealtimeTrends().charts;
    let maxMin = DEFAULT_TIME_SPAN_MINUTES;
    for (const chart of charts) {
      const minutes = normalizeTimeSpanMinutes(chart.timeSpanMinutes);
      if (minutes > maxMin) maxMin = minutes;
    }
    return Math.min(MAX_BACKFILL_WINDOW_MS, Math.max(60_000, maxMin * 60 * 1000));
  } catch {
    return DEFAULT_BACKFILL_WINDOW_MS;
  }
}

/** Latest timestamp across subscribed tag histories (epoch ms). */
export function latestSubscribedHistoryMs(tagNames: string[]): number | null {
  const { tagHistory } = store.getState().tags;
  let latest: number | null = null;
  for (const name of tagNames) {
    const pts = tagHistory[name];
    if (!pts?.length) continue;
    const ms = pointTimeMs(pts[pts.length - 1]);
    if (!Number.isFinite(ms)) continue;
    if (latest === null || ms > latest) latest = ms;
  }
  return latest;
}

export function computeBackfillRange(
  nowMs: number,
  lastReceivedMs: number | null,
  windowMs: number
): { fromMs: number; toMs: number; gapMs: number } | null {
  const span = Math.min(MAX_BACKFILL_WINDOW_MS, Math.max(60_000, windowMs));
  const windowStart = nowMs - span;
  const fromMs =
    lastReceivedMs != null && Number.isFinite(lastReceivedMs)
      ? Math.max(lastReceivedMs, windowStart)
      : windowStart;
  const toMs = nowMs;
  const gapMs = toMs - fromMs;
  if (gapMs < MIN_BACKFILL_GAP_MS) return null;
  return { fromMs, toMs, gapMs };
}

export function scheduleTagHistoryBackfill(
  tagNames: string[],
  _timeZone: string,
  dispatch: AppDispatch,
  force = false
): void {
  if (tagNames.length === 0) return;

  if (debounceTimer) clearTimeout(debounceTimer);
  debounceTimer = setTimeout(() => {
    debounceTimer = null;
    void runTagHistoryBackfill(tagNames, dispatch, force);
  }, DEBOUNCE_MS);
}

async function runTagHistoryBackfill(
  tagNames: string[],
  dispatch: AppDispatch,
  force = false
): Promise<void> {
  const now = Date.now();
  if (!force && now - lastRunAt < MIN_INTERVAL_MS) return;

  const windowMs = resolveRealtimeBackfillWindowMs();
  const lastMs = latestSubscribedHistoryMs(tagNames);
  const range = computeBackfillRange(now, lastMs, windowMs);
  if (!range) return;

  lastRunAt = now;
  abortController?.abort();
  abortController = new AbortController();
  const { signal } = abortController;

  try {
    const payload = await getHistoryBackfill(tagNames, range.fromMs, range.toMs, {
      signal,
    });
    if (signal.aborted) return;
    if (Object.keys(payload).length === 0) return;
    dispatch(backfillTagHistory(payload as Record<string, TagHistoryPoint[]>));
  } catch (_err) {
    if (signal.aborted) return;
    // Historiador opcional durante reconexión; el socket RT sigue activo.
  }
}
