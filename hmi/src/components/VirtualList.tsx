import { useEffect, useRef, useState, type ReactNode, type UIEvent } from "react";

export const VIRTUALIZE_AFTER = 200;

type VirtualListProps<T> = {
  items: T[];
  itemHeight?: number;
  height: number;
  overscan?: number;
  className?: string;
  getKey: (item: T, index: number) => string;
  renderItem: (item: T, index: number) => ReactNode;
  highlightedIndex?: number;
  /**
   * When this token changes, scroll so ``highlightedIndex`` is visible.
   * Do not scroll on every highlight change (e.g. mouse hover while scrolling).
   */
  scrollToIndexToken?: number;
  onScroll?: () => void;
};

export function shouldVirtualize(count: number): boolean {
  return count > VIRTUALIZE_AFTER;
}

export function VirtualList<T>({
  items,
  itemHeight = 44,
  height,
  overscan = 6,
  className,
  getKey,
  renderItem,
  highlightedIndex,
  scrollToIndexToken,
  onScroll: onScrollProp,
}: VirtualListProps<T>) {
  const scrollerRef = useRef<HTMLDivElement>(null);
  const [scrollTop, setScrollTop] = useState(0);

  useEffect(() => {
    if (scrollToIndexToken == null) {
      return;
    }
    if (highlightedIndex == null || highlightedIndex < 0) {
      return;
    }
    const el = scrollerRef.current;
    if (!el) {
      return;
    }
    const top = highlightedIndex * itemHeight;
    const bottom = top + itemHeight;
    if (top < el.scrollTop) {
      el.scrollTop = top;
    } else if (bottom > el.scrollTop + el.clientHeight) {
      el.scrollTop = bottom - el.clientHeight;
    }
  }, [scrollToIndexToken, highlightedIndex, itemHeight]);

  const handleScroll = (event: UIEvent<HTMLDivElement>) => {
    setScrollTop(event.currentTarget.scrollTop);
    onScrollProp?.();
  };

  if (!shouldVirtualize(items.length)) {
    return (
      <div
        ref={scrollerRef}
        className={className}
        style={{ maxHeight: height, overflowY: "auto" }}
        onScroll={() => onScrollProp?.()}
      >
        {items.map((item, index) => (
          <div key={getKey(item, index)}>{renderItem(item, index)}</div>
        ))}
      </div>
    );
  }

  const start = Math.max(0, Math.floor(scrollTop / itemHeight) - overscan);
  const visible = Math.ceil(height / itemHeight) + overscan * 2;
  const end = Math.min(items.length, start + visible);
  const padTop = start * itemHeight;
  const padBottom = Math.max(0, (items.length - end) * itemHeight);

  return (
    <div
      ref={scrollerRef}
      className={className}
      style={{ height, overflowY: "auto" }}
      onScroll={handleScroll}
    >
      <div style={{ height: padTop }} aria-hidden="true" />
      {items.slice(start, end).map((item, offset) => {
        const index = start + offset;
        return <div key={getKey(item, index)}>{renderItem(item, index)}</div>;
      })}
      <div style={{ height: padBottom }} aria-hidden="true" />
    </div>
  );
}
