import { useEffect, useState } from "react";

/**
 * Returns ``value`` after ``delay`` ms of inactivity.
 * Used for free-text table filters (alarms summary, events).
 */
export function useDebounce<T>(value: T, delay: number = 300): T {
  const [debouncedValue, setDebouncedValue] = useState(value);

  useEffect(() => {
    const handler = window.setTimeout(() => setDebouncedValue(value), delay);
    return () => window.clearTimeout(handler);
  }, [value, delay]);

  return debouncedValue;
}
