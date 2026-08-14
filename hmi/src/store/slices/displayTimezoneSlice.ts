import { createSlice, PayloadAction } from "@reduxjs/toolkit";
import {
  loadDisplayTimezoneMode,
  persistDisplayTimezoneMode,
  type DisplayTimezoneMode,
} from "../../utils/timezone";

export type DisplayTimezoneState = {
  mode: DisplayTimezoneMode;
  plantTimezone: string;
};

const initialState: DisplayTimezoneState = {
  mode: loadDisplayTimezoneMode(),
  plantTimezone: "",
};

const displayTimezoneSlice = createSlice({
  name: "displayTimezone",
  initialState,
  reducers: {
    setDisplayTimezoneMode(state, action: PayloadAction<DisplayTimezoneMode>) {
      state.mode = action.payload;
      persistDisplayTimezoneMode(state.mode);
    },
    setPlantTimezone(state, action: PayloadAction<string>) {
      state.plantTimezone = action.payload;
    },
  },
});

export const { setDisplayTimezoneMode, setPlantTimezone } = displayTimezoneSlice.actions;

export default displayTimezoneSlice.reducer;
