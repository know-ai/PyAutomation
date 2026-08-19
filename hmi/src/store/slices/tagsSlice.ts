import { createSlice, PayloadAction } from "@reduxjs/toolkit";
import type { Tag } from "../../services/tags";
import { logout } from "./authSlice";

/** ~12 min @ 1 Hz. Tope duro por tag: el buffer no crece sin límite. */
export const MAX_HISTORY_POINTS = 720;
/** Tope de tags con historial (LRU de no suscritos). ~64×720 pts ≈ 2 MB. */
export const MAX_HISTORY_TAGS = 64;
export const HISTORY_STORAGE_KEY = "pyautomation.tagHistory";
/** Tope de muestras encoladas por tag entre flushes (CA-RT-5). */
export const HISTORY_POINTS_PER_FLUSH = 20;

export interface TagHistoryPoint {
  timestamp: string;
  value: number;
}

interface TagsState {
  tagValues: Record<string, Tag>;
  tagHistory: Record<string, TagHistoryPoint[]>;
  historySubscribers: Record<string, number>;
}

const isValidPoint = (pt: unknown): pt is TagHistoryPoint => {
  if (!pt || typeof pt !== "object") return false;
  const p = pt as TagHistoryPoint;
  return typeof p.timestamp === "string" && typeof p.value === "number" && !Number.isNaN(p.value);
};

const trimHistory = (pts: TagHistoryPoint[]): TagHistoryPoint[] => {
  if (pts.length <= MAX_HISTORY_POINTS) return pts;
  return pts.slice(pts.length - MAX_HISTORY_POINTS);
};

export const mergeHistoryPoints = (
  existing: TagHistoryPoint[],
  incoming: TagHistoryPoint[]
): TagHistoryPoint[] => {
  if (incoming.length === 0) return existing;
  if (existing.length === 0) return trimHistory(incoming.filter(isValidPoint));

  const byTs = new Map<string, number>();
  for (const p of existing) byTs.set(p.timestamp, p.value);
  for (const p of incoming) {
    if (isValidPoint(p)) byTs.set(p.timestamp, p.value);
  }
  const merged = Array.from(byTs, ([timestamp, value]) => ({ timestamp, value }));
  merged.sort((a, b) => a.timestamp.localeCompare(b.timestamp));
  return trimHistory(merged);
};

const lastTimestamp = (pts: TagHistoryPoint[] | undefined): string => {
  if (!pts || pts.length === 0) return "";
  return pts[pts.length - 1]?.timestamp || "";
};

export const evictExcessHistory = (
  history: Record<string, TagHistoryPoint[]>,
  subscribers: Record<string, number> = {}
): Record<string, TagHistoryPoint[]> => {
  const names = Object.keys(history);
  if (names.length <= MAX_HISTORY_TAGS) return history;
  const overflow = names.length - MAX_HISTORY_TAGS;
  const ranked = names
    .filter((n) => !subscribers[n])
    .sort((a, b) => lastTimestamp(history[a]).localeCompare(lastTimestamp(history[b])));
  const next = { ...history };
  for (let i = 0; i < overflow && i < ranked.length; i++) {
    delete next[ranked[i]];
  }
  return next;
};

export const loadPersistedTagHistory = (): Record<string, TagHistoryPoint[]> => {
  try {
    if (typeof localStorage === "undefined") return {};
    const raw = localStorage.getItem(HISTORY_STORAGE_KEY);
    if (!raw) return {};
    const parsed = JSON.parse(raw);
    if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) return {};
    const out: Record<string, TagHistoryPoint[]> = {};
    for (const [name, pts] of Object.entries(parsed)) {
      if (typeof name !== "string" || !name || !Array.isArray(pts)) continue;
      out[name] = trimHistory(pts.filter(isValidPoint));
    }
    return evictExcessHistory(out);
  } catch (_e) {
    return {};
  }
};

export const persistTagHistory = (history: Record<string, TagHistoryPoint[]>): void => {
  if (typeof localStorage === "undefined") return;
  const bounded = evictExcessHistory(history);
  const payload: Record<string, TagHistoryPoint[]> = {};
  for (const [name, pts] of Object.entries(bounded)) {
    payload[name] = trimHistory(pts);
  }
  try {
    localStorage.setItem(HISTORY_STORAGE_KEY, JSON.stringify(payload));
  } catch (_e) {
    const names = Object.keys(payload).sort(
      (a, b) => lastTimestamp(payload[a]).localeCompare(lastTimestamp(payload[b]))
    );
    const keep = names.slice(Math.floor(names.length / 2));
    const reduced: Record<string, TagHistoryPoint[]> = {};
    keep.forEach((n) => {
      reduced[n] = payload[n];
    });
    try {
      localStorage.setItem(HISTORY_STORAGE_KEY, JSON.stringify(reduced));
    } catch (_retry) {
      try {
        localStorage.removeItem(HISTORY_STORAGE_KEY);
      } catch (_ignore) {
        // quota / private mode
      }
    }
  }
};

export const isTagHistoryTracked = (
  subscribers: Record<string, number>,
  history: Record<string, TagHistoryPoint[]>,
  name: string
): boolean => !!subscribers[name] || Array.isArray(history[name]);

const tagToHistoryPoint = (tag: Tag): TagHistoryPoint | null => {
  if (!tag.name || tag.value === undefined || tag.value === null) return null;
  const numericValue =
    typeof tag.value === "boolean" ? (tag.value ? 1 : 0) : Number(tag.value);
  if (Number.isNaN(numericValue)) return null;
  const timestamp =
    typeof tag.timestamp === "string" ? tag.timestamp : new Date().toISOString();
  return { timestamp, value: numericValue };
};

const appendPointsToHistory = (state: TagsState, name: string, tags: Tag[]) => {
  if (!name || tags.length === 0) return;
  if (!isTagHistoryTracked(state.historySubscribers, state.tagHistory, name)) return;
  const history = state.tagHistory[name] || [];
  for (const tag of tags) {
    const point = tagToHistoryPoint(tag);
    if (!point) continue;
    history.push(point);
  }
  if (history.length > MAX_HISTORY_POINTS) {
    history.splice(0, history.length - MAX_HISTORY_POINTS);
  }
  state.tagHistory[name] = history;
  if (Object.keys(state.tagHistory).length > MAX_HISTORY_TAGS) {
    state.tagHistory = evictExcessHistory(state.tagHistory, state.historySubscribers);
  }
};

const initialState: TagsState = {
  tagValues: {},
  tagHistory: loadPersistedTagHistory(),
  historySubscribers: {},
};

const tagsSlice = createSlice({
  name: "tags",
  initialState,
  reducers: {
    updateTagValue: (state, action: PayloadAction<Tag>) => {
      const tag = action.payload;
      if (tag.name) {
        state.tagValues[tag.name] = tag;
      }
    },
    updateTagValuesBatch: (state, action: PayloadAction<Tag[]>) => {
      action.payload.forEach((tag) => {
        if (tag.name) {
          state.tagValues[tag.name] = tag;
        }
      });
    },
    appendTagHistoryPoints: (
      state,
      action: PayloadAction<Array<{ name: string; points: Tag[] }>>
    ) => {
      action.payload.forEach(({ name, points }) => {
        appendPointsToHistory(state, name, points);
      });
    },
    backfillTagHistory: (
      state,
      action: PayloadAction<Record<string, TagHistoryPoint[]>>
    ) => {
      for (const [name, points] of Object.entries(action.payload)) {
        if (!state.historySubscribers[name]) continue;
        const existing = state.tagHistory[name] || [];
        state.tagHistory[name] = mergeHistoryPoints(existing, points);
      }
      if (Object.keys(state.tagHistory).length > MAX_HISTORY_TAGS) {
        state.tagHistory = evictExcessHistory(state.tagHistory, state.historySubscribers);
      }
    },
    subscribeTagHistory: (state, action: PayloadAction<string>) => {
      const name = action.payload;
      if (!name) return;
      state.historySubscribers[name] = (state.historySubscribers[name] || 0) + 1;
      if (!state.tagHistory[name]) {
        state.tagHistory[name] = [];
      }
      if (Object.keys(state.tagHistory).length > MAX_HISTORY_TAGS) {
        state.tagHistory = evictExcessHistory(state.tagHistory, state.historySubscribers);
      }
    },
    unsubscribeTagHistory: (state, action: PayloadAction<string>) => {
      const name = action.payload;
      if (!name) return;
      const next = (state.historySubscribers[name] || 1) - 1;
      if (next <= 0) {
        delete state.historySubscribers[name];
        // Conservar tagHistory: navegar o desmontar StripChart no vacía el buffer.
      } else {
        state.historySubscribers[name] = next;
      }
    },
    clearTagValues: (state) => {
      state.tagValues = {};
      state.historySubscribers = {};
      // tagHistory se conserva (tope MAX_HISTORY_POINTS / MAX_HISTORY_TAGS).
    },
  },
    extraReducers: (builder) => {
    builder.addCase(logout, (state) => {
      // Política de producto: tagHistory acotado (720×64) se persiste; no se vacía en logout.
      persistTagHistory(state.tagHistory);
      state.tagValues = {};
      state.historySubscribers = {};
    });
  },
});

export const {
  updateTagValue,
  updateTagValuesBatch,
  appendTagHistoryPoints,
  backfillTagHistory,
  subscribeTagHistory,
  unsubscribeTagHistory,
  clearTagValues,
} = tagsSlice.actions;
export default tagsSlice.reducer;
