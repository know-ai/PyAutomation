import { useEffect, useRef, useState, type RefObject } from "react";

const DEBOUNCE_MS = 200;
const MIN_DELTA_PX = 5;

export type PlotSize = { width: number; height: number };

/**
 * Observe the plot container. Dimensions come from the card, never from Plotly,
 * so autosize cannot feed back into the grid item.
 */
export function usePlotlyResize(
  containerRef: RefObject<HTMLElement | null>,
  interacting: boolean
): PlotSize {
  const [size, setSize] = useState<PlotSize>({ width: 0, height: 0 });
  const lastRef = useRef<PlotSize>({ width: 0, height: 0 });
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const interactingRef = useRef(interacting);
  interactingRef.current = interacting;

  useEffect(() => {
    const node = containerRef.current;
    if (!node || typeof ResizeObserver === "undefined") return;

    const apply = (width: number, height: number) => {
      if (interactingRef.current) return;
      const prev = lastRef.current;
      if (
        Math.abs(width - prev.width) < MIN_DELTA_PX &&
        Math.abs(height - prev.height) < MIN_DELTA_PX
      ) {
        return;
      }
      lastRef.current = { width, height };
      setSize({ width, height });
    };

    const observer = new ResizeObserver((entries) => {
      if (interactingRef.current) return;
      const entry = entries[0];
      if (!entry) return;
      const { width, height } = entry.contentRect;
      if (width < 1 || height < 1) return;
      if (timerRef.current) window.clearTimeout(timerRef.current);
      timerRef.current = window.setTimeout(() => apply(Math.round(width), Math.round(height)), DEBOUNCE_MS);
    });
    observer.observe(node);
    apply(Math.round(node.clientWidth), Math.round(node.clientHeight));
    return () => {
      observer.disconnect();
      if (timerRef.current) window.clearTimeout(timerRef.current);
    };
  }, [containerRef]);

  useEffect(() => {
    if (interacting) return;
    const node = containerRef.current;
    if (!node) return;
    const width = Math.round(node.clientWidth);
    const height = Math.round(node.clientHeight);
    const prev = lastRef.current;
    if (Math.abs(width - prev.width) < MIN_DELTA_PX && Math.abs(height - prev.height) < MIN_DELTA_PX) {
      return;
    }
    lastRef.current = { width, height };
    setSize({ width, height });
  }, [containerRef, interacting]);

  return size;
}
