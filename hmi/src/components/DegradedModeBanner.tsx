import { useCallback, useEffect, useRef, useState } from "react";
import { useTranslation } from "../hooks/useTranslation";
import { useDatabaseConnected } from "../hooks/useDatabaseStatus";

const POSITION_KEY = "pya.degradedBanner.pos";

type BannerPos = { x: number; y: number };

function readStoredPos(): BannerPos | null {
  try {
    const raw = sessionStorage.getItem(POSITION_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as BannerPos;
    if (typeof parsed?.x === "number" && typeof parsed?.y === "number") {
      return parsed;
    }
  } catch {
    /* ignore */
  }
  return null;
}

function writeStoredPos(pos: BannerPos): void {
  try {
    sessionStorage.setItem(POSITION_KEY, JSON.stringify(pos));
  } catch {
    /* ignore */
  }
}

/**
 * Floating degraded-mode notice inside the view stage.
 * Overlay (no layout shift). Draggable. Not dismissible — hides only when DB is back.
 */
export function DegradedModeBanner() {
  const { t } = useTranslation();
  const { connected } = useDatabaseConnected();
  const bannerRef = useRef<HTMLDivElement>(null);
  const dragRef = useRef<{
    startX: number;
    startY: number;
    originX: number;
    originY: number;
  } | null>(null);
  const [pos, setPos] = useState<BannerPos | null>(() => readStoredPos());
  const [dragging, setDragging] = useState(false);

  const clampToStage = useCallback((next: BannerPos): BannerPos => {
    const el = bannerRef.current;
    const stage = el?.offsetParent as HTMLElement | null;
    if (!el || !stage) return next;
    const maxX = Math.max(0, stage.clientWidth - el.offsetWidth);
    const maxY = Math.max(0, stage.clientHeight - el.offsetHeight);
    return {
      x: Math.min(Math.max(0, next.x), maxX),
      y: Math.min(Math.max(0, next.y), maxY),
    };
  }, []);

  useEffect(() => {
    if (connected !== false || pos !== null) return;
    const el = bannerRef.current;
    const stage = el?.offsetParent as HTMLElement | null;
    if (!el || !stage) return;
    const x = Math.max(0, Math.round((stage.clientWidth - el.offsetWidth) / 2));
    const y = 12;
    const initial = clampToStage({ x, y });
    setPos(initial);
    writeStoredPos(initial);
  }, [connected, pos, clampToStage]);

  useEffect(() => {
    if (!dragging) return;

    const onMove = (event: PointerEvent) => {
      const drag = dragRef.current;
      if (!drag) return;
      const next = clampToStage({
        x: drag.originX + (event.clientX - drag.startX),
        y: drag.originY + (event.clientY - drag.startY),
      });
      setPos(next);
    };

    const onUp = () => {
      dragRef.current = null;
      setDragging(false);
      setPos((current) => {
        if (current) writeStoredPos(current);
        return current;
      });
    };

    window.addEventListener("pointermove", onMove);
    window.addEventListener("pointerup", onUp);
    window.addEventListener("pointercancel", onUp);
    return () => {
      window.removeEventListener("pointermove", onMove);
      window.removeEventListener("pointerup", onUp);
      window.removeEventListener("pointercancel", onUp);
    };
  }, [dragging, clampToStage]);

  if (connected !== false) {
    return null;
  }

  const style =
    pos !== null
      ? { left: pos.x, top: pos.y, transform: "none" as const }
      : undefined;

  return (
    <div
      ref={bannerRef}
      className={`degraded-mode-banner${dragging ? " is-dragging" : ""}`}
      style={style}
      role="status"
      aria-live="polite"
      aria-label={t("dbHealth.degradedModeBanner")}
    >
      <button
        type="button"
        className="degraded-mode-banner__handle"
        aria-label={t("dbHealth.degradedModeMove")}
        title={t("dbHealth.degradedModeMove")}
        onPointerDown={(event) => {
          if (event.button !== 0) return;
          event.preventDefault();
          const current = pos ?? { x: bannerRef.current?.offsetLeft ?? 0, y: bannerRef.current?.offsetTop ?? 0 };
          dragRef.current = {
            startX: event.clientX,
            startY: event.clientY,
            originX: current.x,
            originY: current.y,
          };
          setDragging(true);
          (event.currentTarget as HTMLElement).setPointerCapture?.(event.pointerId);
        }}
      >
        <i className="bi bi-grip-vertical" aria-hidden="true" />
      </button>
      <i className="bi bi-exclamation-triangle-fill degraded-mode-banner__icon" aria-hidden="true" />
      <span className="degraded-mode-banner__text">{t("dbHealth.degradedModeBanner")}</span>
    </div>
  );
}
