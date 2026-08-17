import { createSlice, PayloadAction } from "@reduxjs/toolkit";
import {
  applyDisplayDensityToDom,
  loadDisplayDensityFromStorage,
  persistDisplayDensity,
  type DisplayDensity,
} from "../../utils/displayDensity";

export type DisplayDensityState = {
  mode: DisplayDensity;
};

const initialMode = loadDisplayDensityFromStorage();
applyDisplayDensityToDom(initialMode);

const initialState: DisplayDensityState = {
  mode: initialMode,
};

const displayDensitySlice = createSlice({
  name: "displayDensity",
  initialState,
  reducers: {
    setDisplayDensity(state, action: PayloadAction<DisplayDensity>) {
      state.mode = action.payload;
      persistDisplayDensity(state.mode);
      applyDisplayDensityToDom(state.mode);
    },
  },
});

export const { setDisplayDensity } = displayDensitySlice.actions;

export default displayDensitySlice.reducer;
