import { useEffect } from "react";
import { showToast } from "../utils/toast";
import { createLog } from "../services/logs";

const DEFAULT_THRESHOLD_MB = 512;
const POLL_MS = 60_000;

type MemoryInfo = {
  usedJSHeapSize: number;
};

export function useMemoryWatchdog(thresholdMb: number = DEFAULT_THRESHOLD_MB): void {
  useEffect(() => {
    let warned = false;
    const id = window.setInterval(() => {
      const mem = (performance as unknown as { memory?: MemoryInfo }).memory;
      if (!mem) {
        return;
      }
      const usedMb = mem.usedJSHeapSize / (1024 * 1024);
      if (usedMb > thresholdMb) {
        const message = `[HMI] heap ${usedMb.toFixed(1)} MB > ${thresholdMb} MB`;
        console.warn(message);
        if (!warned) {
          warned = true;
          showToast(message, "warning");
          void createLog({
            message,
            description: "memory-watchdog",
          }).catch(() => undefined);
        }
      } else {
        warned = false;
      }
    }, POLL_MS);
    return () => window.clearInterval(id);
  }, [thresholdMb]);
}
