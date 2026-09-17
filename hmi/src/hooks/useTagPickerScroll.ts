import { useLayoutEffect, useRef, type RefObject, type UIEvent } from "react";

/**
 * Preserve listbox scrollTop across parent re-renders (socket/Redux).
 * onScroll only mutates a ref — it MUST NOT setState.
 *
 * Runs on every commit (no dep array) so I-1 stream re-renders keep scroll.
 * A mount-only effect would regress CA-HOVER-8 / SPEC-HMI-RT-TRENDS-FIX I-1.
 */
export function useTagPickerScroll(): {
  listRef: RefObject<HTMLDivElement>;
  handleScroll: (event: UIEvent<HTMLDivElement>) => void;
  restoreScroll: () => void;
} {
  const listRef = useRef<HTMLDivElement>(null) as RefObject<HTMLDivElement>;
  const scrollTopRef = useRef(0);

  const restoreScroll = () => {
    const el = listRef.current;
    if (!el) return;
    const max = Math.max(0, el.scrollHeight - el.clientHeight);
    const next = Math.min(Math.max(0, scrollTopRef.current), max);
    if (Math.abs(el.scrollTop - next) > 1) {
      el.scrollTop = next;
    }
    scrollTopRef.current = el.scrollTop;
  };

  const handleScroll = (event: UIEvent<HTMLDivElement>) => {
    scrollTopRef.current = event.currentTarget.scrollTop;
  };

  useLayoutEffect(() => {
    restoreScroll();
  });

  return { listRef, handleScroll, restoreScroll };
}
