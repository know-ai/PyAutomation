import { createSlice, PayloadAction } from "@reduxjs/toolkit";
import type { Alarm } from "../../services/alarms";

interface AlarmsState {
  // Map of alarm identifier/id -> latest alarm data
  alarms: Record<string, Alarm>;
}

const initialState: AlarmsState = {
  alarms: {},
};

const alarmsSlice = createSlice({
  name: "alarms",
  initialState,
  reducers: {
    updateAlarm: (state, action: PayloadAction<Alarm>) => {
      const alarm = action.payload;
      const key = alarm.identifier || alarm.id || alarm.name;
      if (key) {
        state.alarms[String(key)] = alarm;
      }
    },
    updateAlarmsBatch: (state, action: PayloadAction<Alarm[]>) => {
      action.payload.forEach((alarm) => {
        const key = alarm.identifier || alarm.id || alarm.name;
        if (key) {
          state.alarms[String(key)] = alarm;
        }
      });
    },
    clearAlarms: (state) => {
      state.alarms = {};
    },
  },
});

export const { updateAlarm, updateAlarmsBatch, clearAlarms } = alarmsSlice.actions;
export default alarmsSlice.reducer;

