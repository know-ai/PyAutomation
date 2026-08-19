import { useEffect, useMemo, useRef, useState } from "react";

export type ComboboxItem = {
  key: string;
  value: string;
  label: string;
  title?: string;
};

type Props = {
  id: string;
  items: ComboboxItem[];
  inputValue: string;
  onInputValueChange: (value: string) => void;
  onSelect: (item: ComboboxItem) => void;
  placeholder: string;
  disabled?: boolean;
  loading?: boolean;
  loadingText?: string;
  emptyText?: string;
  listHeight?: number;
  rowHeight?: number;
  className?: string;
};

export function VirtualizedCombobox({
  id,
  items,
  inputValue,
  onInputValueChange,
  onSelect,
  placeholder,
  disabled = false,
  loading = false,
  loadingText = "Loading...",
  emptyText = "No results",
  listHeight = 220,
  rowHeight = 38,
  className = "form-control",
}: Props) {
  const [isOpen, setIsOpen] = useState(false);
  const [highlightedIndex, setHighlightedIndex] = useState(-1);
  const [scrollTop, setScrollTop] = useState(0);
  const rootRef = useRef<HTMLDivElement | null>(null);
  const listRef = useRef<HTMLDivElement | null>(null);
  const overscan = 4;

  const visibleCount = Math.ceil(listHeight / rowHeight);
  const virtualStartIndex = Math.max(0, Math.floor(scrollTop / rowHeight) - overscan);
  const virtualEndIndex = Math.min(items.length, virtualStartIndex + visibleCount + overscan * 2);
  const virtualItems = items.slice(virtualStartIndex, virtualEndIndex);

  const closeDropdown = () => {
    setIsOpen(false);
    setHighlightedIndex(-1);
    setScrollTop(0);
  };

  const openDropdown = () => {
    if (disabled) return;
    setIsOpen(true);
    setHighlightedIndex(items.length ? 0 : -1);
  };

  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      const target = event.target as Node;
      if (rootRef.current && !rootRef.current.contains(target)) {
        closeDropdown();
      }
    };
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  useEffect(() => {
    if (disabled) closeDropdown();
  }, [disabled]);

  useEffect(() => {
    if (!isOpen) return;
    setHighlightedIndex(items.length ? 0 : -1);
  }, [items.length, isOpen]);

  useEffect(() => {
    if (!isOpen || highlightedIndex < 0 || !listRef.current) return;
    const listEl = listRef.current;
    const targetTop = highlightedIndex * rowHeight;
    const targetBottom = targetTop + rowHeight;
    const viewTop = listEl.scrollTop;
    const viewBottom = viewTop + listHeight;
    if (targetTop < viewTop) {
      listEl.scrollTop = targetTop;
    } else if (targetBottom > viewBottom) {
      listEl.scrollTop = targetBottom - listHeight;
    }
  }, [highlightedIndex, isOpen, rowHeight, listHeight]);

  const renderHighlighted = (text: string, query: string) => {
    const q = query.trim();
    if (!q) return text;
    const lowerText = text.toLowerCase();
    const lowerQuery = q.toLowerCase();
    const start = lowerText.indexOf(lowerQuery);
    if (start < 0) return text;
    const end = start + q.length;
    return (
      <>
        {text.slice(0, start)}
        <mark className="px-0">{text.slice(start, end)}</mark>
        {text.slice(end)}
      </>
    );
  };

  const listId = `${id}-list`;

  return (
    <div className="position-relative" ref={rootRef}>
      <input
        id={id}
        type="text"
        className={className}
        placeholder={placeholder}
        value={inputValue}
        onFocus={openDropdown}
        onChange={(e) => {
          onInputValueChange(e.target.value);
          if (!disabled) {
            setIsOpen(true);
            setHighlightedIndex(0);
            setScrollTop(0);
          }
        }}
        onKeyDown={(e) => {
          if (disabled) return;
          if (!isOpen && (e.key === "ArrowDown" || e.key === "ArrowUp")) {
            openDropdown();
            return;
          }
          if (!isOpen) return;
          if (e.key === "ArrowDown") {
            e.preventDefault();
            if (!items.length) return;
            setHighlightedIndex((prev) => (prev < items.length - 1 ? prev + 1 : 0));
          } else if (e.key === "ArrowUp") {
            e.preventDefault();
            if (!items.length) return;
            setHighlightedIndex((prev) => (prev > 0 ? prev - 1 : items.length - 1));
          } else if (e.key === "Enter") {
            if (highlightedIndex >= 0 && highlightedIndex < items.length) {
              e.preventDefault();
              const item = items[highlightedIndex];
              onSelect(item);
              closeDropdown();
            }
          } else if (e.key === "Escape") {
            e.preventDefault();
            closeDropdown();
          }
        }}
        disabled={disabled}
        autoComplete="off"
        role="combobox"
        aria-expanded={isOpen}
        aria-controls={listId}
        aria-autocomplete="list"
      />
      {isOpen && (
        <div
          id={listId}
          ref={listRef}
          className="dropdown-menu show w-100 mt-1 p-0"
          style={{ maxHeight: `${listHeight}px`, overflowY: "auto" }}
          onScroll={(e) => setScrollTop((e.target as HTMLDivElement).scrollTop)}
        >
          {loading ? (
            <div className="dropdown-item text-muted">{loadingText}</div>
          ) : items.length === 0 ? (
            <div className="dropdown-item text-muted">{emptyText}</div>
          ) : (
            <div style={{ height: `${items.length * rowHeight}px`, position: "relative" }}>
              {virtualItems.map((item, localIndex) => {
                const index = virtualStartIndex + localIndex;
                return (
                  <button
                    key={item.key}
                    type="button"
                    className={`dropdown-item text-wrap ${index === highlightedIndex ? "active" : ""}`}
                    style={{
                      position: "absolute",
                      top: `${index * rowHeight}px`,
                      left: 0,
                      right: 0,
                      height: `${rowHeight}px`,
                      overflow: "hidden",
                      textOverflow: "ellipsis",
                      whiteSpace: "nowrap",
                    }}
                    onMouseEnter={() => setHighlightedIndex(index)}
                    onMouseDown={(evt) => evt.preventDefault()}
                    onClick={() => {
                      onSelect(item);
                      closeDropdown();
                    }}
                    title={item.title}
                  >
                    {renderHighlighted(item.label, inputValue)}
                  </button>
                );
              })}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

