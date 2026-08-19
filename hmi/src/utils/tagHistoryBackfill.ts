import { getTrends, type TrendsResponse } from "../services/tags";
import type { AppDispatch } from "../store/store";
import { backfillTagHistory, type TagHistoryPoint } from "../store/slices/tagsSlice";
import { formatInstantForBackend } from "./timezone";

/** Ventana de backfill al reconectar (alineada con BUFFER_SIZE_MIN del StripChart: 120 s). */
export const BACKFILL_WINDOW_SECONDS = 120;
const MIN_INTERVAL_MS = 5000;
const DEBOUNCE_MS = 300;

let lastRunAt = 0;
let debounceTimer: ReturnType<typeof setTimeout> | null = null;
let abortController: AbortController | null = null;

export function resetTagHistoryBackfillThrottle(): void {
  lastRunAt = 0;
}

const trendsToHistory = (response: TrendsResponse): Record<string, TagHistoryPoint[]> => {
  const out: Record<string, TagHistoryPoint[]> = {};
  for (const [name, series] of Object.entries(response)) {
    const values = series?.values;
    if (!values?.length) continue;
    const pts: TagHistoryPoint[] = [];
    for (const point of values) {
      if (
        point &&
        typeof point.x === "string" &&
        typeof point.y === "number" &&
        !Number.isNaN(point.y)
      ) {
        pts.push({ timestamp: point.x, value: point.y });
      }
    }
    if (pts.length > 0) out[name] = pts;
  }
  return out;
};

export function scheduleTagHistoryBackfill(
  tagNames: string[],
  timeZone: string,
  dispatch: AppDispatch,
  force = false
): void {
  if (tagNames.length === 0) return;

  if (debounceTimer) clearTimeout(debounceTimer);
  debounceTimer = setTimeout(() => {
    debounceTimer = null;
    void runTagHistoryBackfill(tagNames, timeZone, dispatch, force);
  }, DEBOUNCE_MS);
}

async function runTagHistoryBackfill(
  tagNames: string[],
  timeZone: string,
  dispatch: AppDispatch,
  force = false
): Promise<void> {
  const now = Date.now();
  if (!force && now - lastRunAt < MIN_INTERVAL_MS) return;
  lastRunAt = now;

  abortController?.abort();
  abortController = new AbortController();
  const { signal } = abortController;

  const end = new Date();
  const start = new Date(now - BACKFILL_WINDOW_SECONDS * 1000);

  try {
    const data = await getTrends(
      {
        tags: tagNames,
        greater_than_timestamp: formatInstantForBackend(start, timeZone),
        less_than_timestamp: formatInstantForBackend(end, timeZone),
        timezone: timeZone,
      },
      { signal }
    );

    if (signal.aborted) return;
    const payload = trendsToHistory(data);
    if (Object.keys(payload).length === 0) return;
    dispatch(backfillTagHistory(payload));
  } catch (_err) {
    if (signal.aborted) return;
    // Historiador opcional durante reconexión; el socket RT sigue activo.
  }
}
