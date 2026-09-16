import { createSlice, configureStore } from "@reduxjs/toolkit";
import alarmsReducer, {
  CATALOG_PAGE_MAX,
  HISTORY_PAGE_MAX,
  TOP3_MAX,
  setAlarmsPage,
  setHistory,
  updateAlarmFromSocket,
} from "../alarmsSlice";
import type { Alarm } from "../../../services/alarms";

function makeAlarm(i: number, live = true): Alarm {
  return {
    name: `ALM.${i}`,
    identifier: `id-${i}`,
    tag: `TAG_${i}`,
    state: live
      ? { mnemonic: "UNACK", state: "Unacknowledged", annunciate_status: "Annunciated" }
      : { mnemonic: "NORM", state: "Normal", annunciate_status: "Not Annunciated" },
    last_transition_ts: new Date(Date.now() - i).toISOString(),
  };
}

describe("alarmsSlice bounds", () => {
  test("store nunca excede 3 elementos en top3Active", () => {
    const store = configureStore({ reducer: { alarms: alarmsReducer } });
    for (let i = 0; i < 1000; i++) {
      store.dispatch(updateAlarmFromSocket(makeAlarm(i)));
    }
    expect(store.getState().alarms.top3Active.length).toBeLessThanOrEqual(TOP3_MAX);
  });

  test("page nunca excede 50 elementos", () => {
    const store = configureStore({ reducer: { alarms: alarmsReducer } });
    const page = Array.from({ length: 200 }, (_, i) => makeAlarm(i));
    store.dispatch(setAlarmsPage(page));
    expect(store.getState().alarms.page.length).toBeLessThanOrEqual(CATALOG_PAGE_MAX);
  });

  test("history nunca excede 100 elementos", () => {
    const store = configureStore({ reducer: { alarms: alarmsReducer } });
    const rows = Array.from({ length: 500 }, (_, i) => ({ id: i, name: `H${i}` }));
    store.dispatch(setHistory(rows));
    expect(store.getState().alarms.history.length).toBeLessThanOrEqual(HISTORY_PAGE_MAX);
  });
});
