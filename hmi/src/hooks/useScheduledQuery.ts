import { useCallback, useEffect, useRef } from "react";
import axios from "axios";

/** Selects simples, paginación y cierre de panel. */
export const FILTER_INSTANT_MS = 0;
/** Multi-select y texto: espera a que el operador termine de componer. */
export const FILTER_COMPOSE_MS = 400;
/** datetime-local genera muchos eventos seguidos. */
export const FILTER_DATE_MS = 700;
/** Consultas pesadas (registrador). */
export const FILTER_HEAVY_MS = 550;
/** Ráfagas live (bitácora). */
export const FILTER_LIVE_MS = 250;

export type ScheduledQueryContext = {
  signal: AbortSignal;
  generation: number;
};

export type ScheduledQueryRunner = (ctx: ScheduledQueryContext) => void | Promise<void>;

export function isRequestCanceled(error: unknown): boolean {
  if (!error || typeof error !== "object") return false;
  const err = error as { code?: string; name?: string };
  return axios.isCancel(error) || err.code === "ERR_CANCELED" || err.name === "CanceledError";
}

/**
 * Agrupa cambios de filtro en una sola consulta y cancela la petición anterior.
 * `schedule(0)` se aplaza al siguiente macrotask para leer el state ya committed.
 */
export function useScheduledQuery() {
  const timerRef = useRef<number | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const generationRef = useRef(0);
  const runnerRef = useRef<ScheduledQueryRunner | null>(null);

  const clearTimer = useCallback(() => {
    if (timerRef.current != null) {
      window.clearTimeout(timerRef.current);
      timerRef.current = null;
    }
  }, []);

  const start = useCallback(() => {
    timerRef.current = null;
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;
    const generation = generationRef.current + 1;
    generationRef.current = generation;
    void runnerRef.current?.({ signal: controller.signal, generation });
  }, []);

  const schedule = useCallback(
    (delayMs: number) => {
      clearTimer();
      timerRef.current = window.setTimeout(start, Math.max(0, delayMs));
    },
    [clearTimer, start]
  );

  const flushPending = useCallback(() => {
    if (timerRef.current == null) return;
    clearTimer();
    timerRef.current = window.setTimeout(start, 0);
  }, [clearTimer, start]);

  const setRunner = useCallback((runner: ScheduledQueryRunner) => {
    runnerRef.current = runner;
  }, []);

  const isCurrent = useCallback((generation: number, signal: AbortSignal) => {
    return generation === generationRef.current && !signal.aborted;
  }, []);

  useEffect(() => {
    return () => {
      clearTimer();
      abortRef.current?.abort();
      generationRef.current += 1;
    };
  }, [clearTimer]);

  return { schedule, flushPending, setRunner, isCurrent };
}
