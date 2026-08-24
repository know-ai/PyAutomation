import { useState, useEffect, useCallback, useMemo, useRef } from "react";
import { Button } from "../components/Button";
import { StripChart, DEFAULT_TIME_SPAN_MINUTES, type StripChartConfig } from "../components/StripChart";
import { useTranslation } from "../hooks/useTranslation";
import { useLongTaskObserver } from "../hooks/useLongTaskObserver";
import { ResponsiveGridLayout, Layout as GridLayoutType } from "react-grid-layout";
import "react-grid-layout/css/styles.css";
import "react-resizable/css/styles.css";
import {
  MAX_STATION_CHARTS,
  createStationChartId,
  hydrateStationRealtimeTrends,
  persistStationRealtimeTrends,
  loadStationRealtimeTrends,
} from "../services/workspaceStore";

const GRID_COLS = 12;
const GRID_ROW_HEIGHT = 40;
const MIN_STRIPCHART_ROWS = 6;
const SAVE_DEBOUNCE_MS = 300;

export function RealTimeTrends() {
  const { t } = useTranslation();
  useLongTaskObserver(50, "real-time-trends");
  const [isEditMode, setIsEditMode] = useState(false);
  const [showThresholds, setShowThresholds] = useState(true);
  const containerRef = useRef<HTMLDivElement>(null);
  const [containerWidth, setContainerWidth] = useState(1200);
  const [stripCharts, setStripCharts] = useState<StripChartConfig[]>(
    () => loadStationRealtimeTrends().charts
  );
  const chartsRef = useRef(stripCharts);
  const hydratedRef = useRef(false);
  chartsRef.current = stripCharts;

  useEffect(() => {
    if (!hydratedRef.current) {
      hydratedRef.current = true;
      return;
    }
    const timer = window.setTimeout(() => {
      void persistStationRealtimeTrends(chartsRef.current);
    }, SAVE_DEBOUNCE_MS);
    return () => window.clearTimeout(timer);
  }, [stripCharts]);

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      const charts = await hydrateStationRealtimeTrends();
      if (!cancelled) {
        setStripCharts(charts);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    const flush = () => {
      void persistStationRealtimeTrends(chartsRef.current);
    };
    window.addEventListener("beforeunload", flush);
    return () => {
      window.removeEventListener("beforeunload", flush);
      flush();
    };
  }, []);

  useEffect(() => {
    const updateWidth = () => {
      if (containerRef.current) {
        setContainerWidth(containerRef.current.offsetWidth);
      }
    };
    updateWidth();
    window.addEventListener("resize", updateWidth);
    return () => window.removeEventListener("resize", updateWidth);
  }, []);

  const handleAddStripChart = useCallback(() => {
    setStripCharts((prev) => {
      if (prev.length >= MAX_STATION_CHARTS) return prev;
      const maxY = prev.reduce((max, chart) => Math.max(max, chart.y + chart.h), 0);
      const next: StripChartConfig = {
        id: createStationChartId(),
        title: t("realTimeTrends.newChartTitle", { index: prev.length + 1 }),
        tagNames: [],
        timeSpanMinutes: DEFAULT_TIME_SPAN_MINUTES,
        x: 0,
        y: maxY,
        w: 6,
        h: MIN_STRIPCHART_ROWS,
      };
      return [...prev, next];
    });
  }, [t]);

  const handleDeleteStripChart = useCallback((id: string) => {
    setStripCharts((prev) => prev.filter((chart) => chart.id !== id));
  }, []);

  const handleConfigChange = useCallback((updatedConfig: StripChartConfig) => {
    setStripCharts((prev) =>
      prev.map((chart) => (chart.id === updatedConfig.id ? updatedConfig : chart))
    );
  }, []);

  const handleLayoutChange = useCallback(
    (layout: GridLayoutType[]) => {
      if (!isEditMode) return;
      setStripCharts((prev) =>
        prev.map((chart) => {
          const layoutItem = layout.find((item) => item.i === chart.id);
          if (layoutItem) {
            return {
              ...chart,
              x: layoutItem.x,
              y: layoutItem.y,
              w: layoutItem.w,
              h: layoutItem.h,
            };
          }
          return chart;
        })
      );
    },
    [isEditMode]
  );

  const gridLayout = useMemo<GridLayoutType[]>(() => {
    return stripCharts.map((chart) => ({
      i: chart.id,
      x: chart.x,
      y: chart.y,
      w: chart.w,
      h: Math.max(chart.h, MIN_STRIPCHART_ROWS),
      minW: 4,
      maxW: 12,
      minH: MIN_STRIPCHART_ROWS,
      static: !isEditMode,
      resizeHandles: isEditMode ? ["e", "s", "se", "sw"] : [],
    } as GridLayoutType & { resizeHandles?: string[] }));
  }, [stripCharts, isEditMode]);

  const handleToggleEditMode = useCallback(() => {
    setIsEditMode((prev) => !prev);
  }, []);

  return (
    <div className="row" onDoubleClick={handleToggleEditMode} style={{ cursor: "default" }}>
      <div className="col-12">
        {isEditMode && (
          <div className="d-flex justify-content-between align-items-center mb-3">
            <div className="d-flex align-items-center gap-2">
              <h3 className="card-title m-0">{t("navigation.realTimeTrends")}</h3>
            </div>
            <div className="d-flex gap-2 align-items-center">
              <div className="form-check form-switch mb-0">
                <input
                  className="form-check-input"
                  type="checkbox"
                  role="switch"
                  id="realtime-trends-show-thresholds"
                  checked={showThresholds}
                  onChange={(e) => setShowThresholds(e.target.checked)}
                />
                <label className="form-check-label small" htmlFor="realtime-trends-show-thresholds">
                  {t("realTimeTrends.showThresholds")}
                </label>
              </div>
              <span className="badge bg-warning text-dark">{t("realTimeTrends.editMode")}</span>
              <Button
                variant="success"
                className="btn-sm"
                onClick={handleAddStripChart}
                disabled={stripCharts.length >= MAX_STATION_CHARTS}
              >
                <i className="bi bi-plus-circle me-1"></i>
                {t("realTimeTrends.addChart")}
              </Button>
            </div>
          </div>
        )}
        {stripCharts.length === 0 ? (
          <div className="text-center py-5">
            <i className="bi bi-graph-up" style={{ fontSize: "4rem", color: "#6c757d" }}></i>
            <h4 className="mt-3 text-muted">{t("navigation.realTimeTrends")}</h4>
            <p className="text-muted">
              {isEditMode
                ? t("realTimeTrends.emptyEdit")
                : t("realTimeTrends.emptyProduction")}
            </p>
          </div>
        ) : (
          <div
            ref={containerRef}
            style={{ position: "relative", width: "100%", minHeight: "300px" }}
          >
            <ResponsiveGridLayout
              className="layout"
              layouts={{ lg: gridLayout }}
              cols={{ lg: GRID_COLS }}
              rowHeight={GRID_ROW_HEIGHT}
              width={containerWidth}
              onLayoutChange={(layout) =>
                handleLayoutChange(layout as unknown as GridLayoutType[])
              }
              isDraggable={isEditMode}
              isResizable={isEditMode}
              draggableHandle={isEditMode ? ".drag-handle" : undefined}
              preventCollision={false}
              compactType={null}
              margin={[10, 10]}
              containerPadding={[0, 0]}
              breakpoints={{ lg: 0 }}
              resizeHandles={isEditMode ? ["e", "s", "se", "sw"] : []}
            >
              {stripCharts.map((chart) => (
                <div
                  key={chart.id}
                  data-chart-id={chart.id}
                  style={{
                    height: "100%",
                    width: "100%",
                    overflow: "visible",
                    display: "flex",
                    flexDirection: "column",
                  }}
                >
                  <StripChart
                    config={chart}
                    isEditMode={isEditMode}
                    showThresholds={isEditMode && showThresholds}
                    onConfigChange={handleConfigChange}
                    onDelete={() => handleDeleteStripChart(chart.id)}
                  />
                </div>
              ))}
            </ResponsiveGridLayout>
          </div>
        )}
      </div>
    </div>
  );
}
