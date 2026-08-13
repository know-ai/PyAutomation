import { createSlice, PayloadAction } from "@reduxjs/toolkit";
import type { Tag } from "../../services/tags";
import { logout } from "./authSlice";

const MAX_HISTORY_POINTS = 720;

export interface TagHistoryPoint {
  timestamp: string;
  value: number;
}

interface TagsState {
  tagValues: Record<string, Tag>;
  tagHistory: Record<string, TagHistoryPoint[]>;
  historySubscribers: Record<string, number>;
}

const initialState: TagsState = {
  tagValues: {},
  tagHistory: {},
  historySubscribers: {},
};

const pushHistoryPoint = (state: TagsState, tag: Tag) => {
  if (!tag.name || tag.value === undefined || tag.value === null) return;
  if (!state.historySubscribers[tag.name]) return;
  const numericValue =
    typeof tag.value === "boolean" ? (tag.value ? 1 : 0) : Number(tag.value);
  if (Number.isNaN(numericValue)) return;

  const history = state.tagHistory[tag.name] || [];
  const timestamp =
    typeof tag.timestamp === "string"
      ? tag.timestamp
      : new Date().toISOString();

  history.push({ timestamp, value: numericValue });
  if (history.length > MAX_HISTORY_POINTS) {
    history.splice(0, history.length - MAX_HISTORY_POINTS);
  }
  state.tagHistory[tag.name] = history;
};

const tagsSlice = createSlice({
  name: "tags",
  initialState,
  reducers: {
    updateTagValue: (state, action: PayloadAction<Tag>) => {
      const tag = action.payload;
      if (tag.name) {
        state.tagValues[tag.name] = tag;
        pushHistoryPoint(state, tag);
      }
    },
    updateTagValuesBatch: (state, action: PayloadAction<Tag[]>) => {
      action.payload.forEach((tag) => {
        if (tag.name) {
          state.tagValues[tag.name] = tag;
          pushHistoryPoint(state, tag);
        }
      });
    },
    subscribeTagHistory: (state, action: PayloadAction<string>) => {
      const name = action.payload;
      if (!name) return;
      state.historySubscribers[name] = (state.historySubscribers[name] || 0) + 1;
    },
    unsubscribeTagHistory: (state, action: PayloadAction<string>) => {
      const name = action.payload;
      if (!name) return;
      const next = (state.historySubscribers[name] || 1) - 1;
      if (next <= 0) {
        delete state.historySubscribers[name];
        delete state.tagHistory[name];
      } else {
        state.historySubscribers[name] = next;
      }
    },
    clearTagValues: (state) => {
      state.tagValues = {};
      state.tagHistory = {};
      state.historySubscribers = {};
    },
  },
  extraReducers: (builder) => {
    builder.addCase(logout, (state) => {
      state.tagValues = {};
      state.tagHistory = {};
      state.historySubscribers = {};
    });
  },
});

export const {
  updateTagValue,
  updateTagValuesBatch,
  subscribeTagHistory,
  unsubscribeTagHistory,
  clearTagValues,
} = tagsSlice.actions;
export default tagsSlice.reducer;
export { MAX_HISTORY_POINTS };
