import { useState, useEffect, useMemo, useRef, useCallback, memo } from "react";
import { Card } from "./Card";
import { Button } from "./Button";
import Plot from "react-plotly.js";
import type { Data, Layout } from "plotly.js";
import { useTheme } from "../hooks/useTheme";
import { useAppSelector } from "../hooks/useAppSelector";
import { useAppDispatch } from "../hooks/useAppDispatch";
import { useTranslation } from "../hooks/useTranslation";
import { getTagsList, type Tag } from "../services/tags";
import { showToast } from "../utils/toast";
import {
  DEFAULT_TIME_SPAN_MINUTES,
  TIME_SPAN_OPTIONS_MINUTES,
  normalizeTimeSpanMinutes,
  pruneHistoryByTime,
  subscribeTagHistory,
  unsubscribeTagHistory,
  type TagHistoryPoint,
  type TimeSpanMinutes,
} from "../store/slices/tagsSlice";
import { usePageHidden } from "../hooks/usePageHidden";
import { VirtualList } from "./VirtualList";
import { useDisplayTimezone } from "../hooks/useDisplayTimezone";
import { toDisplayDate } from "../utils/timezone";
import { resolveTagDisplayLabel } from "../utils/tagDisplayLabel";
import { isFilteredDerivativeName, sourceTagName } from "../utils/filteredTags";
import { isDisplayableThreshold, resolveTagThreshold } from "../utils/tagThreshold";
import { QualityBadge } from "./QualityBadge";

/** @deprecated Usar timeSpanMinutes; conservado por compatibilidad de imports. */
export const BUFFER_SIZE_MIN = 120;
/** @deprecated Usar timeSpanMinutes. */
export const BUFFER_SIZE_MAX = 360;

function historyRevision(
  histories: Array<TagHistoryPoint[] | undefined>,
  timeSpanMinutes: number,
  nowMs: number
): string {
  return (
    histories
      .map((h) => {
        if (!h || h.length === 0) return "0";
        const last = h[h.length - 1];
        return `${h.length}:${last?.timestamp}:${last?.value}`;
      })
      .join("|") + `:${timeSpanMinutes}:${Math.floor(nowMs / 1000)}`
  );
}

export interface StripChartConfig {
  id: string;
  title: string;
  tagNames: string[];
  /** Ventana temporal visible (minutos): 1 | 2 | 3 | 5. */
  timeSpanMinutes: TimeSpanMinutes;
  x: number;
  y: number;
  w: number;
  h: number;
}

interface StripChartProps {
  config: StripChartConfig;
  isEditMode: boolean;
  showThresholds?: boolean;
  onConfigChange: (config: StripChartConfig) => void;
  onDelete: () => void;
}

function StripChartInner({
  config,
  isEditMode,
  showThresholds = false,
  onConfigChange,
  onDelete,
}: StripChartProps) {
  const { mode } = useTheme();
  const { t } = useTranslation();
  const { timeZone } = useDisplayTimezone();
  const dispatch = useAppDispatch();
  const pageHidden = usePageHidden();
  const tagNamesKey = config.tagNames.join("|");
  const timeSpanMinutes = normalizeTimeSpanMinutes(config.timeSpanMinutes);
  const timeSpanMs = timeSpanMinutes * 60 * 1000;

  const histories = useAppSelector(
    (state) => config.tagNames.map((name) => state.tags.tagHistory[name]),
    (left, right) =>
      left.length === right.length && left.every((item, index) => item === right[index])
  );
  const liveTags = useAppSelector((state) => state.tags.tagValues);
  const machines = useAppSelector((state) => state.machines.machines);
  const historiesRef = useRef(histories);
  historiesRef.current = histories;
  const [throttledHistories, setThrottledHistories] = useState(histories);
  const [nowMs, setNowMs] = useState(() => Date.now());
  useEffect(() => {
    const id = window.setInterval(() => {
      setThrottledHistories(historiesRef.current);
      setNowMs(Date.now());
    }, 200);
    return () => window.clearInterval(id);
  }, []);
  const [showTagConfig, setShowTagConfig] = useState(false);
  const [availableTags, setAvailableTags] = useState<Tag[]>([]);
  const [tagSearch, setTagSearch] = useState("");
  const [showSearchDropdown, setShowSearchDropdown] = useState(false);
  const [loadingTags, setLoadingTags] = useState(false);
  const tagConfigRef = useRef<HTMLDivElement>(null);
  const searchInputRef = useRef<HTMLInputElement>(null);
  const searchDropdownRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const loadTags = async () => {
      setLoadingTags(true);
      try {
        const tags = await getTagsList();
        setAvailableTags(tags || []);
      } catch (err: any) {
        console.error("Error loading tags:", err);
        showToast(t("stripChart.errorLoadingTags"), "error");
      } finally {
        setLoadingTags(false);
      }
    };
    loadTags();
  }, []);

  useEffect(() => {
    if (!showTagConfig) return;

    const handlePointerDown = (event: MouseEvent) => {
      const target = event.target as Node;
      if (tagConfigRef.current && !tagConfigRef.current.contains(target)) {
        setShowTagConfig(false);
        setShowSearchDropdown(false);
        return;
      }
      // Inside panel: close only the search list when clicking selected tags / elsewhere.
      if (
        showSearchDropdown &&
        searchDropdownRef.current &&
        !searchDropdownRef.current.contains(target) &&
        searchInputRef.current &&
        !searchInputRef.current.contains(target)
      ) {
        setShowSearchDropdown(false);
      }
    };

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key !== "Escape") return;
      if (showSearchDropdown) {
        setShowSearchDropdown(false);
        event.preventDefault();
        return;
      }
      setShowTagConfig(false);
    };

    document.addEventListener("mousedown", handlePointerDown);
    document.addEventListener("keydown", handleKeyDown);
    return () => {
      document.removeEventListener("mousedown", handlePointerDown);
      document.removeEventListener("keydown", handleKeyDown);
    };
  }, [showTagConfig, showSearchDropdown]);

  useEffect(() => {
    const names = config.tagNames.filter(Boolean);
    names.forEach((name) => dispatch(subscribeTagHistory(name)));
    return () => {
      names.forEach((name) => dispatch(unsubscribeTagHistory(name)));
    };
  }, [dispatch, tagNamesKey]);

  const filteredTags = useMemo(() => {
    if (!tagSearch.trim()) {
      return availableTags;
    }
    const searchLower = tagSearch.toLowerCase();
    return availableTags.filter(
      (tag) =>
        tag.name.toLowerCase().includes(searchLower) ||
        tag.display_name?.toLowerCase().includes(searchLower) ||
        tag.description?.toLowerCase().includes(searchLower)
    );
  }, [availableTags, tagSearch]);

  const unselectedFilteredTags = useMemo(
    () => filteredTags.filter((tag) => !config.tagNames.includes(tag.name)),
    [filteredTags, config.tagNames]
  );

  const getTagMeta = useCallback(
    (tagName: string) => {
      const tag = availableTags.find((item) => item.name === tagName);
      if (!isFilteredDerivativeName(tagName)) return tag;
      const source = availableTags.find((item) => item.name === sourceTagName(tagName));
      if (!source) return tag;
      return {
        ...tag,
        ...source,
        name: tag?.name ?? tagName,
        display_name: source.display_name,
        display_unit: source.display_unit || tag?.display_unit,
        unit: source.unit || tag?.unit,
      } as Tag;
    },
    [availableTags]
  );

  const getTagUnit = useCallback(
    (tagName: string) => {
      const tag = getTagMeta(tagName);
      return tag?.display_unit || tag?.unit || "—";
    },
    [getTagMeta]
  );

  const getTagLabel = useCallback(
    (tagName: string) => resolveTagDisplayLabel(getTagMeta(tagName), tagName),
    [getTagMeta]
  );

  const prunedHistories = useMemo(
    () =>
      throttledHistories.map((history) =>
        pruneHistoryByTime(history || [], timeSpanMs, nowMs)
      ),
    [throttledHistories, timeSpanMs, nowMs]
  );

  const hasAnyPointsInSpan = useMemo(
    () => prunedHistories.some((h) => h.length > 0),
    [prunedHistories]
  );

  const lastPlotRef = useRef<{ data: Data[]; layout: Partial<Layout> }>({ data: [], layout: {} });

  const plotData = useMemo(() => {
    if (pageHidden && lastPlotRef.current.data.length > 0) {
      return lastPlotRef.current;
    }
    if (config.tagNames.length === 0) {
      const empty = { data: [] as Data[], layout: {} as Partial<Layout> };
      lastPlotRef.current = empty;
      return empty;
    }

    const colorPalette = [
      "#1f77b4", "#ff7f0e", "#2ca02c", "#d62728", "#9467bd",
      "#8c564b", "#e377c2", "#7f7f7f", "#bcbd22", "#17becf",
    ];

    const unitOrder: string[] = [];
    config.tagNames.forEach((tagName) => {
      const unit = getTagUnit(tagName);
      if (!unitOrder.includes(unit)) unitOrder.push(unit);
    });

    const unitAxis: Record<string, string> = {};
    unitOrder.forEach((unit, idx) => {
      unitAxis[unit] = idx === 0 ? "y" : "y2";
    });

    const displayTz = timeZone || Intl.DateTimeFormat().resolvedOptions().timeZone || "";
    const rangeStartIso = new Date(nowMs - timeSpanMs).toISOString();
    const rangeEndIso = new Date(nowMs).toISOString();
    const xRange = displayTz
      ? [toDisplayDate(rangeStartIso, displayTz), toDisplayDate(rangeEndIso, displayTz)]
      : [rangeStartIso, rangeEndIso];

    const traces: Data[] = config.tagNames.map((tagName, index) => {
      const bufferSlice = prunedHistories[index] || [];
      const unit = getTagUnit(tagName);
      const x = displayTz
        ? bufferSlice.map((p) => toDisplayDate(p.timestamp, displayTz))
        : bufferSlice.map((p) => p.timestamp);
      return {
        x,
        y: bufferSlice.map((p) => p.value),
        type: "scatter",
        mode: "lines",
        name: getTagLabel(tagName),
        line: { color: colorPalette[index % colorPalette.length], width: 2 },
        yaxis: unitAxis[unit] || "y",
      } as Data;
    });

    if (showThresholds) {
      const thresholdColor = mode === "dark" ? "#adb5bd" : "#999999";
      config.tagNames.forEach((tagName, index) => {
        const threshold = resolveTagThreshold(tagName, machines, liveTags[tagName]);
        if (!isDisplayableThreshold(threshold)) return;

        const bufferSlice = prunedHistories[index] || [];
        const unit = getTagUnit(tagName);
        const x =
          bufferSlice.length >= 2
            ? displayTz
              ? [
                  toDisplayDate(bufferSlice[0].timestamp, displayTz),
                  toDisplayDate(bufferSlice[bufferSlice.length - 1].timestamp, displayTz),
                ]
              : [bufferSlice[0].timestamp, bufferSlice[bufferSlice.length - 1].timestamp]
            : xRange;

        traces.push({
          x,
          y: [threshold, threshold],
          type: "scatter",
          mode: "lines",
          name: t("stripChart.thresholdLegend", { tag: getTagLabel(tagName) }),
          line: { color: thresholdColor, width: 1, dash: "dash" },
          opacity: 0.5,
          yaxis: unitAxis[unit] || "y",
          hovertemplate: `${t("stripChart.thresholdLine")}: ${threshold}<extra></extra>`,
        } as Data);
      });
    }

    const axisColors: Record<string, string> = {};
    traces.forEach((tr) => {
      const axis = (tr as any).yaxis || "y";
      if (!axisColors[axis]) {
        axisColors[axis] = (tr as any).line?.color || "#6c757d";
      }
    });

    const layout: Partial<Layout> = {
      autosize: true,
      uirevision: config.id,
      datarevision: historyRevision(prunedHistories, timeSpanMinutes, nowMs),
      margin: { l: 60, r: unitOrder.length > 1 ? 60 : 20, t: 40, b: 28 },
      paper_bgcolor: mode === "dark" ? "#212529" : "#ffffff",
      plot_bgcolor: mode === "dark" ? "#2c3034" : "#f8f9fa",
      font: { color: mode === "dark" ? "#ffffff" : "#212529" },
      xaxis: {
        type: "date",
        range: xRange,
        tickformat: "%H:%M:%S",
        hoverformat: "%H:%M:%S",
        color: mode === "dark" ? "#ffffff" : "#212529",
        gridcolor: mode === "dark" ? "#495057" : "#dee2e6",
      },
      yaxis: {
        title: unitOrder[0] || "Valor",
        color: axisColors["y"] || (mode === "dark" ? "#ffffff" : "#212529"),
        gridcolor: mode === "dark" ? "#495057" : "#dee2e6",
      },
      showlegend: config.tagNames.length > 1 || (showThresholds && traces.length > config.tagNames.length),
      legend: {
        x: 1.02,
        xanchor: "left",
        y: 1,
        bgcolor: mode === "dark" ? "rgba(33, 37, 41, 0.8)" : "rgba(255, 255, 255, 0.8)",
      },
    };

    if (unitOrder.length > 1) {
      (layout as any).yaxis2 = {
        title: unitOrder[1],
        overlaying: "y",
        side: "right",
        color: axisColors["y2"] || (mode === "dark" ? "#ffffff" : "#212529"),
        gridcolor: "rgba(0,0,0,0)",
      };
    }

    const next = { data: traces, layout };
    lastPlotRef.current = next;
    return next;
  }, [
    config.tagNames,
    config.id,
    timeSpanMinutes,
    timeSpanMs,
    nowMs,
    mode,
    getTagUnit,
    getTagLabel,
    prunedHistories,
    pageHidden,
    timeZone,
    showThresholds,
    machines,
    liveTags,
    t,
  ]);

  const handleTagToggle = (tagName: string) => {
    const isSelected = config.tagNames.includes(tagName);
    const unit = getTagUnit(tagName);

    const currentUnits = new Set(config.tagNames.map(getTagUnit));
    const wouldAddNewUnit = !isSelected && !currentUnits.has(unit);

    if (wouldAddNewUnit && currentUnits.size >= 2) {
      showToast(t("stripChart.maxUnitsPerChart"), "warning");
      return;
    }

    const newTagNames = isSelected
      ? config.tagNames.filter((name) => name !== tagName)
      : [...config.tagNames, tagName];

    onConfigChange({
      ...config,
      tagNames: newTagNames,
    });
  };

  const handleTimeSpanChange = (raw: string) => {
    const next = normalizeTimeSpanMinutes(Number(raw));
    onConfigChange({
      ...config,
      timeSpanMinutes: next,
    });
  };

  const handleTitleChange = (newTitle: string) => {
    onConfigChange({
      ...config,
      title: newTitle,
    });
  };

  return (
    <div style={{ height: "100%", width: "100%", display: "flex", flexDirection: "column" }}>
      <Card
        className="overflow-visible"
        style={{ height: "100%", width: "100%", display: "flex", flexDirection: "column", overflow: "visible" }}
        headerClassName="py-1 px-2 overflow-visible"
        bodyClassName="p-0"
        title={
          <div className="d-flex justify-content-between align-items-center w-100 drag-handle" style={{ cursor: isEditMode ? "move" : "default" }}>
            <div className="d-flex align-items-center gap-2">
              {isEditMode && <i className="bi bi-grip-vertical text-muted"></i>}
              {isEditMode ? (
                <input
                  type="text"
                  className="form-control form-control-sm"
                  value={config.title}
                  onChange={(e) => handleTitleChange(e.target.value)}
                  style={{ width: "auto", minWidth: "150px", maxWidth: "300px" }}
                  placeholder={t("stripChart.titlePlaceholder")}
                  onClick={(e) => e.stopPropagation()}
                />
              ) : (
                <span className="d-inline-flex align-items-center gap-2 flex-wrap">
                  <span>{config.title || t("stripChart.defaultTitle")}</span>
                  {config.tagNames.map((tagName) => {
                    const live = liveTags[tagName];
                    return (
                      <span key={tagName} className="d-inline-flex align-items-center gap-1">
                        <span className="small text-muted">{getTagLabel(tagName)}</span>
                        <QualityBadge
                          quality={live?.quality}
                          qualityLabel={live?.quality_label}
                          substatus={live?.quality_substatus}
                          stale={Boolean(live?.stale)}
                          staleAgeMs={typeof live?.stale_age_ms === "number" ? live.stale_age_ms : null}
                        />
                      </span>
                    );
                  })}
                </span>
              )}
            </div>
            <div className="d-flex gap-2 align-items-center position-relative" onClick={(e) => e.stopPropagation()}>
              {isEditMode && (
                <>
                  <label className="small text-muted mb-0 d-none d-sm-inline" htmlFor={`time-span-${config.id}`}>
                    {t("stripChart.timeSpanLabel")}
                  </label>
                  <select
                    id={`time-span-${config.id}`}
                    className="form-select form-select-sm"
                    style={{ width: "auto", minWidth: "5.5rem" }}
                    value={timeSpanMinutes}
                    onChange={(e) => handleTimeSpanChange(e.target.value)}
                    title={t("stripChart.timeSpanLabel")}
                    aria-label={t("stripChart.timeSpanLabel")}
                  >
                    {TIME_SPAN_OPTIONS_MINUTES.map((mins) => (
                      <option key={mins} value={mins}>
                        {t("stripChart.timeSpanOption", { minutes: mins })}
                      </option>
                    ))}
                  </select>
                </>
              )}
              {isEditMode && (
                <>
                  <Button
                    variant="primary"
                    className="btn-sm"
                    onClick={() => {
                      setShowTagConfig((open) => {
                        const next = !open;
                        if (next) {
                          // If tags already selected, keep list closed so chips stay reachable.
                          setShowSearchDropdown(config.tagNames.length === 0);
                          setTagSearch("");
                        } else {
                          setShowSearchDropdown(false);
                        }
                        return next;
                      });
                    }}
                    title={t("stripChart.configureTags")}
                  >
                    <i className="bi bi-tags me-1"></i>
                    {t("stripChart.tags")} ({config.tagNames.length})
                  </Button>
                  <Button
                    variant="danger"
                    className="btn-sm"
                    onClick={onDelete}
                    title={t("stripChart.deleteChart")}
                  >
                    <i className="bi bi-trash"></i>
                  </Button>
                  {showTagConfig && (
                    <div
                      ref={tagConfigRef}
                      className="stripchart-tag-config position-absolute bg-body border rounded shadow-lg p-3"
                      onClick={(e) => e.stopPropagation()}
                    >
                      <div className="mb-2 position-relative">
                        <div className="d-flex justify-content-between align-items-center mb-1">
                          <label className="form-label small mb-0">{t("stripChart.searchTag")}</label>
                          {showSearchDropdown && (
                            <button
                              type="button"
                              className="btn btn-link btn-sm p-0 text-decoration-none"
                              onClick={() => setShowSearchDropdown(false)}
                            >
                              {t("stripChart.hideSearchList")}
                            </button>
                          )}
                        </div>
                        <input
                          ref={searchInputRef}
                          type="text"
                          className="form-control form-control-sm"
                          value={tagSearch}
                          onChange={(e) => {
                            setTagSearch(e.target.value);
                            setShowSearchDropdown(true);
                          }}
                          placeholder={t("stripChart.searchPlaceholder")}
                          onFocus={() => setShowSearchDropdown(true)}
                          aria-expanded={showSearchDropdown}
                          aria-controls="stripchart-tag-search-list"
                        />
                        {showSearchDropdown && (
                          <div
                            id="stripchart-tag-search-list"
                            ref={searchDropdownRef}
                            className="stripchart-tag-search-list position-absolute bg-body border rounded shadow-sm w-100"
                          >
                            {unselectedFilteredTags.length === 0 ? (
                              <div className="text-muted small p-2">{t("stripChart.noTagsAvailable")}</div>
                            ) : (
                              <VirtualList
                                items={unselectedFilteredTags}
                                height={280}
                                itemHeight={52}
                                getKey={(tag) => tag.name}
                                renderItem={(tag) => (
                                  <div
                                    className="p-2 border-bottom cursor-pointer"
                                    onMouseDown={(e) => e.preventDefault()}
                                    onClick={() => {
                                      handleTagToggle(tag.name);
                                      setShowSearchDropdown(false);
                                      setTagSearch("");
                                    }}
                                  >
                                    <div className="d-flex justify-content-between align-items-center">
                                      <div>
                                        <strong className="small">{resolveTagDisplayLabel(tag, tag.name)}</strong>
                                        <br />
                                        <span className="text-muted small">
                                          {tag.name} · {getTagUnit(tag.name)}
                                        </span>
                                      </div>
                                      <i className="bi bi-plus-circle text-primary"></i>
                                    </div>
                                  </div>
                                )}
                              />
                            )}
                          </div>
                        )}
                        <div className="form-text small text-muted mt-1">
                          {t("stripChart.searchDismissHint")}
                        </div>
                      </div>
                      <div
                        className="mb-0"
                        onMouseDown={() => {
                          if (showSearchDropdown) setShowSearchDropdown(false);
                        }}
                      >
                        <label className="form-label small d-flex justify-content-between align-items-center">
                          <span>{t("stripChart.selectedTags")}</span>
                          <span className="badge bg-secondary">
                            {t("stripChart.unitsCount", {
                              count: Array.from(new Set(config.tagNames.map(getTagUnit))).length,
                            })}
                          </span>
                        </label>
                        <div className="d-flex flex-wrap gap-1">
                          {config.tagNames.map((tagName) => (
                              <span key={tagName} className="badge bg-primary">
                                {getTagLabel(tagName)}
                                <button
                                  type="button"
                                  className="btn-close btn-close-white ms-1"
                                  style={{ fontSize: "0.6rem" }}
                                  onClick={() => handleTagToggle(tagName)}
                                  aria-label="Remove"
                                ></button>
                              </span>
                          ))}
                        </div>
                      </div>
                    </div>
                  )}
                </>
              )}
            </div>
          </div>
        }
      >
        <div style={{ width: "100%", flex: 1, minHeight: 0, position: "relative", display: "flex", flexDirection: "column" }}>
          {config.tagNames.length === 0 ? (
            <div className="text-center py-5 text-muted" style={{ height: "100%", display: "flex", flexDirection: "column", justifyContent: "center" }}>
              <i className="bi bi-graph-up" style={{ fontSize: "3rem" }}></i>
              <p className="mt-3">{t("stripChart.emptyState")}</p>
            </div>
          ) : !hasAnyPointsInSpan ? (
            <div className="text-center py-5 text-muted" style={{ height: "100%", display: "flex", flexDirection: "column", justifyContent: "center" }}>
              <i className="bi bi-clock-history" style={{ fontSize: "3rem" }}></i>
              <p className="mt-3">{t("stripChart.emptyTimeSpan")}</p>
            </div>
          ) : (
            <Plot
              data={plotData.data}
              layout={plotData.layout}
              revision={String((plotData.layout as { datarevision?: string }).datarevision || "")}
              style={{ width: "100%", height: "100%" }}
              config={{
                displayModeBar: true,
                modeBarButtonsToRemove: ["lasso2d", "select2d"],
                displaylogo: false,
                responsive: true,
              }}
              useResizeHandler={true}
            />
          )}
        </div>
      </Card>
    </div>
  );
}

export const StripChart = memo(StripChartInner);
StripChart.displayName = "StripChart";

export { DEFAULT_TIME_SPAN_MINUTES, TIME_SPAN_OPTIONS_MINUTES };
