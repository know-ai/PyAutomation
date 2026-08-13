import { useEffect, useRef } from "react";
import { useAppDispatch } from "./useAppDispatch";
import { socketService } from "../services/socket";
import { updateTagValuesBatch } from "../store/slices/tagsSlice";
import { updateAlarmsBatch } from "../store/slices/alarmsSlice";
import { updateMachinesBatch } from "../store/slices/machinesSlice";
import { useAppSelector } from "./useAppSelector";
import { batch } from "react-redux";
import type { Tag } from "../services/tags";
import type { Alarm } from "../services/alarms";
import type { Machine } from "../services/machines";
import { isPageHidden } from "./usePageHidden";

const BUFFER_INTERVAL_MS = 1000;
const HIDDEN_FLUSH_EVERY = 5;

export function useSocket() {
  const dispatch = useAppDispatch();
  const isAuthenticated = useAppSelector((state) => state.auth.status === "authenticated");
  const pendingTagUpdatesRef = useRef<Map<string, Tag>>(new Map());
  const pendingAlarmUpdatesRef = useRef<Map<string, Alarm>>(new Map());
  const pendingMachineUpdatesRef = useRef<Map<string, Machine>>(new Map());
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const hiddenTicksRef = useRef(0);

  useEffect(() => {
    if (!isAuthenticated) {
      socketService.disconnect();
      if (intervalRef.current) {
        clearInterval(intervalRef.current);
        intervalRef.current = null;
      }
      pendingTagUpdatesRef.current.clear();
      pendingAlarmUpdatesRef.current.clear();
      pendingMachineUpdatesRef.current.clear();
      return;
    }

    socketService.connect();

    const flushUpdates = () => {
      const hasTagUpdates = pendingTagUpdatesRef.current.size > 0;
      const hasAlarmUpdates = pendingAlarmUpdatesRef.current.size > 0;
      const hasMachineUpdates = pendingMachineUpdatesRef.current.size > 0;

      if (!hasTagUpdates && !hasAlarmUpdates && !hasMachineUpdates) {
        return;
      }

      const tagUpdates = hasTagUpdates ? Array.from(pendingTagUpdatesRef.current.values()) : [];
      const alarmUpdates = hasAlarmUpdates ? Array.from(pendingAlarmUpdatesRef.current.values()) : [];
      const machineUpdates = hasMachineUpdates ? Array.from(pendingMachineUpdatesRef.current.values()) : [];

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

    intervalRef.current = setInterval(() => {
      if (isPageHidden()) {
        hiddenTicksRef.current += 1;
        if (hiddenTicksRef.current % HIDDEN_FLUSH_EVERY !== 0) {
          return;
        }
      } else {
        hiddenTicksRef.current = 0;
      }
      flushUpdates();
    }, BUFFER_INTERVAL_MS);

    const cleanupTags = socketService.onTagUpdate((tag) => {
      if (tag.name) {
        pendingTagUpdatesRef.current.set(tag.name, tag);
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

    return () => {
      cleanupTags();
      cleanupAlarms();
      cleanupMachines();
      if (intervalRef.current) {
        clearInterval(intervalRef.current);
        intervalRef.current = null;
      }
      flushUpdates();
      pendingTagUpdatesRef.current.clear();
      pendingAlarmUpdatesRef.current.clear();
      pendingMachineUpdatesRef.current.clear();
    };
  }, [dispatch, isAuthenticated]);

  return {
    isConnected: socketService.getIsConnected(),
  };
}
