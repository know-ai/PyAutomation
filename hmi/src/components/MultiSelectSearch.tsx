import {
  useCallback,
  useEffect,
  useId,
  useMemo,
  useRef,
  useState,
  type CSSProperties,
  type KeyboardEvent,
} from "react";
import { createPortal } from "react-dom";
import { VirtualList } from "./VirtualList";

export type MultiSelectOption = {
  value: string;
  label: string;
  description?: string;
};

type MultiSelectSearchProps = {
  options: MultiSelectOption[];
  selected: string[];
  onChange: (selected: string[]) => void;
  placeholder?: string;
  searchPlaceholder?: string;
  emptyText?: string;
  selectAllLabel?: string;
  clearLabel?: string;
  selectedCountLabel?: (count: number) => string;
  disabled?: boolean;
  className?: string;
  style?: CSSProperties;
  onClose?: () => void;
};

type PanelPosition = {
  top: number;
  left: number;
  width: number;
  maxHeight: number;
  placement: "bottom" | "top";
};

import { readUiScale } from "../utils/displayDensity";

const PANEL_MAX_HEIGHT = 320;
const PANEL_MIN_WIDTH = 280;
const VIEWPORT_GAP = 8;

function scaledPx(base: number): number {
  return Math.round(base * readUiScale());
}

export function MultiSelectSearch({
  options,
  selected,
  onChange,
  placeholder = "Select…",
  searchPlaceholder = "Search…",
  emptyText = "No results",
  selectAllLabel = "Select all",
  clearLabel = "Clear",
  selectedCountLabel,
  disabled = false,
  className,
  style,
  onClose,
}: MultiSelectSearchProps) {
  const triggerId = useId();
  const listId = useId();
  const triggerRef = useRef<HTMLButtonElement>(null);
  const panelRef = useRef<HTMLDivElement>(null);
  const searchRef = useRef<HTMLInputElement>(null);
  const optionRefs = useRef<Array<HTMLButtonElement | null>>([]);
  /** Only keyboard navigation should scroll the list to the highlight. */
  const keyboardNavRef = useRef(false);
  const scrollingRef = useRef(false);
  const scrollIdleTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [highlightIndex, setHighlightIndex] = useState(0);
  const [position, setPosition] = useState<PanelPosition | null>(null);
  /** Bumped only on keyboard nav so VirtualList scrolls without fighting the wheel. */
  const [keyboardScrollToken, setKeyboardScrollToken] = useState(0);

  const selectedSet = useMemo(() => new Set(selected), [selected]);

  const labelByValue = useMemo(() => {
    const map = new Map<string, string>();
    for (const option of options) {
      map.set(option.value, option.label);
    }
    return map;
  }, [options]);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return options;
    return options.filter((option) => {
      return (
        option.label.toLowerCase().includes(q) ||
        option.value.toLowerCase().includes(q) ||
        (option.description ? option.description.toLowerCase().includes(q) : false)
      );
    });
  }, [options, query]);

  const allFilteredSelected =
    filtered.length > 0 && filtered.every((option) => selectedSet.has(option.value));

  const updatePosition = useCallback(() => {
    const trigger = triggerRef.current;
    if (!trigger) return;

    const gap = scaledPx(VIEWPORT_GAP);
    const minWidth = scaledPx(PANEL_MIN_WIDTH);
    const maxHeight = scaledPx(PANEL_MAX_HEIGHT);
    const flipBelow = scaledPx(180);
    const minPanel = scaledPx(160);

    const rect = trigger.getBoundingClientRect();
    const viewportHeight = window.innerHeight;
    const viewportWidth = window.innerWidth;
    const spaceBelow = viewportHeight - rect.bottom - gap;
    const spaceAbove = rect.top - gap;
    const placement: "bottom" | "top" =
      spaceBelow < flipBelow && spaceAbove > spaceBelow ? "top" : "bottom";
    const available = placement === "bottom" ? spaceBelow : spaceAbove;
    const width = Math.min(
      Math.max(rect.width, minWidth),
      viewportWidth - gap * 2
    );
    let left = rect.left;
    if (left + width > viewportWidth - gap) {
      left = Math.max(gap, viewportWidth - gap - width);
    }

    setPosition({
      top: placement === "bottom" ? rect.bottom + 4 : rect.top - 4,
      left,
      width,
      maxHeight: Math.min(maxHeight, Math.max(minPanel, available)),
      placement,
    });
  }, []);

  const close = useCallback(() => {
    setOpen(false);
    setQuery("");
    setHighlightIndex(0);
    keyboardNavRef.current = false;
    onClose?.();
  }, [onClose]);

  const markListScrolling = useCallback(() => {
    scrollingRef.current = true;
    if (scrollIdleTimerRef.current) {
      clearTimeout(scrollIdleTimerRef.current);
    }
    scrollIdleTimerRef.current = setTimeout(() => {
      scrollingRef.current = false;
      scrollIdleTimerRef.current = null;
    }, 120);
  }, []);

  const highlightFromMouse = useCallback((index: number) => {
    // While the user is scrolling, ignore hover highlights — they fight scrollIntoView
    // and pull the list back toward the cursor position (usually the top of the panel).
    if (scrollingRef.current || keyboardNavRef.current) return;
    setHighlightIndex(index);
  }, []);

  const highlightFromKeyboard = useCallback((index: number) => {
    keyboardNavRef.current = true;
    setHighlightIndex(index);
    setKeyboardScrollToken((token) => token + 1);
  }, []);

  const toggleOption = useCallback(
    (value: string) => {
      if (selectedSet.has(value)) {
        onChange(selected.filter((item) => item !== value));
      } else {
        onChange([...selected, value]);
      }
    },
    [onChange, selected, selectedSet]
  );

  const selectFiltered = useCallback(() => {
    const next = new Set(selected);
    for (const option of filtered) {
      next.add(option.value);
    }
    onChange(Array.from(next));
  }, [filtered, onChange, selected]);

  const clearFiltered = useCallback(() => {
    if (!query.trim()) {
      onChange([]);
      return;
    }
    const filteredValues = new Set(filtered.map((option) => option.value));
    onChange(selected.filter((value) => !filteredValues.has(value)));
  }, [filtered, onChange, query, selected]);

  useEffect(() => {
    if (!open) return;

    updatePosition();
    const frame = window.requestAnimationFrame(() => {
      searchRef.current?.focus();
    });

    const onPointerDown = (event: MouseEvent) => {
      const target = event.target as Node;
      if (triggerRef.current?.contains(target) || panelRef.current?.contains(target)) {
        return;
      }
      close();
    };

    const onReposition = (event: Event) => {
      // Ignore scrolls inside the dropdown panel — they must not reset layout/scroll.
      const target = event.target;
      if (
        target instanceof Node &&
        panelRef.current &&
        (target === panelRef.current || panelRef.current.contains(target))
      ) {
        return;
      }
      updatePosition();
    };

    document.addEventListener("mousedown", onPointerDown);
    window.addEventListener("resize", onReposition);
    window.addEventListener("scroll", onReposition, true);

    return () => {
      window.cancelAnimationFrame(frame);
      document.removeEventListener("mousedown", onPointerDown);
      window.removeEventListener("resize", onReposition);
      window.removeEventListener("scroll", onReposition, true);
      if (scrollIdleTimerRef.current) {
        clearTimeout(scrollIdleTimerRef.current);
        scrollIdleTimerRef.current = null;
      }
    };
  }, [close, open, updatePosition]);

  useEffect(() => {
    setHighlightIndex(0);
    keyboardNavRef.current = false;
  }, [query]);

  useEffect(() => {
    if (!open || !keyboardNavRef.current) return;
    keyboardNavRef.current = false;
    const el = optionRefs.current[highlightIndex];
    el?.scrollIntoView({ block: "nearest" });
  }, [highlightIndex, keyboardScrollToken, open]);

  const handleTriggerKeyDown = (event: KeyboardEvent<HTMLButtonElement>) => {
    if (disabled) return;
    if (event.key === "ArrowDown" || event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      setOpen(true);
    }
  };

  const handlePanelKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    if (event.key === "Escape") {
      event.preventDefault();
      close();
      triggerRef.current?.focus();
      return;
    }

    if (event.key === "ArrowDown") {
      event.preventDefault();
      highlightFromKeyboard(Math.min(highlightIndex + 1, Math.max(filtered.length - 1, 0)));
      return;
    }

    if (event.key === "ArrowUp") {
      event.preventDefault();
      highlightFromKeyboard(Math.max(highlightIndex - 1, 0));
      return;
    }

    if (event.key === "Enter" && filtered[highlightIndex]) {
      event.preventDefault();
      toggleOption(filtered[highlightIndex].value);
    }
  };

  const summary = (() => {
    if (selected.length === 0) {
      return <span className="multi-select-search__placeholder">{placeholder}</span>;
    }
    if (selected.length === 1) {
      return (
        <span className="multi-select-search__summary-text">
          {labelByValue.get(selected[0]) || selected[0]}
        </span>
      );
    }
    const label = selectedCountLabel
      ? selectedCountLabel(selected.length)
      : `${selected.length} selected`;
    return <span className="multi-select-search__summary-text">{label}</span>;
  })();

  const panel =
    open && position
      ? createPortal(
          <div
            ref={panelRef}
            className={`multi-select-search__panel multi-select-search__panel--${position.placement}`}
            style={{
              top: position.placement === "bottom" ? position.top : undefined,
              bottom:
                position.placement === "top"
                  ? window.innerHeight - position.top
                  : undefined,
              left: position.left,
              width: position.width,
              maxHeight: position.maxHeight,
            }}
            role="listbox"
            id={listId}
            aria-multiselectable="true"
            aria-labelledby={triggerId}
            onKeyDown={handlePanelKeyDown}
          >
            <div className="multi-select-search__search">
              <i className="bi bi-search" aria-hidden="true" />
              <input
                ref={searchRef}
                type="text"
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                placeholder={searchPlaceholder}
                aria-label={searchPlaceholder}
                autoComplete="off"
                spellCheck={false}
              />
              {query && (
                <button
                  type="button"
                  className="multi-select-search__clear-query"
                  onClick={() => setQuery("")}
                  aria-label={clearLabel}
                >
                  <i className="bi bi-x" />
                </button>
              )}
            </div>

            <div className="multi-select-search__toolbar">
              <span className="multi-select-search__count">
                {selected.length}/{options.length}
              </span>
              <div className="multi-select-search__actions">
                <button
                  type="button"
                  onClick={selectFiltered}
                  disabled={filtered.length === 0 || allFilteredSelected}
                >
                  {selectAllLabel}
                </button>
                <button type="button" onClick={clearFiltered} disabled={selected.length === 0}>
                  {clearLabel}
                </button>
              </div>
            </div>

            {filtered.length === 0 ? (
              <div className="multi-select-search__empty">{emptyText}</div>
            ) : (
            <VirtualList
              className="multi-select-search__list"
              items={filtered}
              height={Math.max(scaledPx(160), position.maxHeight - scaledPx(96))}
              itemHeight={scaledPx(48)}
              highlightedIndex={highlightIndex}
              scrollToIndexToken={keyboardScrollToken}
              onScroll={markListScrolling}
              getKey={(option) => option.value}
              renderItem={(option, index) => {
                const isSelected = selectedSet.has(option.value);
                const isHighlighted = index === highlightIndex;
                const showValue = option.label !== option.value;
                return (
                  <button
                    type="button"
                    role="option"
                    aria-selected={isSelected}
                    ref={(el) => {
                      optionRefs.current[index] = el;
                    }}
                    className={`multi-select-search__option${
                      isSelected ? " is-selected" : ""
                    }${isHighlighted ? " is-highlighted" : ""}`}
                    onMouseEnter={() => highlightFromMouse(index)}
                    onClick={() => toggleOption(option.value)}
                  >
                    <span
                      className={`multi-select-search__check${isSelected ? " is-on" : ""}`}
                      aria-hidden="true"
                    >
                      {isSelected ? <i className="bi bi-check-lg" /> : null}
                    </span>
                    <span className="multi-select-search__option-text">
                      <span className="multi-select-search__option-label">{option.label}</span>
                      {showValue && (
                        <span className="multi-select-search__option-value">{option.value}</span>
                      )}
                      {option.description && (
                        <span className="multi-select-search__option-desc">
                          {option.description}
                        </span>
                      )}
                    </span>
                  </button>
                );
              }}
            />
            )}
          </div>,
          document.body
        )
      : null;

  return (
    <div className={`multi-select-search ${className || ""}`.trim()} style={style}>
      <button
        ref={triggerRef}
        type="button"
        id={triggerId}
        className="multi-select-search__trigger"
        disabled={disabled}
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-controls={open ? listId : undefined}
        onClick={() => {
          if (disabled) return;
          if (open) {
            close();
          } else {
            setOpen(true);
          }
        }}
        onKeyDown={handleTriggerKeyDown}
      >
        {summary}
        {selected.length > 0 && (
          <span className="multi-select-search__badge">{selected.length}</span>
        )}
        <i
          className={`bi ${open ? "bi-chevron-up" : "bi-chevron-down"} multi-select-search__chevron`}
          aria-hidden="true"
        />
      </button>
      {panel}
    </div>
  );
}
