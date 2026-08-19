import { useEffect, useMemo } from "react";
import { createSelector } from "@reduxjs/toolkit";
import { getAlarms, type Alarm } from "../services/alarms";
import {
  alarmNameMatches,
  lifecycleOf,
  type PerfAlarmLifecycle,
} from "../services/performanceAlarms";
import type { PerfAlarmCatalogEntry, PerfAlarmKey, PerfAlarmsCatalog } from "../services/performance";
import { PERF_ALARM_KEYS } from "../services/performance";
import { updateAlarmsBatch } from "../store/slices/alarmsSlice";
import { useAppDispatch } from "./useAppDispatch";
import { useAppSelector } from "./useAppSelector";
import type { RootState } from "../store/store";

export type PerfAlarmBinding = {
  key: PerfAlarmKey;
  alarm?: Alarm;
  catalog?: PerfAlarmCatalogEntry;
  lifecycle: PerfAlarmLifecycle;
};

const selectAlarmMap = (state: RootState) => state.alarms.alarms;

const selectAlarmList = createSelector([selectAlarmMap], (alarms) => Object.values(alarms));

export function usePerformanceAlarms(catalog?: PerfAlarmsCatalog | null): Record<PerfAlarmKey, PerfAlarmBinding> {
  const dispatch = useAppDispatch();
  const alarms = useAppSelector(selectAlarmList);

  useEffect(() => {
    let cancelled = false;
    getAlarms(1, 500)
      .then((response) => {
        if (!cancelled && response?.data?.length) {
          dispatch(updateAlarmsBatch(response.data));
        }
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, [dispatch]);

  return useMemo(() => {
    const byKey = {} as Record<PerfAlarmKey, PerfAlarmBinding>;
    const catalogByKey = new Map(
      (catalog?.alarms || []).map((item) => [String(item.key || "").toLowerCase(), item])
    );
    for (const key of PERF_ALARM_KEYS) {
      const entry = catalogByKey.get(key);
      const alarm = alarms.find((item) => alarmNameMatches(item.name, entry?.alarm, key));
      byKey[key] = {
        key,
        alarm,
        catalog: entry,
        lifecycle: lifecycleOf(alarm),
      };
    }
    return byKey;
  }, [alarms, catalog]);
}
