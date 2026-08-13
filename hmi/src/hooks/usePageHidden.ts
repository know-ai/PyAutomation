import { useEffect, useState } from "react";

export function isPageHidden(): boolean {
  return typeof document !== "undefined" && document.hidden;
}

export function usePageHidden(): boolean {
  const [hidden, setHidden] = useState(() => isPageHidden());

  useEffect(() => {
    const onChange = () => setHidden(document.hidden);
    document.addEventListener("visibilitychange", onChange);
    return () => document.removeEventListener("visibilitychange", onChange);
  }, []);

  return hidden;
}
