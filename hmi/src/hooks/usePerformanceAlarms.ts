import { useEffect, useMemo, useState } from "react";
import { getAlarms, type Alarm } from "../services/alarms";
import {
  alarmNameMatches,
  lifecycleOf,
  type PerfAlarmLifecycle,
} from "../services/performanceAlarms";
import type { PerfAlarmCatalogEntry, PerfAlarmKey, PerfAlarmsCatalog } from "../services/performance";
import { PERF_ALARM_KEYS } from "../services/performance";
import { useAppSelector } from "./useAppSelector";

export type PerfAlarmBinding = {
  key: PerfAlarmKey;
  alarm?: Alarm;
  catalog?: PerfAlarmCatalogEntry;
  lifecycle: PerfAlarmLifecycle;
};

export function usePerformanceAlarms(catalog?: PerfAlarmsCatalog | null): Record<PerfAlarmKey, PerfAlarmBinding> {
  const [pageAlarms, setPageAlarms] = useState<Alarm[]>([]);
  const top3 = useAppSelector((state) => state.alarms.top3Active);

  useEffect(() => {
    let cancelled = false;
    getAlarms(1, 50, { q: "ALM.PERF" })
      .then((response) => {
        if (!cancelled && response?.data?.length) {
          setPageAlarms(response.data.slice(0, 50));
        }
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, []);

  const alarms = useMemo(() => {
    const byName = new Map<string, Alarm>();
    for (const alarm of pageAlarms) {
      if (alarm.name) byName.set(alarm.name, alarm);
    }
    for (const alarm of top3) {
      if (alarm.name) byName.set(alarm.name, alarm);
    }
    return Array.from(byName.values());
  }, [pageAlarms, top3]);

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
