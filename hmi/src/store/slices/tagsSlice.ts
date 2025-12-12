import { createSlice, PayloadAction } from "@reduxjs/toolkit";
import type { Tag } from "../../services/tags";

interface TagsState {
  // Map of tag name -> latest tag data with value
  tagValues: Record<string, Tag>;
}

const initialState: TagsState = {
  tagValues: {},
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
    clearTagValues: (state) => {
      state.tagValues = {};
    },
  },
});

export const { updateTagValue, updateTagValuesBatch, clearTagValues } = tagsSlice.actions;
export default tagsSlice.reducer;

