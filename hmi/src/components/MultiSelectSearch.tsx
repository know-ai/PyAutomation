import {
  memo,
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
import { TAG_PICKER_ITEM_HEIGHT } from "./tagPicker";
import { firstUnselectedIndex, sortTagsWithSelectedFirst } from "../utils/tagSort";
import { readUiScale } from "../utils/displayDensity";

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
  selectedGroupLabel?: string;
  otherGroupLabel?: string;
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

const PANEL_MAX_HEIGHT = 580;
const PANEL_MIN_WIDTH = 280;
const VIEWPORT_GAP = 8;

function scaledPx(base: number): number {
  return Math.round(base * readUiScale());
}

function sameIds(left: string[], right: string[]): boolean {
  return left.length === right.length && left.every((value, index) => value === right[index]);
}

function sameOptions(left: MultiSelectOption[], right: MultiSelectOption[]): boolean {
  if (left === right) return true;
  if (left.length !== right.length) return false;
  return left.every(
    (option, index) =>
      option.value === right[index].value &&
      option.label === right[index].label &&
      option.description === right[index].description
  );
}

function MultiSelectSearchInner({
  options,
  selected,
  onChange,
  placeholder = "Select…",
  searchPlaceholder = "Search…",
  emptyText = "No results",
  selectAllLabel = "Select all",
  clearLabel = "Clear",
  selectedCountLabel,
  selectedGroupLabel,
  otherGroupLabel,
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

  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [highlightIndex, setHighlightIndex] = useState(0);
  const [position, setPosition] = useState<PanelPosition | null>(null);
  /** Bumped only on keyboard nav so VirtualList scrolls without fighting the wheel. */
  const [keyboardScrollToken, setKeyboardScrollToken] = useState(0);

  if (import.meta.env.DEV && typeof window !== "undefined") {
    const w = window as Window & { __pickerRenderCount?: number };
    w.__pickerRenderCount = (w.__pickerRenderCount || 0) + 1;
  }

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
    const matches = q
      ? options.filter((option) => {
          return (
            option.label.toLowerCase().includes(q) ||
            option.value.toLowerCase().includes(q) ||
            (option.description ? option.description.toLowerCase().includes(q) : false)
          );
        })
      : options;
    return sortTagsWithSelectedFirst(matches, selected);
  }, [options, query, selected]);

  const unselectedStart = useMemo(
    () => firstUnselectedIndex(filtered, selected),
    [filtered, selected]
  );

  const allFilteredSelected =
    filtered.length > 0 && filtered.every((option) => selectedSet.has(option.value));

  const updatePosition = useCallback(() => {
    const trigger = triggerRef.current;
    if (!trigger) return;

    const gap = scaledPx(VIEWPORT_GAP);
    const minWidth = scaledPx(PANEL_MIN_WIDTH);
    const flipBelow = scaledPx(180);
    const minPanel = scaledPx(160);

    const rect = trigger.getBoundingClientRect();
    const viewportHeight = window.innerHeight;
    const viewportWidth = window.innerWidth;
    const maxHeight = Math.min(scaledPx(PANEL_MAX_HEIGHT), Math.floor(viewportHeight * 0.6));
    const spaceBelow = viewportHeight - rect.bottom - gap;
    const spaceAbove = rect.top - gap;
    const placement: "bottom" | "top" =
      spaceBelow < flipBelow && spaceAbove > spaceBelow ? "top" : "bottom";
    const available = placement === "bottom" ? spaceBelow : spaceAbove;
    const width = Math.min(Math.max(rect.width, minWidth), viewportWidth - gap * 2);
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
    onClose?.();
  }, [onClose]);

  const highlightFromKeyboard = useCallback((index: number) => {
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
    };
  }, [close, open, updatePosition]);

  useEffect(() => {
    setHighlightIndex(0);
  }, [query]);

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
      event.stopPropagation();
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

  const itemHeight = scaledPx(TAG_PICKER_ITEM_HEIGHT);

  const renderTagItem = useCallback(
    (option: MultiSelectOption, index: number) => {
      const isSelected = selectedSet.has(option.value);
      const isHighlighted = index === highlightIndex;
      const showValue = option.label !== option.value;
      const showSelectedHeader = index === 0 && isSelected && Boolean(selectedGroupLabel);
      const showOtherHeader =
        index === unselectedStart && unselectedStart > 0 && Boolean(otherGroupLabel);
      const showDivider =
        !showOtherHeader && unselectedStart > 0 && index === unselectedStart;
      return (
        <div
          className={`multi-select-search-item${
            showSelectedHeader || showOtherHeader ? " has-header" : ""
          }${showDivider ? " has-divider" : ""}`}
        >
          {showSelectedHeader && (
            <div className="multi-select-search__group" role="presentation">
              {selectedGroupLabel}
            </div>
          )}
          {showOtherHeader && (
            <div className="multi-select-search__group" role="presentation">
              {otherGroupLabel}
            </div>
          )}
          <button
            type="button"
            role="option"
            aria-selected={isSelected}
            className={`multi-select-search__option${isSelected ? " is-selected" : ""}${
              isHighlighted ? " is-highlighted" : ""
            }`}
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
                <span className="multi-select-search__option-desc">{option.description}</span>
              )}
            </span>
          </button>
        </div>
      );
    },
    [
      highlightIndex,
      otherGroupLabel,
      selectedGroupLabel,
      selectedSet,
      toggleOption,
      unselectedStart,
    ]
  );

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
                position.placement === "top" ? window.innerHeight - position.top : undefined,
              left: position.left,
              width: position.width,
              maxHeight: position.maxHeight,
            }}
            role="listbox"
            id={listId}
            aria-multiselectable="true"
            aria-labelledby={triggerId}
            onKeyDown={handlePanelKeyDown}
            onWheel={(event) => event.stopPropagation()}
            onScroll={(event) => event.stopPropagation()}
            onMouseMove={(event) => event.stopPropagation()}
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
                className="multi-select-search__list multi-select-search-list"
                items={filtered}
                height={Math.max(scaledPx(160), position.maxHeight - scaledPx(96))}
                itemHeight={itemHeight}
                highlightedIndex={highlightIndex}
                scrollToIndexToken={keyboardScrollToken}
                getKey={(option) => option.value}
                renderItem={renderTagItem}
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

export const MultiSelectSearch = memo(MultiSelectSearchInner, (prev, next) => {
  return (
    prev.disabled === next.disabled &&
    prev.placeholder === next.placeholder &&
    prev.searchPlaceholder === next.searchPlaceholder &&
    prev.emptyText === next.emptyText &&
    prev.selectAllLabel === next.selectAllLabel &&
    prev.clearLabel === next.clearLabel &&
    prev.selectedGroupLabel === next.selectedGroupLabel &&
    prev.otherGroupLabel === next.otherGroupLabel &&
    prev.className === next.className &&
    prev.onChange === next.onChange &&
    prev.onClose === next.onClose &&
    prev.selectedCountLabel === next.selectedCountLabel &&
    sameIds(prev.selected, next.selected) &&
    sameOptions(prev.options, next.options)
  );
});
MultiSelectSearch.displayName = "MultiSelectSearch";
