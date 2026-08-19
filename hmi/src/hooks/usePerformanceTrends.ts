import { useEffect, useSyncExternalStore } from "react";
import {
  getPerformanceTrendState,
  startPerformanceTrendSampler,
  stopPerformanceTrendSampler,
  subscribePerformanceTrends,
} from "../services/performanceTrends";

export function usePerformanceTrendSampler(enabled: boolean): void {
  useEffect(() => {
    if (!enabled) {
      stopPerformanceTrendSampler(true);
      return undefined;
    }
    startPerformanceTrendSampler();
    return () => stopPerformanceTrendSampler(false);
  }, [enabled]);
}

export function usePerformanceTrends() {
  return useSyncExternalStore(subscribePerformanceTrends, getPerformanceTrendState, getPerformanceTrendState);
}
