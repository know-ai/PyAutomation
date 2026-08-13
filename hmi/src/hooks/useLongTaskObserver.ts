import { useEffect } from "react";

export function useLongTaskObserver(thresholdMs: number = 50, label: string = "hmi"): void {
  useEffect(() => {
    if (typeof PerformanceObserver === "undefined") {
      return;
    }
    const supported = PerformanceObserver.supportedEntryTypes?.includes("longtask");
    if (!supported) {
      return;
    }
    const observer = new PerformanceObserver((list) => {
      for (const entry of list.getEntries()) {
        if (entry.duration > thresholdMs) {
          console.warn(`[HMI] longtask ${entry.duration.toFixed(0)} ms (${label})`);
        }
      }
    });
    try {
      observer.observe({ type: "longtask", buffered: true });
    } catch {
      return;
    }
    return () => observer.disconnect();
  }, [thresholdMs, label]);
}
