import { useEffect, useMemo, useSyncExternalStore } from "react";

export type FloatingBannerId = "db" | "socket";

/** Vertical gap between stacked floating banners (px). */
export const FLOATING_BANNER_STACK_GAP = 52;
export const FLOATING_BANNER_TOP = 12;

type Listener = () => void;

const active = new Set<FloatingBannerId>();
const listeners = new Set<Listener>();
const ORDER: FloatingBannerId[] = ["db", "socket"];

function emit(): void {
  for (const listener of listeners) listener();
}

function snapshot(): string {
  return ORDER.filter((id) => active.has(id)).join(",");
}

function subscribe(listener: Listener): () => void {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

/** Register/unregister a floating banner; returns 0-based stack index among active ones. */
export function useFloatingBannerSlot(id: FloatingBannerId, visible: boolean): number {
  useEffect(() => {
    if (!visible) {
      if (active.delete(id)) emit();
      return;
    }
    if (!active.has(id)) {
      active.add(id);
      emit();
    }
    return () => {
      if (active.delete(id)) emit();
    };
  }, [id, visible]);

  const key = useSyncExternalStore(subscribe, snapshot, () => "");
  return useMemo(() => {
    const ids = key ? key.split(",") : [];
    const idx = ids.indexOf(id);
    return idx >= 0 ? idx : 0;
  }, [key, id]);
}

export function floatingBannerDefaultY(stackIndex: number): number {
  return FLOATING_BANNER_TOP + stackIndex * FLOATING_BANNER_STACK_GAP;
}

export type BannerPos = { x: number; y: number };

export function readBannerPos(storageKey: string): BannerPos | null {
  try {
    const raw = sessionStorage.getItem(storageKey);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as BannerPos;
    if (typeof parsed?.x === "number" && typeof parsed?.y === "number") {
      return { x: parsed.x, y: parsed.y };
    }
  } catch {
    /* ignore */
  }
  return null;
}

export function writeBannerPos(
  storageKey: string,
  pos: BannerPos,
  userMoved = true
): void {
  try {
    sessionStorage.setItem(storageKey, JSON.stringify({ ...pos, userMoved }));
  } catch {
    /* ignore */
  }
}

export function wasBannerUserMoved(storageKey: string): boolean {
  try {
    const raw = sessionStorage.getItem(storageKey);
    if (!raw) return false;
    const parsed = JSON.parse(raw) as { userMoved?: boolean };
    return Boolean(parsed?.userMoved);
  } catch {
    return false;
  }
}

export function clampBannerToStage(
  el: HTMLElement | null,
  next: BannerPos
): BannerPos {
  const stage = el?.offsetParent as HTMLElement | null;
  if (!el || !stage) return next;
  const maxX = Math.max(0, stage.clientWidth - el.offsetWidth);
  const maxY = Math.max(0, stage.clientHeight - el.offsetHeight);
  return {
    x: Math.min(Math.max(0, next.x), maxX),
    y: Math.min(Math.max(0, next.y), maxY),
  };
}
