import { useState, useEffect, useCallback, useMemo, useRef } from "react";
import { Card } from "../components/Card";
import { Button } from "../components/Button";
import { StripChart, type StripChartConfig } from "../components/StripChart";
import { useTranslation } from "../hooks/useTranslation";
import { ResponsiveGridLayout, Layout as GridLayoutType } from "react-grid-layout";
import "react-grid-layout/css/styles.css";
import "react-resizable/css/styles.css";

const STORAGE_KEY = "realTimeTrends_layout";
const GRID_COLS = 12;
const GRID_ROW_HEIGHT = 50;

export function RealTimeTrends() {
  const { t } = useTranslation();
  const [isEditMode, setIsEditMode] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);
  const [containerWidth, setContainerWidth] = useState(1200);
  const [stripCharts, setStripCharts] = useState<StripChartConfig[]>(() => {
    const saved = localStorage.getItem(STORAGE_KEY);
    if (saved) {
      try {
        return JSON.parse(saved);
      } catch {
        return [];
      }
    }
    return [];
  });

  // Persistir layout en localStorage (también cuando está vacío)
  useEffect(() => {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(stripCharts));
  }, [stripCharts]);

  // Cargar layout guardado al montar
  useEffect(() => {
    const saved = localStorage.getItem(STORAGE_KEY);
    if (saved) {
      try {
        const parsed = JSON.parse(saved);
        if (Array.isArray(parsed) && parsed.length > 0) {
          setStripCharts(parsed);
        }
      } catch (e) {
        console.error("Error loading saved layout:", e);
      }
    }
  }, []);

  // Medir ancho del contenedor para ResponsiveGridLayout
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

  // Crear nuevo StripChart
  const handleAddStripChart = useCallback(() => {
    const newChart: StripChartConfig = {
      id: `stripchart-${Date.now()}`,
      title: `Gráfico ${stripCharts.length + 1}`,
      tagNames: [],
      bufferSize: 100,
      x: 0,
      y: 0,
      w: 6,
      h: 6,
    };

    // Calcular posición Y para evitar solapamiento
    const maxY = stripCharts.reduce((max, chart) => Math.max(max, chart.y + chart.h), 0);
    newChart.y = maxY;

    setStripCharts((prev) => [...prev, newChart]);
  }, [stripCharts]);

  // Eliminar StripChart
  const handleDeleteStripChart = useCallback((id: string) => {
    setStripCharts((prev) => prev.filter((chart) => chart.id !== id));
  }, []);

  // Actualizar configuración de un StripChart
  const handleConfigChange = useCallback((updatedConfig: StripChartConfig) => {
    setStripCharts((prev) =>
      prev.map((chart) => (chart.id === updatedConfig.id ? updatedConfig : chart))
    );
  }, []);

  // Manejar cambios en el layout (drag and drop, resize)
  const handleLayoutChange = useCallback((layout: GridLayoutType[]) => {
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
  }, []);

  // Convertir StripChartConfig a GridLayout
  const gridLayout = useMemo<GridLayoutType[]>(() => {
    return stripCharts.map((chart) => ({
      i: chart.id,
      x: chart.x,
      y: chart.y,
      w: chart.w,
      h: chart.h,
      minW: 4, // Mínimo de ancho (4 columnas)
      maxW: 12, // Máximo de ancho (12 columnas)
      minH: 1, // Mínimo de altura muy bajo (casi sin restricción)
      resizeHandles: isEditMode ? ["e", "s", "se", "sw"] : ["se"],
    } as GridLayoutType & { resizeHandles?: string[] }));
  }, [stripCharts, isEditMode]);

  return (
    <div className="row">
      <div className="col-12">
        <Card
          title={
            <div className="d-flex justify-content-between align-items-center w-100">
              <h3 className="card-title m-0">{t("navigation.realTimeTrends")}</h3>
              <div className="d-flex gap-2 align-items-center">
                <div className="form-check form-switch">
                  <input
                    className="form-check-input"
                    type="checkbox"
                    role="switch"
                    id="editModeSwitch"
                    checked={isEditMode}
                    onChange={(e) => setIsEditMode(e.target.checked)}
                  />
                  <label className="form-check-label" htmlFor="editModeSwitch">
                    {isEditMode ? "Modo Edición" : "Modo Producción"}
                  </label>
                </div>
                {isEditMode && (
                  <Button variant="success" className="btn-sm" onClick={handleAddStripChart}>
                    <i className="bi bi-plus-circle me-1"></i>
                    Agregar Gráfico
                  </Button>
                )}
              </div>
            </div>
          }
        >
          {stripCharts.length === 0 ? (
            <div className="text-center py-5">
              <i className="bi bi-graph-up" style={{ fontSize: "4rem", color: "#6c757d" }}></i>
              <h4 className="mt-3 text-muted">{t("navigation.realTimeTrends")}</h4>
              <p className="text-muted">
                {isEditMode
                  ? "Haga clic en 'Agregar Gráfico' para crear su primer gráfico en tiempo real"
                  : "No hay gráficos configurados. Active el modo edición para crear gráficos."}
              </p>
            </div>
          ) : (
            <div ref={containerRef} style={{ position: "relative", width: "100%", minHeight: "500px" }}>
              <ResponsiveGridLayout
                className="layout"
                layouts={{ lg: gridLayout }}
                cols={{ lg: GRID_COLS, md: GRID_COLS, sm: GRID_COLS, xs: GRID_COLS, xxs: GRID_COLS }}
                rowHeight={GRID_ROW_HEIGHT}
                width={containerWidth}
                onLayoutChange={(layout, layouts) => {
                  if (layouts && layouts.lg) {
                    handleLayoutChange(layouts.lg);
                  } else {
                    handleLayoutChange(layout);
                  }
                }}
                isDraggable={isEditMode}
                isResizable={isEditMode}
                draggableHandle=".drag-handle"
                preventCollision={false}
                compactType={null}
                margin={[10, 10]}
                containerPadding={[0, 0]}
                breakpoints={{ lg: 1200, md: 996, sm: 768, xs: 480, xxs: 0 }}
                resizeHandles={isEditMode ? ['e', 's', 'se', 'sw'] : ['se']}
              >
                {stripCharts.map((chart) => (
                  <div
                    key={chart.id}
                    data-chart-id={chart.id}
                    style={{ height: "100%", width: "100%", overflow: "visible", display: "flex", flexDirection: "column" }}
                  >
                    <StripChart
                      config={chart}
                      isEditMode={isEditMode}
                      onConfigChange={handleConfigChange}
                      onDelete={() => handleDeleteStripChart(chart.id)}
                    />
                  </div>
                ))}
              </ResponsiveGridLayout>
            </div>
          )}
        </Card>
      </div>
    </div>
  );
}
