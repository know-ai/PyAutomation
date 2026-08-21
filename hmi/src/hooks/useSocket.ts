import { useEffect, useRef } from "react";
import { useAppDispatch } from "./useAppDispatch";
import { useDisplayTimezone } from "./useDisplayTimezone";
import { socketService, type SocketConnectionSnapshot } from "../services/socket";
import {
  appendTagHistoryPoints,
  HISTORY_POINTS_PER_FLUSH,
  isTagHistoryTracked,
  updateTagValuesBatch,
} from "../store/slices/tagsSlice";
import { loadAllAlarms, updateAlarmsBatch } from "../store/slices/alarmsSlice";
import { loadAllMachines, updateMachinesBatch } from "../store/slices/machinesSlice";
import { useAppSelector } from "./useAppSelector";
import { store } from "../store/store";
import { batch } from "react-redux";
import type { Tag } from "../services/tags";
import { getAlarms, type Alarm } from "../services/alarms";
import type { Machine } from "../services/machines";
import { isPageHidden } from "./usePageHidden";
import { isSystemUser } from "../utils/systemUser";
import { scheduleTagHistoryBackfill, resetTagHistoryBackfillThrottle } from "../utils/tagHistoryBackfill";

const BUFFER_INTERVAL_MS = 1000;
const HIDDEN_FLUSH_EVERY = 5;

const enqueueHistorySample = (queues: Map<string, Tag[]>, tag: Tag): void => {
  if (!tag.name) return;
  const queue = queues.get(tag.name) || [];
  queue.push(tag);
  while (queue.length > HISTORY_POINTS_PER_FLUSH) {
    queue.shift();
  }
  queues.set(tag.name, queue);
};

const isHistoryTrackedTag = (name: string): boolean => {
  const tags = store.getState().tags;
  return isTagHistoryTracked(tags.historySubscribers, tags.tagHistory, name);
};

export function useSocket() {
  const dispatch = useAppDispatch();
  const { timeZone } = useDisplayTimezone();
  const isAuthenticated = useAppSelector((state) => state.auth.status === "authenticated");
  const isSystemSession = useAppSelector((state) => isSystemUser(state.auth.user));
  const pendingTagUpdatesRef = useRef<Map<string, Tag>>(new Map());
  const pendingHistoryUpdatesRef = useRef<Map<string, Tag[]>>(new Map());
  const pendingAlarmUpdatesRef = useRef<Map<string, Alarm>>(new Map());
  const pendingMachineUpdatesRef = useRef<Map<string, Machine>>(new Map());
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const hiddenTicksRef = useRef(0);

  useEffect(() => {
    if (!isAuthenticated || isSystemSession) {
      socketService.disconnect();
      if (intervalRef.current) {
        clearInterval(intervalRef.current);
        intervalRef.current = null;
      }
      pendingTagUpdatesRef.current.clear();
      pendingHistoryUpdatesRef.current.clear();
      pendingAlarmUpdatesRef.current.clear();
      pendingMachineUpdatesRef.current.clear();
      return;
    }

    const hydrateFromSnapshot = (payload: SocketConnectionSnapshot) => {
      const tags = Array.isArray(payload.tags) ? payload.tags : [];
      const machines = Array.isArray(payload.machines) ? payload.machines : [];

      batch(() => {
        if (Array.isArray(payload.alarms)) {
          // Full catalog snapshot (may be empty) replaces stale session state.
          dispatch(loadAllAlarms(payload.alarms));
        } else if (
          Array.isArray(payload.last_active_alarms) &&
          payload.last_active_alarms.length > 0
        ) {
          dispatch(updateAlarmsBatch(payload.last_active_alarms));
        }
        if (tags.length > 0) {
          dispatch(updateTagValuesBatch(tags));
        }
        if (machines.length > 0) {
          dispatch(loadAllMachines(machines));
        }
      });
    };

    const hydrateAlarmsFromRest = async () => {
      try {
        const response = await getAlarms(1, 10000);
        if (Array.isArray(response?.data)) {
          dispatch(loadAllAlarms(response.data));
        }
      } catch {
        // Offline / historian-less nodes still get on_connection when available.
      }
    };

    // Register snapshot listener before connect so we do not miss the first emit.
    const cleanupSnapshot = socketService.onConnectionSnapshot(hydrateFromSnapshot);
    socketService.connect();

    const flushHistory = () => {
      if (pendingHistoryUpdatesRef.current.size === 0) return;
      const payload = Array.from(pendingHistoryUpdatesRef.current.entries()).map(
        ([name, points]) => ({ name, points })
      );
      pendingHistoryUpdatesRef.current.clear();
      dispatch(appendTagHistoryPoints(payload));
    };

    const flushCurrentValues = () => {
      const hasTagUpdates = pendingTagUpdatesRef.current.size > 0;
      const hasAlarmUpdates = pendingAlarmUpdatesRef.current.size > 0;
      const hasMachineUpdates = pendingMachineUpdatesRef.current.size > 0;

      if (!hasTagUpdates && !hasAlarmUpdates && !hasMachineUpdates) {
        return;
      }

      const tagUpdates = hasTagUpdates ? Array.from(pendingTagUpdatesRef.current.values()) : [];
      const alarmUpdates = hasAlarmUpdates ? Array.from(pendingAlarmUpdatesRef.current.values()) : [];
      const machineUpdates = hasMachineUpdates
        ? Array.from(pendingMachineUpdatesRef.current.values())
        : [];

      pendingTagUpdatesRef.current.clear();
      pendingAlarmUpdatesRef.current.clear();
      pendingMachineUpdatesRef.current.clear();

      batch(() => {
        if (hasTagUpdates) {
          dispatch(updateTagValuesBatch(tagUpdates));
        }
        if (hasAlarmUpdates) {
          dispatch(updateAlarmsBatch(alarmUpdates));
        }
        if (hasMachineUpdates) {
          dispatch(updateMachinesBatch(machineUpdates));
        }
      });
    };

    const flushAll = () => {
      flushHistory();
      flushCurrentValues();
    };

    intervalRef.current = setInterval(() => {
      flushHistory();
      if (isPageHidden()) {
        hiddenTicksRef.current += 1;
        if (hiddenTicksRef.current % HIDDEN_FLUSH_EVERY !== 0) {
          return;
        }
      } else {
        hiddenTicksRef.current = 0;
      }
      flushCurrentValues();
    }, BUFFER_INTERVAL_MS);

    const onVisibility = () => {
      if (!isPageHidden()) {
        hiddenTicksRef.current = 0;
        flushAll();
      }
    };
    document.addEventListener("visibilitychange", onVisibility);

    const cleanupTags = socketService.onTagUpdate((tag) => {
      if (!tag.name) return;
      pendingTagUpdatesRef.current.set(tag.name, tag);
      if (isHistoryTrackedTag(tag.name)) {
        enqueueHistorySample(pendingHistoryUpdatesRef.current, tag);
      }
    });

    const cleanupAlarms = socketService.onAlarmUpdate((alarm) => {
      const key = alarm.identifier || alarm.id || alarm.name;
      if (key) {
        pendingAlarmUpdatesRef.current.set(String(key), alarm);
      }
    });

    const cleanupMachines = socketService.onMachineUpdate((machine) => {
      if (machine.name) {
        pendingMachineUpdatesRef.current.set(machine.name, machine);
      }
    });

    const cleanupConnection = socketService.onConnectionChange(({ connected, reconnect }) => {
      if (!connected) {
        resetTagHistoryBackfillThrottle();
        return;
      }
      // First connect + reconnect: ensure footer/active alarms reflect runtime state
      // even if `on.alarm` deltas were emitted before this session subscribed.
      void hydrateAlarmsFromRest();
      if (!reconnect) return;
      const { historySubscribers } = store.getState().tags;
      const names = Object.keys(historySubscribers).filter((n) => historySubscribers[n] > 0);
      if (names.length === 0) return;
      scheduleTagHistoryBackfill(names, timeZone, dispatch, true);
    });

    return () => {
      document.removeEventListener("visibilitychange", onVisibility);
      cleanupSnapshot();
      cleanupTags();
      cleanupAlarms();
      cleanupMachines();
      cleanupConnection();
      if (intervalRef.current) {
        clearInterval(intervalRef.current);
        intervalRef.current = null;
      }
      flushAll();
      pendingTagUpdatesRef.current.clear();
      pendingHistoryUpdatesRef.current.clear();
      pendingAlarmUpdatesRef.current.clear();
      pendingMachineUpdatesRef.current.clear();
    };
  }, [dispatch, isAuthenticated, isSystemSession, timeZone]);

  return {
    isConnected: socketService.getIsConnected(),
  };
}
