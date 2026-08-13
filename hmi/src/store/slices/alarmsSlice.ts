import { createSlice, PayloadAction, createSelector } from "@reduxjs/toolkit";
import type { Alarm } from "../../services/alarms";
import { logout } from "./authSlice";

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
    loadAllAlarms: (state, action: PayloadAction<Alarm[]>) => {
      // Replace all alarms with the new list
      state.alarms = {};
      action.payload.forEach((alarm) => {
        const key = alarm.identifier || alarm.id || alarm.name;
        if (key) {
          state.alarms[String(key)] = alarm;
        }
      });
    },
  },
  extraReducers: (builder) => {
    builder.addCase(logout, (state) => {
      state.alarms = {};
    });
  },
});

export const { updateAlarm, updateAlarmsBatch, clearAlarms, loadAllAlarms } = alarmsSlice.actions;
export default alarmsSlice.reducer;

const PREVIEW_SIZE = 3;

function isActiveAlarm(alarm: Alarm): boolean {
  const state = alarm.state;
  if (typeof state === "object") {
    const stateStr = state.mnemonic || state.state || "";
    return stateStr.includes("UNACK") || stateStr.includes("ACK");
  }
  const stateStr = String(state);
  return stateStr.includes("Unacknowledged") || stateStr.includes("Acknowledged");
}

export const selectActiveAlarmsPreview = createSelector(
  [(state: { alarms: AlarmsState }) => state.alarms.alarms],
  (alarms): Alarm[] =>
    Object.values(alarms)
      .filter(isActiveAlarm)
      .sort((a, b) => {
        const aTime = a.timestamp ? new Date(a.timestamp).getTime() : 0;
        const bTime = b.timestamp ? new Date(b.timestamp).getTime() : 0;
        return bTime - aTime;
      })
      .slice(0, PREVIEW_SIZE)
);

