import { createSlice, PayloadAction } from "@reduxjs/toolkit";
import type { Tag } from "../../services/tags";

const MAX_HISTORY_POINTS = 10000;

export interface TagHistoryPoint {
  timestamp: string;
  value: number;
}

interface TagsState {
  // Map of tag name -> latest tag data with value
  tagValues: Record<string, Tag>;
  // Histórico por tag para tendencias en tiempo real
  tagHistory: Record<string, TagHistoryPoint[]>;
}

const initialState: TagsState = {
  tagValues: {},
  tagHistory: {},
};

const pushHistoryPoint = (state: TagsState, tag: Tag) => {
  if (!tag.name || tag.value === undefined || tag.value === null) return;
  const numericValue =
    typeof tag.value === "boolean" ? (tag.value ? 1 : 0) : Number(tag.value);
  if (Number.isNaN(numericValue)) return;

  const history = state.tagHistory[tag.name] || [];
  const timestamp =
    typeof tag.timestamp === "string"
      ? tag.timestamp
      : new Date().toISOString();

  const newHistory: TagHistoryPoint[] = [
    ...history,
    { timestamp, value: numericValue },
  ].slice(-MAX_HISTORY_POINTS);

  state.tagHistory[tag.name] = newHistory;
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
    clearTagValues: (state) => {
      state.tagValues = {};
      state.tagHistory = {};
    },
  },
});

export const { updateTagValue, updateTagValuesBatch, clearTagValues } = tagsSlice.actions;
export default tagsSlice.reducer;

