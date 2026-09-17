import { useState, useEffect, useCallback, useMemo, useRef } from "react";
import { Button } from "../components/Button";
import { StripChart, type StripChartConfig } from "../components/StripChart";
import { useTranslation } from "../hooks/useTranslation";
import { useLongTaskObserver } from "../hooks/useLongTaskObserver";
import { useStationTagCatalog } from "../hooks/useStationTagCatalog";
import { GridLayout, getCompactor, type Layout, type LayoutItem } from "react-grid-layout";
import "react-grid-layout/css/styles.css";
import "react-resizable/css/styles.css";
import {
  MAX_STATION_CHARTS,
  createDefaultStripChart,
  hydrateStationRealtimeTrends,
  persistStationRealtimeTrends,
  loadStationRealtimeTrends,
  exportStationRealtimeTrends,
  importStationRealtimeTrends,
  subscribeWorkspaceSync,
  flushPendingSave,
  type WorkspaceSyncStatus,
} from "../services/workspaceStore";
import {
  GRID_COLS,
  GRID_MARGIN,
  GRID_ROW_HEIGHT,
  MIN_GRID_H,
  MIN_GRID_W,
  MAX_GRID_W,
  isLayoutV3Enabled,
} from "../utils/realtimeTrendsGrid";
import { showToast } from "../utils/toast";
import { filterChartsToCatalog } from "../utils/sanitize";
import type { Tag } from "../services/tags";

const SAVE_DEBOUNCE_MS = 300;
const LEGACY_COLS = 12;
const LEGACY_ROW_HEIGHT = 40;
const LEGACY_MIN_W = 4;
const LEGACY_MIN_H = 6;

export function RealTimeTrends() {
  const { t } = useTranslation();
  useLongTaskObserver(50, "real-time-trends");
  const useV3 = isLayoutV3Enabled();
  const cols = useV3 ? GRID_COLS : LEGACY_COLS;
  const rowHeight = useV3 ? GRID_ROW_HEIGHT : LEGACY_ROW_HEIGHT;
  const minW = useV3 ? MIN_GRID_W : LEGACY_MIN_W;
  const minH = useV3 ? MIN_GRID_H : LEGACY_MIN_H;
  const maxW = useV3 ? MAX_GRID_W : LEGACY_COLS;

  const initial = loadStationRealtimeTrends();
  const [isEditMode, setIsEditMode] = useState(false);
  const [panelTitle, setPanelTitle] = useState(initial.panelTitle);
  const [layoutInteracting, setLayoutInteracting] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);
  const importRef = useRef<HTMLInputElement>(null);
  const [containerWidth, setContainerWidth] = useState(1200);
  const [stripCharts, setStripCharts] = useState<StripChartConfig[]>(() => initial.charts);
  const { tags: availableTags, loading: loadingTags } = useStationTagCatalog({
    refreshInEditMode: true,
    isEditMode,
  });
  const [syncStatus, setSyncStatus] = useState<WorkspaceSyncStatus>("ok");
  const chartsRef = useRef(stripCharts);
  const titleRef = useRef(panelTitle);
  const hydratedRef = useRef(false);
  const containerWidthRef = useRef(1200);
  const failToastAtRef = useRef(0);
  chartsRef.current = stripCharts;
  titleRef.current = panelTitle;

  const persistNow = useCallback(
    (charts: StripChartConfig[], panelTitleValue: string) => {
      chartsRef.current = charts;
      titleRef.current = panelTitleValue;
      void persistStationRealtimeTrends(charts, { panelTitle: panelTitleValue }).then((ok) => {
        if (ok) return;
        const now = Date.now();
        if (now - failToastAtRef.current < 10_000) return;
        failToastAtRef.current = now;
        showToast(t("realTimeTrends.syncSaveFailed"), "error", 8000, {
          label: t("realTimeTrends.syncRetry"),
          onClick: () => {
            void persistStationRealtimeTrends(chartsRef.current, { panelTitle: titleRef.current });
          },
        });
      });
    },
    [t]
  );

  useEffect(() => subscribeWorkspaceSync(setSyncStatus), []);

  useEffect(() => {
    if (!hydratedRef.current) {
      hydratedRef.current = true;
      return;
    }
    const timer = window.setTimeout(() => {
      persistNow(chartsRef.current, titleRef.current);
    }, SAVE_DEBOUNCE_MS);
    return () => window.clearTimeout(timer);
  }, [stripCharts, panelTitle, persistNow]);

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      const workspace = await hydrateStationRealtimeTrends();
      if (!cancelled) {
        setStripCharts(workspace.charts);
        setPanelTitle(workspace.panelTitle);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    const flush = () => {
      void flushPendingSave();
    };
    window.addEventListener("beforeunload", flush);
    window.addEventListener("pagehide", flush);
    return () => {
      window.removeEventListener("beforeunload", flush);
      window.removeEventListener("pagehide", flush);
      flush();
    };
  }, []);

  useEffect(() => {
    const WIDTH_DELTA_PX = 5;
    const updateWidth = () => {
      const target = containerRef.current;
      if (!target) return;
      const next = Math.round(target.offsetWidth);
      if (next < 1) return;
      if (Math.abs(next - containerWidthRef.current) < WIDTH_DELTA_PX) return;
      containerWidthRef.current = next;
      setContainerWidth(next);
    };
    updateWidth();
    window.addEventListener("resize", updateWidth);
    let observer: ResizeObserver | null = null;
    const node = containerRef.current;
    if (node && typeof ResizeObserver !== "undefined") {
      observer = new ResizeObserver(updateWidth);
      observer.observe(node);
    }
    return () => {
      window.removeEventListener("resize", updateWidth);
      observer?.disconnect();
    };
  }, []);

  useEffect(() => {
    if (!isEditMode || availableTags.length === 0) return;
    const catalog = new Set(availableTags.map((tag) => tag.name));
    setStripCharts((prev) => {
      const next = filterChartsToCatalog(prev, catalog);
      if (next !== prev) persistNow(next, titleRef.current);
      return next;
    });
  }, [isEditMode, availableTags, persistNow]);

  const exitEditMode = useCallback(() => {
    persistNow(chartsRef.current, titleRef.current);
    setIsEditMode(false);
  }, [persistNow]);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape" && isEditMode) {
        if (event.defaultPrevented) return;
        const overlay = document.querySelector(".multi-select-search__panel, .modal.show, .perf-alarm-modal");
        if (overlay) return;
        event.preventDefault();
        exitEditMode();
      }
    };
    window.addEventListener("keydown", onKey, true);
    return () => {
      window.removeEventListener("keydown", onKey, true);
    };
  }, [isEditMode, exitEditMode]);

  const handleAddStripChart = useCallback(() => {
    setStripCharts((prev) => {
      if (prev.length >= MAX_STATION_CHARTS) return prev;
      const maxY = prev.reduce((max, chart) => Math.max(max, chart.y + chart.h), 0);
      return [
        ...prev,
        createDefaultStripChart(t("realTimeTrends.newChartTitle", { index: prev.length + 1 }), maxY),
      ];
    });
  }, [t]);

  const handleDeleteStripChart = useCallback(
    (id: string) => {
      setStripCharts((prev) => {
        const next = prev.filter((chart) => chart.id !== id);
        persistNow(next, titleRef.current);
        return next;
      });
    },
    [persistNow]
  );

  const handleConfigChange = useCallback((updatedConfig: StripChartConfig) => {
    setStripCharts((prev) =>
      prev.map((chart) => (chart.id === updatedConfig.id ? updatedConfig : chart))
    );
  }, []);

  const commitLayout = useCallback((layout: Layout) => {
    setStripCharts((prev) => {
      let changed = false;
      const next = prev.map((chart) => {
        const layoutItem = layout.find((item) => item.i === chart.id);
        if (!layoutItem) return chart;
        if (
          layoutItem.x === chart.x &&
          layoutItem.y === chart.y &&
          layoutItem.w === chart.w &&
          layoutItem.h === chart.h
        ) {
          return chart;
        }
        changed = true;
        return {
          ...chart,
          x: layoutItem.x,
          y: layoutItem.y,
          w: layoutItem.w,
          h: layoutItem.h,
        };
      });
      return changed ? next : prev;
    });
  }, []);

  const handleDragStart = useCallback(() => setLayoutInteracting(true), []);
  const handleResizeStart = useCallback(() => setLayoutInteracting(true), []);
  const handleDragStop = useCallback(
    (layout: Layout) => {
      commitLayout(layout);
      setLayoutInteracting(false);
    },
    [commitLayout]
  );
  const handleResizeStop = useCallback(
    (layout: Layout) => {
      commitLayout(layout);
      setLayoutInteracting(false);
    },
    [commitLayout]
  );

  const gridLayout = useMemo<LayoutItem[]>(() => {
    return stripCharts.map((chart) => ({
      i: chart.id,
      x: chart.x,
      y: chart.y,
      w: chart.w,
      h: Math.max(chart.h, minH),
      minW,
      maxW,
      minH,
      static: !isEditMode,
      resizeHandles: isEditMode ? (["e", "s", "se", "sw"] as LayoutItem["resizeHandles"]) : [],
    }));
  }, [stripCharts, isEditMode, minH, minW, maxW]);

  const compactor = useMemo(() => getCompactor(null, true, false), []);
  const gridConfig = useMemo(
    () => ({
      cols,
      rowHeight,
      margin: GRID_MARGIN,
      containerPadding: [0, 0] as const,
      maxRows: Number.POSITIVE_INFINITY,
    }),
    [cols, rowHeight]
  );

  const handleExport = useCallback(() => {
    const payload = exportStationRealtimeTrends(stripCharts, { panelTitle });
    const blob = new Blob([payload], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = "realtime-trends-layout.json";
    anchor.click();
    URL.revokeObjectURL(url);
  }, [panelTitle, stripCharts]);

  const handleImportFile = useCallback(
    async (event: React.ChangeEvent<HTMLInputElement>) => {
      const file = event.target.files?.[0];
      event.target.value = "";
      if (!file) return;
      try {
        const text = await file.text();
        const imported = importStationRealtimeTrends(text);
        if (!imported) {
          showToast(t("realTimeTrends.importInvalid"), "error");
          return;
        }
        setStripCharts(imported.charts);
        setPanelTitle(imported.panelTitle);
        showToast(t("realTimeTrends.importOk"), "success");
      } catch {
        showToast(t("realTimeTrends.importInvalid"), "error");
      }
    },
    [t]
  );

  const heading = panelTitle.trim() || t("navigation.realTimeTrends");

  return (
    <div className={`rt-trends-page${isEditMode ? " rt-trends-page--editing" : ""}`}>
      <span id="rt-trends-drag-instruction" className="visually-hidden">
        {t("realTimeTrends.dragInstruction")}
      </span>
      <div className="rt-trends-toolbar sticky-top">
        <div className="d-flex justify-content-between align-items-center flex-wrap gap-2 py-2">
          <div className="d-flex align-items-center gap-2 min-w-0">
            {isEditMode ? (
              <input
                type="text"
                className="form-control form-control-sm"
                style={{ maxWidth: "18rem" }}
                value={panelTitle}
                onChange={(e) => setPanelTitle(e.target.value)}
                placeholder={t("navigation.realTimeTrends")}
                aria-label={t("realTimeTrends.panelTitle")}
              />
            ) : (
              <h3 className="card-title m-0 text-truncate">{heading}</h3>
            )}
            {syncStatus !== "ok" && (
              <span className="badge bg-warning text-dark">
                {syncStatus === "offline"
                  ? t("realTimeTrends.syncOffline")
                  : t("realTimeTrends.syncRetrying")}
              </span>
            )}
          </div>
          <div className="d-flex gap-2 align-items-center flex-wrap">
            {isEditMode ? (
              <>
                <span className="badge bg-warning text-dark">{t("realTimeTrends.editMode")}</span>
                <Button
                  variant="success"
                  className="btn-sm"
                  onClick={handleAddStripChart}
                  disabled={stripCharts.length >= MAX_STATION_CHARTS}
                  aria-label={t("realTimeTrends.addChartAria")}
                >
                  <i className="bi bi-plus-circle me-1"></i>
                  {t("realTimeTrends.addChart")}
                </Button>
                <Button variant="secondary" className="btn-sm" onClick={handleExport}>
                  {t("realTimeTrends.exportLayout")}
                </Button>
                <Button variant="secondary" className="btn-sm" onClick={() => importRef.current?.click()}>
                  {t("realTimeTrends.importLayout")}
                </Button>
                <input
                  ref={importRef}
                  type="file"
                  accept="application/json,.json"
                  className="d-none"
                  onChange={handleImportFile}
                />
                <Button variant="primary" className="btn-sm" onClick={exitEditMode}>
                  {t("realTimeTrends.closeEdit")}
                </Button>
              </>
            ) : (
              <Button
                variant="secondary"
                className="btn-sm"
                onClick={() => setIsEditMode(true)}
                aria-label={t("realTimeTrends.editPanel")}
              >
                <i className="bi bi-pencil me-1"></i>
                {t("realTimeTrends.editPanel")}
              </Button>
            )}
          </div>
        </div>
      </div>
      {syncStatus !== "ok" && (
        <div className="alert alert-warning py-2 small mb-2" role="status">
          {t("realTimeTrends.syncBanner")}
        </div>
      )}
      <div ref={containerRef} className="rt-trends-width-probe" aria-hidden="true" />
      <div
        className={`rt-trends-layout${isEditMode ? " rt-trends-layout--editing" : ""}`}
        style={{ position: "relative", width: "100%", minHeight: "300px" }}
      >
      {stripCharts.length === 0 ? (
        <div className="text-center py-5">
          <i className="bi bi-graph-up" style={{ fontSize: "4rem", color: "#6c757d" }}></i>
          <h4 className="mt-3 text-muted">{heading}</h4>
          <p className="text-muted">
            {isEditMode ? t("realTimeTrends.emptyEdit") : t("realTimeTrends.emptyProduction")}
          </p>
        </div>
      ) : (
          <GridLayout
            className="layout"
            width={containerWidth}
            layout={gridLayout}
            gridConfig={gridConfig}
            autoSize
            dragConfig={{
              enabled: isEditMode,
              bounded: false,
              handle: ".rt-card-drag-handle",
              cancel: "button,a,input,select,textarea,.rt-stripchart-picker",
              threshold: 3,
            }}
            resizeConfig={{
              enabled: isEditMode,
              handles: isEditMode ? ["e", "s", "se", "sw"] : [],
            }}
            compactor={compactor}
            onDragStart={handleDragStart}
            onDragStop={handleDragStop}
            onResizeStart={handleResizeStart}
            onResizeStop={handleResizeStop}
          >
            {stripCharts.map((chart) => (
              <div
                key={chart.id}
                data-chart-id={chart.id}
                data-grid={{
                  i: chart.id,
                  x: chart.x,
                  y: chart.y,
                  w: chart.w,
                  h: Math.max(chart.h, minH),
                  minW,
                  maxW,
                  minH,
                }}
                className="rt-trends-grid-item"
                style={{
                  height: "100%",
                  width: "100%",
                  overflow: "hidden",
                  display: "flex",
                  flexDirection: "column",
                  minHeight: 0,
                }}
              >
                <StripChart
                  config={chart}
                  isEditMode={isEditMode}
                  layoutInteracting={layoutInteracting}
                  availableTags={availableTags}
                  loadingTags={loadingTags}
                  onConfigChange={handleConfigChange}
                  onDelete={() => handleDeleteStripChart(chart.id)}
                />
              </div>
            ))}
          </GridLayout>
      )}
      </div>
    </div>
  );
}
