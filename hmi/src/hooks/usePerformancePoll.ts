import { useEffect, useRef } from "react";
import { FOCUS_POLL_MS, HIDDEN_POLL_MS, pollIntervalMs } from "../services/performance";

export function usePerformancePoll(tick: () => void, enabled: boolean): void {
  const tickRef = useRef(tick);
  tickRef.current = tick;

  useEffect(() => {
    if (!enabled) return undefined;

    let timer: ReturnType<typeof setInterval> | undefined;

    const arm = () => {
      if (timer) clearInterval(timer);
      const interval = pollIntervalMs(Boolean(document.hidden));
      timer = setInterval(() => {
        tickRef.current();
      }, interval);
    };

    const onVisibility = () => {
      arm();
      if (!document.hidden) tickRef.current();
    };

    tickRef.current();
    arm();
    document.addEventListener("visibilitychange", onVisibility);
    return () => {
      if (timer) clearInterval(timer);
      document.removeEventListener("visibilitychange", onVisibility);
    };
  }, [enabled]);
}

export { FOCUS_POLL_MS, HIDDEN_POLL_MS };
