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

// Buffer interval: 1 second (1000ms)
const BUFFER_INTERVAL_MS = 1000;

export function useSocket() {
  const dispatch = useAppDispatch();
  const isAuthenticated = useAppSelector((state) => state.auth.status === "authenticated");
  const pendingTagUpdatesRef = useRef<Map<string, Tag>>(new Map());
  const pendingAlarmUpdatesRef = useRef<Map<string, Alarm>>(new Map());
  const pendingMachineUpdatesRef = useRef<Map<string, Machine>>(new Map());
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    if (!isAuthenticated) {
      // Disconnect if user is not authenticated
      socketService.disconnect();
      // Clear interval
      if (intervalRef.current) {
        clearInterval(intervalRef.current);
        intervalRef.current = null;
      }
      pendingTagUpdatesRef.current.clear();
      pendingAlarmUpdatesRef.current.clear();
      pendingMachineUpdatesRef.current.clear();
      return;
    }

    // Connect to Socket.IO
    socketService.connect();

    // Function to flush pending updates from buffers
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

      // Use batch to group all updates together in a single render
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

    // Start interval to flush buffer every second
    intervalRef.current = setInterval(() => {
      flushUpdates();
    }, BUFFER_INTERVAL_MS);

    // Subscribe to tag updates - they go into the buffer
    const cleanupTags = socketService.onTagUpdate((tag) => {
      // Add to buffer (will overwrite if same tag name already exists)
      if (tag.name) {
        pendingTagUpdatesRef.current.set(tag.name, tag);
      }
    });

    // Subscribe to alarm updates - they go into the buffer
    const cleanupAlarms = socketService.onAlarmUpdate((alarm) => {
      // Add to buffer (will overwrite if same alarm identifier/id/name already exists)
      const key = alarm.identifier || alarm.id || alarm.name;
      if (key) {
        pendingAlarmUpdatesRef.current.set(String(key), alarm);
      }
    });

    // Subscribe to machine updates - they go into the buffer
    const cleanupMachines = socketService.onMachineUpdate((machine) => {
      // Add to buffer (will overwrite if same machine name already exists)
      if (machine.name) {
        pendingMachineUpdatesRef.current.set(machine.name, machine);
      }
    });

    // Cleanup on unmount or when authentication changes
    return () => {
      cleanupTags();
      cleanupAlarms();
      cleanupMachines();
      if (intervalRef.current) {
        clearInterval(intervalRef.current);
        intervalRef.current = null;
      }
      // Flush any remaining updates before cleanup
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

