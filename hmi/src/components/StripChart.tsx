import { useState, useEffect, useMemo, useRef, useCallback, memo } from "react";
import { Card } from "./Card";
import { Button } from "./Button";
import { OpsConfirmModal } from "./OpsConfirmModal";
import { MultiSelectSearch, type MultiSelectOption } from "./MultiSelectSearch";
import Plot from "react-plotly.js";
import type { Data, Layout } from "plotly.js";
import { useTheme } from "../hooks/useTheme";
import { useAppSelector } from "../hooks/useAppSelector";
import { useAppDispatch } from "../hooks/useAppDispatch";
import { useTranslation } from "../hooks/useTranslation";
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
import { useDisplayTimezone } from "../hooks/useDisplayTimezone";
import { usePlotlyResize } from "../hooks/usePlotlyResize";
import { toDisplayDate } from "../utils/timezone";
import { resolveTagDisplayLabel } from "../utils/tagDisplayLabel";
import { isFilteredDerivativeName, sourceTagName } from "../utils/filteredTags";
import { isDisplayableThreshold, resolveTagThreshold } from "../utils/tagThreshold";
import { QualityBadge } from "./QualityBadge";
import type { Tag } from "../services/tags";

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
  showThresholds?: boolean;
  x: number;
  y: number;
  w: number;
  h: number;
}

interface StripChartProps {
  config: StripChartConfig;
  isEditMode: boolean;
  layoutInteracting?: boolean;
  availableTags?: Tag[];
  loadingTags?: boolean;
  onConfigChange: (config: StripChartConfig) => void;
  onDelete: () => void;
}

function StripChartInner({
  config,
  isEditMode,
  layoutInteracting = false,
  availableTags = [],
  loadingTags = false,
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
  const showThresholds = config.showThresholds !== false;
  const plotBoxRef = useRef<HTMLDivElement>(null);
  const plotSize = usePlotlyResize(plotBoxRef, layoutInteracting);
  const [confirmDelete, setConfirmDelete] = useState(false);

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

  useEffect(() => {
    const names = config.tagNames.filter(Boolean);
    names.forEach((name) => dispatch(subscribeTagHistory(name)));
    return () => {
      names.forEach((name) => dispatch(unsubscribeTagHistory(name)));
    };
  }, [dispatch, tagNamesKey]);

  const catalogNames = useMemo(
    () => new Set(availableTags.map((tag) => tag.name)),
    [availableTags]
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

  const missingTags = useMemo(() => {
    if (availableTags.length === 0) return [] as string[];
    return config.tagNames.filter((name) => !catalogNames.has(name) && !catalogNames.has(sourceTagName(name)));
  }, [availableTags.length, catalogNames, config.tagNames]);

  const tagOptions = useMemo<MultiSelectOption[]>(() => {
    return availableTags.map((tag) => {
      const unit = tag.display_unit || tag.unit || "—";
      return {
        value: tag.name,
        label: resolveTagDisplayLabel(tag, tag.name),
        description: `${unit} · ${tag.name}`,
      };
    });
  }, [availableTags]);

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

    const width = plotSize.width > 0 ? plotSize.width : undefined;
    const height = plotSize.height > 0 ? plotSize.height : undefined;

    const layout: Partial<Layout> = {
      autosize: false,
      width,
      height,
      uirevision: config.id,
      datarevision: historyRevision(prunedHistories, timeSpanMinutes, nowMs),
      margin: { l: 56, r: unitOrder.length > 1 ? 56 : 16, t: 28, b: 40 },
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
        orientation: "h",
        x: 0,
        y: 1,
        xanchor: "left",
        yanchor: "top",
        bgcolor: "rgba(0,0,0,0)",
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
    plotSize.width,
    plotSize.height,
  ]);

  const applyTagNames = (nextNames: string[]) => {
    const accepted: string[] = [];
    const units = new Set<string>();
    let warnedSecond = false;
    let blockedExtra = false;
    for (const name of nextNames) {
      const unit = getTagUnit(name);
      if (!units.has(unit) && units.size >= 2) {
        if (!blockedExtra) {
          showToast(t("stripChart.maxUnitsPerChart"), "warning");
          blockedExtra = true;
        }
        continue;
      }
      if (!units.has(unit) && units.size === 1 && !warnedSecond) {
        showToast(t("stripChart.secondUnitWarning", { unit }), "info");
        warnedSecond = true;
      }
      units.add(unit);
      accepted.push(name);
    }
    onConfigChange({ ...config, tagNames: accepted });
  };

  const handleTimeSpanChange = (raw: string) => {
    onConfigChange({
      ...config,
      timeSpanMinutes: normalizeTimeSpanMinutes(Number(raw)),
    });
  };

  const handleTitleChange = (newTitle: string) => {
    onConfigChange({ ...config, title: newTitle });
  };

  const plotReady = plotSize.width > 8 && plotSize.height > 8;

  return (
    <div className="rt-stripchart" style={{ height: "100%", width: "100%", display: "flex", flexDirection: "column" }}>
      {isEditMode && (
        <div
          className="rt-card-drag-handle"
          role="button"
          tabIndex={0}
          aria-label={t("realTimeTrends.dragHandle")}
          aria-describedby="rt-trends-drag-instruction"
        >
          <i className="bi bi-grip-horizontal" aria-hidden="true" />
        </div>
      )}
      <Card
        className="overflow-hidden rt-stripchart-card"
        style={{ height: "100%", width: "100%", display: "flex", flexDirection: "column", minHeight: 0 }}
        headerClassName="py-1 px-2"
        bodyClassName="p-0"
        title={
          <div className="d-flex justify-content-between align-items-center w-100 gap-2">
            <div className="d-flex align-items-center gap-2 min-w-0">
              {isEditMode ? (
                <input
                  type="text"
                  className="form-control form-control-sm"
                  value={config.title}
                  onChange={(e) => handleTitleChange(e.target.value)}
                  onMouseDown={(e) => e.stopPropagation()}
                  style={{ width: "auto", minWidth: "150px", maxWidth: "300px" }}
                  placeholder={t("stripChart.titlePlaceholder")}
                />
              ) : (
                <span className="d-inline-flex align-items-center gap-2 flex-wrap">
                  <span>{config.title || t("stripChart.defaultTitle")}</span>
                  {config.tagNames.map((tagName) => {
                    const live = liveTags[tagName];
                    const missing = missingTags.includes(tagName);
                    return (
                      <span key={tagName} className="d-inline-flex align-items-center gap-1">
                        <span className="small text-muted">{getTagLabel(tagName)}</span>
                        {missing ? (
                          <span className="badge bg-warning text-dark">{t("stripChart.tagUnavailable")}</span>
                        ) : (
                          <QualityBadge
                            quality={live?.quality}
                            qualityLabel={live?.quality_label}
                            substatus={live?.quality_substatus}
                            stale={Boolean(live?.stale)}
                            staleAgeMs={typeof live?.stale_age_ms === "number" ? live.stale_age_ms : null}
                          />
                        )}
                      </span>
                    );
                  })}
                </span>
              )}
            </div>
            {isEditMode && (
              <div className="d-flex gap-2 align-items-center flex-shrink-0" onMouseDown={(e) => e.stopPropagation()}>
                {missingTags.length > 0 && (
                  <span className="badge bg-warning text-dark">{t("stripChart.tagUnavailable")}</span>
                )}
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
                <div className="rt-stripchart-picker d-flex align-items-center gap-1">
                  {loadingTags && (
                    <span className="spinner-border spinner-border-sm" role="status" aria-label={t("stripChart.loadingTags")} />
                  )}
                  <MultiSelectSearch
                    options={tagOptions}
                    selected={config.tagNames}
                    onChange={applyTagNames}
                    disabled={loadingTags}
                    placeholder={
                      loadingTags
                        ? t("stripChart.loadingTags")
                        : t("stripChart.tagsWithCount", { count: config.tagNames.length })
                    }
                    searchPlaceholder={t("stripChart.searchPlaceholder")}
                    emptyText={t("stripChart.noTagsAvailable")}
                    selectedCountLabel={(count) => t("stripChart.tagsWithCount", { count })}
                  />
                </div>
                <Button
                  variant="danger"
                  className="btn-sm"
                  onClick={() => setConfirmDelete(true)}
                  title={t("stripChart.deleteChart")}
                  aria-label={t("stripChart.deleteChart")}
                >
                  <i className="bi bi-trash"></i>
                </Button>
              </div>
            )}
          </div>
        }
      >
        <div
          ref={plotBoxRef}
          className="rt-stripchart-plotbox"
          style={{ width: "100%", flex: 1, minHeight: 0, position: "relative", overflow: "hidden" }}
        >
          {config.tagNames.length === 0 ? (
            <div className="text-center py-5 text-muted" style={{ height: "100%", display: "flex", flexDirection: "column", justifyContent: "center" }}>
              <i className="bi bi-graph-up" style={{ fontSize: "3rem" }}></i>
              <p className="mt-3">{t("stripChart.emptyState")}</p>
            </div>
          ) : !hasAnyPointsInSpan ? (
            <div className="rt-stripchart-skeleton" aria-busy="true" aria-label={t("stripChart.loadingData")}>
              <div className="rt-stripchart-skeleton-bar" />
              <div className="rt-stripchart-skeleton-bar" />
              <div className="rt-stripchart-skeleton-bar" />
            </div>
          ) : plotReady ? (
            <Plot
              data={plotData.data}
              layout={plotData.layout}
              revision={String((plotData.layout as { datarevision?: string }).datarevision || "")}
              style={{ width: "100%", height: "100%" }}
              config={{
                displayModeBar: isEditMode,
                modeBarButtonsToRemove: ["lasso2d", "select2d"],
                displaylogo: false,
                responsive: false,
              }}
              useResizeHandler={false}
            />
          ) : null}
        </div>
      </Card>
      <OpsConfirmModal
        open={confirmDelete}
        danger
        title={t("stripChart.deleteChart")}
        body={t("stripChart.confirmDelete", { title: config.title || t("stripChart.defaultTitle") })}
        confirmLabel={t("common.delete")}
        onCancel={() => setConfirmDelete(false)}
        onConfirm={() => {
          setConfirmDelete(false);
          onDelete();
        }}
      />
    </div>
  );
}

export const StripChart = memo(StripChartInner);
StripChart.displayName = "StripChart";

export { DEFAULT_TIME_SPAN_MINUTES, TIME_SPAN_OPTIONS_MINUTES };
