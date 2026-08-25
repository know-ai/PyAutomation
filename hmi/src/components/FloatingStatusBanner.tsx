import { useCallback, useEffect, useRef, useState, type PointerEvent as ReactPointerEvent } from "react";
import {
  clampBannerToStage,
  floatingBannerDefaultY,
  readBannerPos,
  useFloatingBannerSlot,
  wasBannerUserMoved,
  writeBannerPos,
  type BannerPos,
  type FloatingBannerId,
} from "../hooks/useFloatingBannerStack";

type FloatingStatusBannerProps = {
  id: FloatingBannerId;
  storageKey: string;
  visible: boolean;
  text: string;
  ariaLabel: string;
  moveLabel: string;
  /** Visual tone — warning (default) or danger. */
  tone?: "warning" | "danger";
  iconClassName?: string;
};

/**
 * Floating stage notice: no layout shift, draggable, stacks with sibling banners.
 */
export function FloatingStatusBanner({
  id,
  storageKey,
  visible,
  text,
  ariaLabel,
  moveLabel,
  tone = "warning",
  iconClassName = "bi bi-exclamation-triangle-fill",
}: FloatingStatusBannerProps) {
  const stackIndex = useFloatingBannerSlot(id, visible);
  const bannerRef = useRef<HTMLDivElement>(null);
  const dragRef = useRef<{
    startX: number;
    startY: number;
    originX: number;
    originY: number;
  } | null>(null);
  const [pos, setPos] = useState<BannerPos | null>(() =>
    visible ? readBannerPos(storageKey) : null
  );
  const [dragging, setDragging] = useState(false);
  const [userMoved, setUserMoved] = useState(() => wasBannerUserMoved(storageKey));

  useEffect(() => {
    if (!visible) return;
    if (userMoved) return;
    const el = bannerRef.current;
    const stage = el?.offsetParent as HTMLElement | null;
    if (!el || !stage) return;
    const x = Math.max(0, Math.round((stage.clientWidth - el.offsetWidth) / 2));
    const y = floatingBannerDefaultY(stackIndex);
    const initial = clampBannerToStage(el, { x, y });
    setPos(initial);
    writeBannerPos(storageKey, initial, false);
  }, [visible, stackIndex, userMoved, storageKey]);

  useEffect(() => {
    if (!dragging) return;

    const onMove = (event: PointerEvent) => {
      const drag = dragRef.current;
      if (!drag) return;
      const next = clampBannerToStage(bannerRef.current, {
        x: drag.originX + (event.clientX - drag.startX),
        y: drag.originY + (event.clientY - drag.startY),
      });
      setPos(next);
    };

    const onUp = () => {
      dragRef.current = null;
      setDragging(false);
      setUserMoved(true);
      setPos((current) => {
        if (current) writeBannerPos(storageKey, current, true);
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
  }, [dragging, storageKey]);

  const onHandlePointerDown = useCallback(
    (event: ReactPointerEvent) => {
      if (event.button !== 0) return;
      event.preventDefault();
      const el = bannerRef.current;
      const current =
        pos ??
        (el
          ? { x: el.offsetLeft, y: el.offsetTop }
          : { x: 0, y: floatingBannerDefaultY(stackIndex) });
      dragRef.current = {
        startX: event.clientX,
        startY: event.clientY,
        originX: current.x,
        originY: current.y,
      };
      setDragging(true);
      (event.currentTarget as HTMLElement).setPointerCapture?.(event.pointerId);
    },
    [pos, stackIndex]
  );

  if (!visible) return null;

  const style =
    pos !== null
      ? { left: pos.x, top: pos.y, transform: "none" as const }
      : { top: floatingBannerDefaultY(stackIndex) };

  return (
    <div
      ref={bannerRef}
      data-floating-banner={storageKey}
      className={`floating-status-banner floating-status-banner--${tone}${
        dragging ? " is-dragging" : ""
      }`}
      style={style}
      role="status"
      aria-live="polite"
      aria-label={ariaLabel}
    >
      <button
        type="button"
        className="floating-status-banner__handle"
        aria-label={moveLabel}
        title={moveLabel}
        onPointerDown={onHandlePointerDown}
      >
        <i className="bi bi-grip-vertical" aria-hidden="true" />
      </button>
      <i className={`${iconClassName} floating-status-banner__icon`} aria-hidden="true" />
      <span className="floating-status-banner__text">{text}</span>
    </div>
  );
}
