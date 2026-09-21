import { useCallback, useEffect, useRef, useState } from "react";
import type { Tag } from "../services/tags";
import { socketService } from "../services/socket";
import { useTranslation } from "./useTranslation";
import { showToast } from "../utils/toast";
import {
  loadStationTagCatalog,
  peekStationTagCatalog,
  subscribeStationTagCatalog,
  subscribeStationTagCatalogInvalidation,
} from "../services/workspaceStore";

const MACHINE_REFRESH_DEBOUNCE_MS = 1500;

type UseStationTagCatalogOptions = {
  /** Refetch when the trends panel enters layout edit mode. */
  refreshInEditMode?: boolean;
  isEditMode?: boolean;
};

/**
 * Tag catalog for Real-Time Trends pickers. Uses a module cache for instant paint,
 * then refreshes from the API and on machine lifecycle / reconnect events.
 */
export function useStationTagCatalog(options: UseStationTagCatalogOptions = {}) {
  const { t } = useTranslation();
  const { refreshInEditMode = false, isEditMode = false } = options;
  const [tags, setTags] = useState<Tag[]>(() => peekStationTagCatalog() ?? []);
  const [loading, setLoading] = useState(() => peekStationTagCatalog() === null);
  const refreshRequestRef = useRef(0);

  const refresh = useCallback(async (force = true) => {
    const requestId = ++refreshRequestRef.current;
    const hasCachedTags = (peekStationTagCatalog()?.length ?? 0) > 0;
    if (!hasCachedTags) {
      setLoading(true);
    }
    try {
      const next = await loadStationTagCatalog(force);
      if (requestId === refreshRequestRef.current) {
        setTags(next);
      }
      return next;
    } catch {
      if (requestId === refreshRequestRef.current) {
        showToast(t("stripChart.errorLoadingTags"), "error");
      }
      return peekStationTagCatalog() ?? [];
    } finally {
      if (requestId === refreshRequestRef.current) {
        setLoading(false);
      }
    }
  }, [t]);

  useEffect(() => subscribeStationTagCatalog(setTags), []);

  useEffect(
    () =>
      subscribeStationTagCatalogInvalidation(() => {
        void refresh(true);
      }),
    [refresh]
  );

  useEffect(() => {
    void refresh(true);
  }, [refresh]);

  useEffect(() => {
    if (!refreshInEditMode || !isEditMode) return;
    void refresh(true);
  }, [refreshInEditMode, isEditMode, refresh]);

  useEffect(() => {
    let timer: ReturnType<typeof setTimeout> | null = null;
    const scheduleRefresh = () => {
      if (timer) clearTimeout(timer);
      timer = setTimeout(() => {
        void refresh(true);
      }, MACHINE_REFRESH_DEBOUNCE_MS);
    };
    const cleanupMachine = socketService.onMachineUpdate(scheduleRefresh);
    const cleanupCatalog = socketService.onTagCatalogUpdate(() => {
      void refresh(true);
    });
    const cleanupConnection = socketService.onConnectionChange(({ connected, reconnect }) => {
      if (connected && reconnect) {
        scheduleRefresh();
      }
    });
    return () => {
      cleanupMachine();
      cleanupCatalog();
      cleanupConnection();
      if (timer) clearTimeout(timer);
    };
  }, [refresh]);

  return { tags, loading, refresh };
}
