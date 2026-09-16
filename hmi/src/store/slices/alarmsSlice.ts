import { createSlice, PayloadAction, createSelector } from "@reduxjs/toolkit";
import type { Alarm } from "../../services/alarms";
import { logout } from "./authSlice";
import { isAnnunciatedAlarm } from "../../utils/alarmState";

export const TOP3_MAX = 3;
export const CATALOG_PAGE_MAX = 50;
export const HISTORY_PAGE_MAX = 100;

export type HistoryRow = Record<string, unknown> & {
  id?: string | number;
  name?: string;
};

interface AlarmsState {
  // INV-43: never the full catalog
  top3Active: Alarm[];
  countByState: Record<string, number>;
  page: Alarm[];
  pageNumber: number;
  pageSize: number;
  hasNext: boolean;
  history: HistoryRow[];
  historyAlarmId: number | string | null;
  historyPage: number;
  historyHasNext: boolean;
}

const initialState: AlarmsState = {
  top3Active: [],
  countByState: {},
  page: [],
  pageNumber: 1,
  pageSize: 50,
  hasNext: false,
  history: [],
  historyAlarmId: null,
  historyPage: 1,
  historyHasNext: false,
};

function alarmKey(alarm: Alarm | HistoryRow | null | undefined): string | null {
  if (!alarm) return null;
  const key = (alarm as Alarm).identifier || alarm.id || alarm.name;
  return key ? String(key) : null;
}

function isLiveAlarm(alarm: Alarm): boolean {
  if (alarm.delay_phase === "pending" || alarm.delay_phase === "clearing") {
    return true;
  }
  return isAnnunciatedAlarm(alarm.state);
}

function sortByTransition(a: Alarm, b: Alarm): number {
  const pa = Number(a.priority ?? 3);
  const pb = Number(b.priority ?? 3);
  if (pa !== pb) return pa - pb;
  const aTime = Date.parse(String(a.last_transition_ts || a.timestamp || "")) || 0;
  const bTime = Date.parse(String(b.last_transition_ts || b.timestamp || "")) || 0;
  return bTime - aTime;
}

export function upsertTop3(list: Alarm[], incoming: Alarm): Alarm[] {
  const key = alarmKey(incoming);
  const next = list.filter((item) => alarmKey(item) !== key);
  if (isLiveAlarm(incoming)) {
    next.push(incoming);
  }
  return next.sort(sortByTransition).slice(0, TOP3_MAX);
}

export function clampPage(items: Alarm[]): Alarm[] {
  return items.slice(0, CATALOG_PAGE_MAX);
}

export function clampHistory(items: HistoryRow[]): HistoryRow[] {
  return items.slice(0, HISTORY_PAGE_MAX);
}

function patchPage(page: Alarm[], incoming: Alarm): Alarm[] {
  const key = alarmKey(incoming);
  if (!key) return clampPage(page);
  return clampPage(
    page.map((item) => (alarmKey(item) === key ? { ...item, ...incoming } : item))
  );
}

const alarmsSlice = createSlice({
  name: "alarms",
  initialState,
  reducers: {
    setTop3Active: (state, action: PayloadAction<Alarm[]>) => {
      state.top3Active = action.payload
        .filter(isLiveAlarm)
        .sort(sortByTransition)
        .slice(0, TOP3_MAX);
    },
    setCountByState: (state, action: PayloadAction<Record<string, number>>) => {
      state.countByState = action.payload || {};
    },
    setAlarmsPage: (state, action: PayloadAction<Alarm[]>) => {
      state.page = clampPage(action.payload);
    },
    setPageMeta: (
      state,
      action: PayloadAction<{ pageNumber?: number; pageSize?: number; hasNext?: boolean }>
    ) => {
      if (action.payload.pageNumber != null) state.pageNumber = action.payload.pageNumber;
      if (action.payload.pageSize != null) {
        state.pageSize = Math.min(CATALOG_PAGE_MAX, Math.max(1, action.payload.pageSize));
      }
      if (action.payload.hasNext != null) state.hasNext = action.payload.hasNext;
    },
    setHistory: (state, action: PayloadAction<HistoryRow[]>) => {
      state.history = clampHistory(action.payload);
    },
    updateAlarmFromSocket: (state, action: PayloadAction<Alarm>) => {
      const alarm = action.payload;
      state.top3Active = upsertTop3(state.top3Active, alarm);
      state.page = patchPage(state.page, alarm);
    },
    updateAlarm: (state, action: PayloadAction<Alarm>) => {
      const alarm = action.payload;
      state.top3Active = upsertTop3(state.top3Active, alarm);
      state.page = patchPage(state.page, alarm);
    },
    updateAlarmsBatch: (state, action: PayloadAction<Alarm[]>) => {
      let top3 = state.top3Active;
      let page = state.page;
      action.payload.forEach((alarm) => {
        top3 = upsertTop3(top3, alarm);
        page = patchPage(page, alarm);
      });
      state.top3Active = top3.slice(0, TOP3_MAX);
      state.page = clampPage(page);
    },
    clearAlarms: (state) => {
      state.top3Active = [];
      state.page = [];
      state.history = [];
      state.historyAlarmId = null;
    },
    loadAllAlarms: (state, action: PayloadAction<Alarm[]>) => {
      // INV-43: treat as footer hydrate, never store the catalog.
      state.top3Active = action.payload
        .filter(isLiveAlarm)
        .sort(sortByTransition)
        .slice(0, TOP3_MAX);
    },
  },
  extraReducers: (builder) => {
    builder.addCase(logout, (state) => {
      state.top3Active = [];
      state.page = [];
      state.hasNext = false;
      state.pageNumber = 1;
      state.history = [];
      state.historyAlarmId = null;
      // CA-P1-6-8: keep countByState
    });
  },
});

export const {
  setTop3Active,
  setCountByState,
  setAlarmsPage,
  setPageMeta,
  setHistory,
  updateAlarmFromSocket,
  updateAlarm,
  updateAlarmsBatch,
  clearAlarms,
  loadAllAlarms,
} = alarmsSlice.actions;
export default alarmsSlice.reducer;

export const selectActiveAlarmsPreview = createSelector(
  [(state: { alarms: AlarmsState }) => state.alarms.top3Active],
  (top3): Alarm[] => top3.slice(0, TOP3_MAX)
);
