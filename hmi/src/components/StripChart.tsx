import { useState, useEffect, useMemo, useRef, useCallback } from "react";
import { Card } from "./Card";
import { Button } from "./Button";
import Plot from "react-plotly.js";
import type { Data, Layout } from "plotly.js";
import { useTheme } from "../hooks/useTheme";
import { useAppSelector } from "../hooks/useAppSelector";
import { getTags, type Tag } from "../services/tags";
import { showToast } from "../utils/toast";

export interface StripChartConfig {
  id: string;
  title: string;
  tagNames: string[];
  bufferSize: number; // Tamaño del buffer en número de puntos
  x: number; // Posición en grid
  y: number;
  w: number; // Ancho en columnas (4-12)
  h: number; // Alto en unidades de grid
}

interface StripChartProps {
  config: StripChartConfig;
  isEditMode: boolean;
  onConfigChange: (config: StripChartConfig) => void;
  onDelete: () => void;
}

export function StripChart({ config, isEditMode, onConfigChange, onDelete }: StripChartProps) {
  const { mode } = useTheme();
  const tagValues = useAppSelector((state) => state.tags.tagValues);
  const [showTagConfig, setShowTagConfig] = useState(false);
  const [availableTags, setAvailableTags] = useState<Tag[]>([]);
  const [tagSearch, setTagSearch] = useState("");
  const [loadingTags, setLoadingTags] = useState(false);
  const [bufferVersion, setBufferVersion] = useState(0);
  const tagConfigRef = useRef<HTMLDivElement>(null);
  const dataBufferRef = useRef<Map<string, Array<{ x: Date; y: number }>>>(new Map());
  const pendingRenderRef = useRef(false);

  // Cargar tags disponibles
  useEffect(() => {
    const loadTags = async () => {
      setLoadingTags(true);
      try {
        const response = await getTags(1, 1000);
        setAvailableTags(response.data || []);
      } catch (err: any) {
        console.error("Error loading tags:", err);
        showToast("Error al cargar los tags", "error");
      } finally {
        setLoadingTags(false);
      }
    };
    loadTags();
  }, []);

  // Cerrar dropdown al hacer click fuera
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (tagConfigRef.current && !tagConfigRef.current.contains(event.target as Node)) {
        setShowTagConfig(false);
      }
    };

    if (showTagConfig) {
      document.addEventListener("mousedown", handleClickOutside);
    }

    return () => {
      document.removeEventListener("mousedown", handleClickOutside);
    };
  }, [showTagConfig]);

  // Filtrar tags por búsqueda
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

  // Actualizar buffer con datos en tiempo real (no disparar render inmediato)
  useEffect(() => {
    const getRealTimeTag = (tagName: string) => {
      return (
        tagValues[tagName] ||
        tagValues[tagName.toUpperCase()] ||
        tagValues[tagName.toLowerCase()]
      );
    };

    config.tagNames.forEach((tagName) => {
      const realTimeTag = getRealTimeTag(tagName);
      if (realTimeTag && realTimeTag.value !== undefined && realTimeTag.value !== null) {
        const buffer = dataBufferRef.current.get(tagName) || [];
        const newPoint = {
          x: new Date(),
          y: typeof realTimeTag.value === "boolean" ? (realTimeTag.value ? 1 : 0) : Number(realTimeTag.value),
        };

        // Agregar nuevo punto y mantener solo los últimos bufferSize puntos
        const updatedBuffer = [...buffer, newPoint].slice(-config.bufferSize);
        dataBufferRef.current.set(tagName, updatedBuffer);
        pendingRenderRef.current = true;
      }
    });
  }, [tagValues, config.tagNames, config.bufferSize]);

  // Búfer de render: aplicar cambios cada 1s como en tablas
  useEffect(() => {
    const id = setInterval(() => {
      if (pendingRenderRef.current) {
        pendingRenderRef.current = false;
        setBufferVersion((prev) => prev + 1);
      }
    }, 1000);
    return () => clearInterval(id);
  }, []);

  const getTagUnit = useCallback(
    (tagName: string) => {
      const tag = availableTags.find((t) => t.name === tagName);
      return tag?.display_unit || tag?.unit || "—";
    },
    [availableTags]
  );

  // Preparar datos para Plotly (soporta hasta 2 unidades distintas -> dos ejes Y)
  const plotData = useMemo(() => {
    if (config.tagNames.length === 0) {
      return { data: [], layout: {} };
    }

    const colorPalette = [
      "#1f77b4", "#ff7f0e", "#2ca02c", "#d62728", "#9467bd",
      "#8c564b", "#e377c2", "#7f7f7f", "#bcbd22", "#17becf",
    ];

    // Orden de unidades según aparición de los tags seleccionados
    const unitOrder: string[] = [];
    config.tagNames.forEach((tagName) => {
      const unit = getTagUnit(tagName);
      if (!unitOrder.includes(unit)) unitOrder.push(unit);
    });

    const unitAxis: Record<string, string> = {};
    unitOrder.forEach((unit, idx) => {
      unitAxis[unit] = idx === 0 ? "y" : "y2";
    });

    const traces: Data[] = config.tagNames.map((tagName, index) => {
      const buffer = dataBufferRef.current.get(tagName) || [];
      const tag = availableTags.find((t) => t.name === tagName);
      const unit = getTagUnit(tagName);
      return {
        x: buffer.map((p) => p.x),
        y: buffer.map((p) => p.y),
        type: "scatter",
        mode: "lines",
        name: tag?.display_name || tagName,
        line: { color: colorPalette[index % colorPalette.length], width: 2 },
        yaxis: unitAxis[unit] || "y",
      } as Data;
    });

    // Color de los ejes basado en el primer trazo de cada unidad
    const axisColors: Record<string, string> = {};
    traces.forEach((t) => {
      const axis = (t as any).yaxis || "y";
      if (!axisColors[axis]) {
        axisColors[axis] = (t as any).line?.color || "#6c757d";
      }
    });

    const layout: Partial<Layout> = {
      title: config.title || "Strip Chart",
      autosize: true,
      margin: { l: 60, r: unitOrder.length > 1 ? 60 : 20, t: 40, b: 40 },
      paper_bgcolor: mode === "dark" ? "#212529" : "#ffffff",
      plot_bgcolor: mode === "dark" ? "#2c3034" : "#f8f9fa",
      font: { color: mode === "dark" ? "#ffffff" : "#212529" },
      xaxis: {
        title: "Tiempo",
        color: mode === "dark" ? "#ffffff" : "#212529",
        gridcolor: mode === "dark" ? "#495057" : "#dee2e6",
      },
      yaxis: {
        title: unitOrder[0] || "Valor",
        color: axisColors["y"] || (mode === "dark" ? "#ffffff" : "#212529"),
        gridcolor: mode === "dark" ? "#495057" : "#dee2e6",
      },
      showlegend: config.tagNames.length > 1,
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

    return { data: traces, layout };
  }, [config.tagNames, config.title, config.bufferSize, mode, availableTags, getTagUnit, bufferVersion]);

  // Máximo 2 unidades distintas; número de tags ilimitado mientras no se supere ese tope de unidades
  const handleTagToggle = (tagName: string) => {
    const isSelected = config.tagNames.includes(tagName);
    const unit = getTagUnit(tagName);

    // Unidades actuales
    const currentUnits = new Set(config.tagNames.map(getTagUnit));
    const wouldAddNewUnit = !isSelected && !currentUnits.has(unit);

    if (wouldAddNewUnit && currentUnits.size >= 2) {
      showToast("Máximo 2 unidades por gráfico", "warning");
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

  const handleBufferSizeChange = (newSize: number) => {
    if (newSize >= 10 && newSize <= 10000) {
      onConfigChange({
        ...config,
        bufferSize: newSize,
      });
    }
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
        style={{ height: "100%", width: "100%", display: "flex", flexDirection: "column" }}
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
                  placeholder="Título del gráfico"
                  onClick={(e) => e.stopPropagation()}
                />
              ) : (
                <span>{config.title || "Strip Chart"}</span>
              )}
            </div>
            <div className="d-flex gap-2" onClick={(e) => e.stopPropagation()}>
              {isEditMode && (
                <>
                  <Button
                    variant="primary"
                    className="btn-sm"
                    onClick={() => setShowTagConfig(!showTagConfig)}
                    title="Configurar tags"
                  >
                    <i className="bi bi-tags me-1"></i>
                    Tags ({config.tagNames.length})
                  </Button>
                  <Button
                    variant="danger"
                    className="btn-sm"
                    onClick={onDelete}
                    title="Eliminar gráfico"
                  >
                    <i className="bi bi-trash"></i>
                  </Button>
                </>
              )}
            </div>
          </div>
        }
      >
        {/* Configuración de tags (dropdown) */}
        {showTagConfig && isEditMode && (
          <div
            ref={tagConfigRef}
            className="position-absolute bg-body border rounded shadow-lg p-3"
            style={{
              zIndex: 10000,
              top: "100%",
              right: 0,
              minWidth: "300px",
              maxHeight: "400px",
              overflowY: "auto",
            }}
            onClick={(e) => e.stopPropagation()}
          >
            <div className="mb-2">
              <label className="form-label small">Buscar tag:</label>
              <input
                type="text"
                className="form-control form-control-sm"
                value={tagSearch}
                onChange={(e) => setTagSearch(e.target.value)}
                placeholder="Buscar..."
              />
            </div>
            <div className="mb-2">
              <label className="form-label small">Buffer size (puntos):</label>
              <input
                type="number"
                className="form-control form-control-sm"
                value={config.bufferSize}
                onChange={(e) => handleBufferSizeChange(Number(e.target.value))}
                min={10}
                max={10000}
                step={10}
              />
            </div>
            <div className="mb-2">
              <label className="form-label small d-flex justify-content-between align-items-center">
                <span>Tags seleccionados:</span>
                <span className="badge bg-secondary">
                  {Array.from(new Set(config.tagNames.map(getTagUnit))).length}/2 unidades
                </span>
              </label>
              <div className="d-flex flex-wrap gap-1">
                {config.tagNames.map((tagName) => {
                  const tag = availableTags.find((t) => t.name === tagName);
                  return (
                    <span key={tagName} className="badge bg-primary">
                      {tag?.display_name || tagName}
                      <button
                        type="button"
                        className="btn-close btn-close-white ms-1"
                        style={{ fontSize: "0.6rem" }}
                        onClick={() => handleTagToggle(tagName)}
                        aria-label="Remove"
                      ></button>
                    </span>
                  );
                })}
              </div>
            </div>
            <div>
              <label className="form-label small">Tags disponibles:</label>
              {loadingTags ? (
                <div className="text-center py-2">
                  <div className="spinner-border spinner-border-sm" role="status">
                    <span className="visually-hidden">Cargando...</span>
                  </div>
                </div>
              ) : (
                <div style={{ maxHeight: "200px", overflowY: "auto" }}>
                  {filteredTags.length === 0 ? (
                    <p className="text-muted small mb-0">No hay tags disponibles</p>
                  ) : (
                    filteredTags.map((tag) => {
                      const isSelected = config.tagNames.includes(tag.name);
                      const unit = getTagUnit(tag.name);
                      const unitsInUse = new Set(config.tagNames.map(getTagUnit));
                      const reachedLimit = unitsInUse.size >= 2 && !unitsInUse.has(unit);
                      return (
                        <div
                          key={tag.name}
                          className={`p-2 border-bottom ${isSelected ? "bg-primary bg-opacity-10" : ""} ${reachedLimit ? "text-muted" : "cursor-pointer"}`}
                          style={{ cursor: reachedLimit ? "not-allowed" : "pointer", opacity: reachedLimit ? 0.6 : 1 }}
                          onClick={() => {
                            if (reachedLimit) return;
                            handleTagToggle(tag.name);
                          }}
                        >
                          <div className="d-flex justify-content-between align-items-center">
                            <div>
                              <strong className="small">{tag.display_name || tag.name}</strong>
                              <br />
                              <span className="text-muted small">
                                {tag.name} · {unit}
                              </span>
                            </div>
                            {isSelected && <i className="bi bi-check-circle-fill text-primary"></i>}
                            {!isSelected && reachedLimit && <small className="text-muted">máx 2 unidades</small>}
                          </div>
                        </div>
                      );
                    })
                  )}
                </div>
              )}
            </div>
          </div>
        )}

        {/* Gráfico */}
        <div style={{ width: "100%", flex: 1, minHeight: "300px", position: "relative", display: "flex", flexDirection: "column" }}>
          {config.tagNames.length === 0 ? (
            <div className="text-center py-5 text-muted" style={{ height: "100%", display: "flex", flexDirection: "column", justifyContent: "center" }}>
              <i className="bi bi-graph-up" style={{ fontSize: "3rem" }}></i>
              <p className="mt-3">Seleccione tags para visualizar</p>
            </div>
          ) : (
            <Plot
              data={plotData.data}
              layout={plotData.layout}
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

