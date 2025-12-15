import { useEffect, useState, useCallback, useMemo, useRef } from "react";
import { Card } from "../components/Card";
import { Button } from "../components/Button";
import {
  getTags,
  getTrends,
  getTimezones,
  type Tag,
  type TrendsFilter,
  type TrendsResponse,
} from "../services/tags";
import Plot from "react-plotly.js";
import type { Data, Layout } from "plotly.js";
import { useTheme } from "../hooks/useTheme";

type PresetDate =
  | "Last Hour"
  | "Last 6 Hours"
  | "Last 12 Hours"
  | "Last Day"
  | "Last Week"
  | "Last Month"
  | "Custom";

const PRESET_DATES: PresetDate[] = [
  "Last Hour",
  "Last 6 Hours",
  "Last 12 Hours",
  "Last Day",
  "Last Week",
  "Last Month",
  "Custom",
];

// Calcular fecha basada en preset
const getPresetDateRange = (preset: PresetDate): { start: Date; end: Date } => {
  const end = new Date();
  let start = new Date();

  switch (preset) {
    case "Last Hour":
      start = new Date(end.getTime() - 1 * 60 * 60 * 1000);
      break;
    case "Last 6 Hours":
      start = new Date(end.getTime() - 6 * 60 * 60 * 1000);
      break;
    case "Last 12 Hours":
      start = new Date(end.getTime() - 12 * 60 * 60 * 1000);
      break;
    case "Last Day":
      start = new Date(end.getTime() - 24 * 60 * 60 * 1000);
      break;
    case "Last Week":
      start = new Date(end.getTime() - 7 * 24 * 60 * 60 * 1000);
      break;
    case "Last Month":
      start = new Date(end.getTime() - 30 * 24 * 60 * 60 * 1000);
      break;
    case "Custom":
      // No cambiar, usar valores actuales
      break;
  }

  return { start, end };
};

// Formatear fecha para input datetime-local
const formatToLocalDateTime = (date: Date): string => {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  const hours = String(date.getHours()).padStart(2, "0");
  const minutes = String(date.getMinutes()).padStart(2, "0");
  return `${year}-${month}-${day}T${hours}:${minutes}`;
};

// Formatear fecha para backend
const formatDateTimeForBackend = (dateString: string): string => {
  if (!dateString) return "";
  // El input datetime-local devuelve formato: YYYY-MM-DDTHH:mm
  // El backend espera: YYYY-MM-DD HH:mm:ss.00
  return dateString.replace("T", " ") + ":00.00";
};

export function Trends() {
  const { mode } = useTheme();
  const [presetDate, setPresetDate] = useState<PresetDate>(() => {
    const saved = localStorage.getItem("trends_presetDate");
    return (saved as PresetDate) || "Last Hour";
  });
  const [startDate, setStartDate] = useState<string>(() => {
    return localStorage.getItem("trends_startDate") || "";
  });
  const [endDate, setEndDate] = useState<string>(() => {
    return localStorage.getItem("trends_endDate") || "";
  });
  const [selectedTags, setSelectedTags] = useState<string[]>(() => {
    const saved = localStorage.getItem("trends_selectedTags");
    return saved ? JSON.parse(saved) : [];
  });
  const [tagSearch, setTagSearch] = useState("");
  const [availableTags, setAvailableTags] = useState<Tag[]>([]);
  const [allTags, setAllTags] = useState<Tag[]>([]);
  const [selectedTimezone, setSelectedTimezone] = useState<string>(() => {
    return localStorage.getItem("trends_timezone") || "";
  });
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [trendsData, setTrendsData] = useState<TrendsResponse>({});
  const [showTagDropdown, setShowTagDropdown] = useState(false);
  const tagDropdownRef = useRef<HTMLDivElement>(null);

  // Estado para controlar si ya se cargaron las opciones
  const [optionsLoaded, setOptionsLoaded] = useState(false);

  // Cargar opciones al montar
  useEffect(() => {
    const loadOptions = async () => {
      try {
        // Detectar zona horaria del navegador
        const browserTimezone = Intl.DateTimeFormat().resolvedOptions().timeZone;

        // Cargar tags (cargar todas las páginas)
        const allTagsList: Tag[] = [];
        let page = 1;
        let hasMore = true;
        while (hasMore) {
          const response = await getTags(page, 100);
          allTagsList.push(...(response.data || []));
          hasMore = page < response.pagination.pages;
          page++;
        }
        setAllTags(allTagsList);
        setAvailableTags(allTagsList);

        // Validar que los tags guardados aún existan
        if (selectedTags.length > 0) {
          const validTags = selectedTags.filter(tagName => 
            allTagsList.some(tag => tag.name === tagName)
          );
          if (validTags.length !== selectedTags.length) {
            setSelectedTags(validTags);
            localStorage.setItem("trends_selectedTags", JSON.stringify(validTags));
          }
        }

        // Cargar timezones para detectar automáticamente
        const timezones = await getTimezones();

        // Detectar timezone automáticamente solo si no hay uno guardado
        if (!selectedTimezone) {
          let detectedTimezone = browserTimezone;
          if (timezones.includes(browserTimezone)) {
            detectedTimezone = browserTimezone;
          } else {
            // Buscar timezone similar en la misma región
            const region = browserTimezone.split("/")[0];
            const similarTimezone = timezones.find((tz) => tz.startsWith(region));
            if (similarTimezone) {
              detectedTimezone = similarTimezone;
            } else if (timezones.length > 0) {
              detectedTimezone = timezones[0];
            }
          }
          setSelectedTimezone(detectedTimezone);
          localStorage.setItem("trends_timezone", detectedTimezone);
        } else {
          // Validar que el timezone guardado aún esté disponible
          if (!timezones.includes(selectedTimezone)) {
            // Buscar timezone similar
            const region = selectedTimezone.split("/")[0];
            const similarTimezone = timezones.find((tz) => tz.startsWith(region));
            const newTimezone = similarTimezone || (timezones.length > 0 ? timezones[0] : browserTimezone);
            setSelectedTimezone(newTimezone);
            localStorage.setItem("trends_timezone", newTimezone);
          }
        }

        // Inicializar fechas solo si no hay fechas guardadas
        if (!startDate || !endDate) {
          const { start, end } = getPresetDateRange(presetDate);
          const newStartDate = formatToLocalDateTime(start);
          const newEndDate = formatToLocalDateTime(end);
          setStartDate(newStartDate);
          setEndDate(newEndDate);
          localStorage.setItem("trends_startDate", newStartDate);
          localStorage.setItem("trends_endDate", newEndDate);
        }

        setOptionsLoaded(true);
      } catch (e: any) {
        const data = e?.response?.data;
        const backendMessage =
          (typeof data === "string" ? data : undefined) ??
          data?.message ??
          data?.detail ??
          data?.error;
        const errorMsg = backendMessage || e?.message || "Error al cargar opciones";
        setError(errorMsg);
        setOptionsLoaded(true);
      }
    };
    loadOptions();
  }, []);

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

  // Cerrar dropdown al hacer click fuera
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (tagDropdownRef.current && !tagDropdownRef.current.contains(event.target as Node)) {
        setShowTagDropdown(false);
      }
    };

    if (showTagDropdown) {
      document.addEventListener("mousedown", handleClickOutside);
    }

    return () => {
      document.removeEventListener("mousedown", handleClickOutside);
    };
  }, [showTagDropdown]);

  const handleTagToggle = (tagName: string) => {
    setSelectedTags((prev) =>
      prev.includes(tagName)
        ? prev.filter((name) => name !== tagName)
        : [...prev, tagName]
    );
  };

  const handleLoadTrends = useCallback(async () => {
    if (selectedTags.length === 0) {
      setError("Debe seleccionar al menos un tag");
      return;
    }

    if (!startDate || !endDate) {
      setError("Debe seleccionar un rango de fechas");
      return;
    }

    const start = new Date(startDate);
    const end = new Date(endDate);
    if (end > new Date()) {
      setError("La fecha final no puede ser mayor a la fecha actual");
      return;
    }

    if (start >= end) {
      setError("La fecha de inicio debe ser menor a la fecha final");
      return;
    }

    setLoading(true);
    setError(null);
    try {
      const filters: TrendsFilter = {
        tags: selectedTags,
        greater_than_timestamp: formatDateTimeForBackend(startDate),
        less_than_timestamp: formatDateTimeForBackend(endDate),
        timezone: selectedTimezone,
      };
      const data = await getTrends(filters);
      setTrendsData(data);
    } catch (e: any) {
      const data = e?.response?.data;
      const backendMessage =
        (typeof data === "string" ? data : undefined) ??
        data?.message ??
        data?.detail ??
        data?.error;
      const errorMsg = backendMessage || e?.message || "Error al cargar las tendencias";
      setError(errorMsg);
      setTrendsData({});
    } finally {
      setLoading(false);
    }
  }, [selectedTags, startDate, endDate, selectedTimezone]);

  // Ref para evitar cargar múltiples veces
  const hasAutoLoadedRef = useRef(false);

  // Cargar automáticamente los trends si hay filtros válidos guardados
  useEffect(() => {
    if (!optionsLoaded || hasAutoLoadedRef.current) return;

    // Solo cargar automáticamente si hay filtros válidos
    if (
      selectedTags.length > 0 &&
      startDate &&
      endDate &&
      selectedTimezone
    ) {
      // Validar fechas antes de cargar
      const start = new Date(startDate);
      const end = new Date(endDate);
      const now = new Date();

      if (end <= now && start < end) {
        hasAutoLoadedRef.current = true;
        handleLoadTrends();
      }
    }
  }, [optionsLoaded, selectedTags, startDate, endDate, selectedTimezone, handleLoadTrends]);

  // Actualizar fechas cuando cambia el preset
  useEffect(() => {
    if (presetDate !== "Custom") {
      const { start, end } = getPresetDateRange(presetDate);
      const newStartDate = formatToLocalDateTime(start);
      const newEndDate = formatToLocalDateTime(end);
      setStartDate(newStartDate);
      setEndDate(newEndDate);
      localStorage.setItem("trends_startDate", newStartDate);
      localStorage.setItem("trends_endDate", newEndDate);
    }
  }, [presetDate]);

  // Persistir cambios en localStorage
  useEffect(() => {
    localStorage.setItem("trends_presetDate", presetDate);
  }, [presetDate]);

  useEffect(() => {
    if (startDate) {
      localStorage.setItem("trends_startDate", startDate);
    }
  }, [startDate]);

  useEffect(() => {
    if (endDate) {
      localStorage.setItem("trends_endDate", endDate);
    }
  }, [endDate]);

  useEffect(() => {
    localStorage.setItem("trends_selectedTags", JSON.stringify(selectedTags));
  }, [selectedTags]);

  useEffect(() => {
    if (selectedTimezone) {
      localStorage.setItem("trends_timezone", selectedTimezone);
    }
  }, [selectedTimezone]);

  // Preparar datos para Plotly con múltiples ejes Y
  const plotData = useMemo(() => {
    if (!trendsData || Object.keys(trendsData).length === 0) {
      return { data: [], layout: {} };
    }

    // Agrupar tags por unidad
    const tagsByUnit = new Map<string, { tagName: string; unit: string; values: { x: string; y: number }[] }[]>();
    
    Object.entries(trendsData).forEach(([tagName, tagData]) => {
      const unit = tagData.unit || "unknown";
      if (!tagsByUnit.has(unit)) {
        tagsByUnit.set(unit, []);
      }
      tagsByUnit.get(unit)!.push({
        tagName,
        unit,
        values: tagData.values || [],
      });
    });

    // Paleta de colores para las diferentes unidades
    const colorPalette = [
      "#1f77b4", // azul
      "#ff7f0e", // naranja
      "#2ca02c", // verde
      "#d62728", // rojo
      "#9467bd", // morado
      "#8c564b", // marrón
      "#e377c2", // rosa
      "#7f7f7f", // gris
      "#bcbd22", // oliva
      "#17becf", // cian
    ];

    // Función auxiliar para ajustar brillo de color
    const adjustColorBrightness = (color: string, amount: number): string => {
      // Convertir hex a RGB
      const hex = color.replace("#", "");
      const r = parseInt(hex.substr(0, 2), 16);
      const g = parseInt(hex.substr(2, 2), 16);
      const b = parseInt(hex.substr(4, 2), 16);
      
      // Ajustar brillo
      const newR = Math.max(0, Math.min(255, r + amount * 50));
      const newG = Math.max(0, Math.min(255, g + amount * 50));
      const newB = Math.max(0, Math.min(255, b + amount * 50));
      
      return `rgb(${Math.round(newR)}, ${Math.round(newG)}, ${Math.round(newB)})`;
    };

    // Crear trazas y asignar ejes Y
    const data: Data[] = [];
    const unitArray = Array.from(tagsByUnit.keys());

    unitArray.forEach((unit, unitIndex) => {
      const tags = tagsByUnit.get(unit)!;
      const yAxisKey = unitIndex === 0 ? "y" : `y${unitIndex + 1}`;
      const unitColor = colorPalette[unitIndex % colorPalette.length];

      // Crear traza para cada tag de esta unidad
      tags.forEach((tag, tagIndex) => {
        // Convertir timestamps a Date objects para Plotly
        // El formato del backend es: "%m/%d/%Y, %H:%M:%S.%f" (ej: "12/12/2025, 14:30:45.123456")
        const xValues = tag.values.map((v) => {
          const dateStr = v.x;
          try {
            // Parsear formato: "MM/DD/YYYY, HH:MM:SS.microseconds"
            // Extraer la parte antes de los microsegundos
            const parts = dateStr.split(".");
            const mainPart = parts[0]; // "MM/DD/YYYY, HH:MM:SS"
            // Convertir a formato parseable: "MM/DD/YYYY, HH:MM:SS" -> "MM/DD/YYYY HH:MM:SS"
            const normalized = mainPart.replace(", ", " ");
            // Parsear manualmente
            const [datePart, timePart] = normalized.split(" ");
            if (!datePart || !timePart) {
              return new Date(dateStr); // Fallback
            }
            const [month, day, year] = datePart.split("/");
            const [hours, minutes, seconds] = timePart.split(":");
            // Crear Date object (mes es 0-indexed)
            return new Date(
              parseInt(year, 10),
              parseInt(month, 10) - 1,
              parseInt(day, 10),
              parseInt(hours, 10),
              parseInt(minutes, 10),
              parseInt(seconds || "0", 10)
            );
          } catch (e) {
            // Fallback: intentar parseo directo
            return new Date(dateStr);
          }
        });
        const yValues = tag.values.map((v) => v.y);

        // Variar ligeramente el color para tags diferentes de la misma unidad
        const colorVariation = tagIndex * 0.15; // Variación de opacidad/brillo
        const tagColor = tagIndex === 0 
          ? unitColor 
          : adjustColorBrightness(unitColor, colorVariation);

        data.push({
          x: xValues,
          y: yValues,
          type: "scatter",
          mode: "lines",
          name: `${tag.tagName} (${unit})`,
          yaxis: yAxisKey,
          line: { 
            width: 2,
            color: tagColor,
          },
        });
      });
    });

    // Configurar colores según el tema
    const isDark = mode === "dark";
    const paperBgColor = isDark ? "#212529" : "#ffffff";
    const plotBgColor = isDark ? "#2b3035" : "#f8f9fa";
    const textColor = isDark ? "#ffffff" : "#212529";
    const gridColor = isDark ? "rgba(255, 255, 255, 0.1)" : "rgba(0, 0, 0, 0.1)";
    const lineColor = isDark ? "rgba(255, 255, 255, 0.3)" : "rgba(0, 0, 0, 0.3)";

    // Crear layout con múltiples ejes Y
    const layout: Partial<Layout> = {
      paper_bgcolor: paperBgColor,
      plot_bgcolor: plotBgColor,
      font: {
        color: textColor,
      },
      xaxis: {
        title: "Tiempo",
        type: "date",
        gridcolor: gridColor,
        linecolor: lineColor,
        zerolinecolor: lineColor,
        titlefont: {
          color: textColor,
        },
        tickfont: {
          color: textColor,
        },
      },
      hovermode: "x unified",
      legend: {
        orientation: "v",
        x: 1.01,
        y: 1,
        xanchor: "left",
        yanchor: "top",
        font: {
          color: textColor,
        },
        bgcolor: isDark ? "rgba(33, 37, 41, 0.8)" : "rgba(255, 255, 255, 0.8)",
        bordercolor: lineColor,
      },
      margin: { l: 60, r: 50, t: 20, b: 60 },
      autosize: true,
    };

    // Agregar ejes Y dinámicamente con colores y posiciones mejoradas
    // Lógica: 1 eje = izquierda, 2 ejes = izquierda y derecha, más de 2 = izquierda y resto a la derecha con separación
    const totalAxes = unitArray.length;
    const axisSpacing = 0.25; // Separación entre ejes a la derecha
    
    unitArray.forEach((unit, index) => {
      const unitColor = colorPalette[index % colorPalette.length];
      
      if (index === 0) {
        // Primer eje Y siempre a la izquierda
        layout.yaxis = {
          title: unit,
          side: "left",
          gridcolor: gridColor,
          linecolor: unitColor,
          zerolinecolor: lineColor,
          titlefont: {
            color: unitColor,
          },
          tickfont: {
            color: unitColor,
          },
        };
      } else {
        // Ejes Y adicionales siempre a la derecha con separación
        const axisKey = `yaxis${index + 1}` as keyof Layout;
        // Calcular posición: 1.0 para el segundo eje, luego incrementar por axisSpacing
        const position = 1.0 + ((index - 1) * axisSpacing);
        
        layout[axisKey] = {
          title: unit,
          side: "right",
          overlaying: "y",
          position: position,
          gridcolor: gridColor,
          linecolor: unitColor,
          zerolinecolor: lineColor,
          titlefont: {
            color: unitColor,
          },
          tickfont: {
            color: unitColor,
          },
        };
      }
    });
    
    // Ajustar márgenes según la cantidad de ejes para evitar que se corten
    const leftMargin = 60;
    const rightMargin = 50 + (totalAxes > 1 ? (totalAxes - 1) * 60 : 0);
    
    layout.margin = { 
      l: leftMargin, 
      r: rightMargin, 
      t: 20, 
      b: 60 
    };

    return { data, layout };
  }, [trendsData, mode]);

  return (
    <div className="row">
      <div className="col-12">
        <Card
          title={
            <div className="d-flex justify-content-between align-items-center w-100 flex-wrap gap-2">
              <h3 className="card-title m-0">Trends</h3>
              <div className="d-flex align-items-center gap-2 flex-wrap">
                <select
                  className="form-select form-select-sm"
                  style={{ width: "auto", minWidth: "150px" }}
                  value={presetDate}
                  onChange={(e) => {
                    const newPreset = e.target.value as PresetDate;
                    setPresetDate(newPreset);
                    localStorage.setItem("trends_presetDate", newPreset);
                  }}
                  disabled={loading}
                >
                  {PRESET_DATES.map((preset) => (
                    <option key={preset} value={preset}>
                      {preset}
                    </option>
                  ))}
                </select>
                {presetDate === "Custom" && (
                  <>
                    <input
                      type="datetime-local"
                      className="form-control form-control-sm"
                      style={{ width: "auto", minWidth: "160px" }}
                      value={startDate}
                      onChange={(e) => {
                        const newStart = e.target.value;
                        setStartDate(newStart);
                        localStorage.setItem("trends_startDate", newStart);
                      }}
                      disabled={loading}
                    />
                    <input
                      type="datetime-local"
                      className="form-control form-control-sm"
                      style={{ width: "auto", minWidth: "160px" }}
                      value={endDate}
                      onChange={(e) => {
                        const newEnd = e.target.value;
                        const endDateObj = new Date(newEnd);
                        const now = new Date();
                        const finalEnd = endDateObj > now ? formatToLocalDateTime(now) : newEnd;
                        setEndDate(finalEnd);
                        localStorage.setItem("trends_endDate", finalEnd);
                      }}
                      disabled={loading}
                      max={formatToLocalDateTime(new Date())}
                    />
                  </>
                )}
                <Button
                  variant="primary"
                  className="btn-sm"
                  onClick={handleLoadTrends}
                  disabled={loading || selectedTags.length === 0}
                  loading={loading}
                >
                  <i className="bi bi-graph-up me-1"></i>
                  Cargar Trends
                </Button>
              </div>
            </div>
          }
        >
          {error && (
            <div className="alert alert-danger mb-3" role="alert">
              {error}
            </div>
          )}

          <div className="row">
            {/* Selector de tags con búsqueda - 4 columnas */}
            <div className="col-4">
              <div className="card">
                <div className="card-header">
                  <h6 className="mb-0">Seleccionar Tags</h6>
                </div>
                <div className="card-body">
                  <div className="position-relative" ref={tagDropdownRef}>
                    <div
                      className="form-control d-flex align-items-center justify-content-between"
                      style={{ cursor: "pointer", minHeight: "38px" }}
                      onClick={() => setShowTagDropdown(!showTagDropdown)}
                    >
                      <div className="d-flex flex-wrap gap-1" style={{ flex: 1 }}>
                        {selectedTags.length === 0 ? (
                          <span className="text-muted">Seleccionar tags...</span>
                        ) : (
                          selectedTags.slice(0, 3).map((tagName) => {
                            const tag = availableTags.find((t) => t.name === tagName);
                            return (
                              <span
                                key={tagName}
                                className="badge bg-primary"
                                onClick={(e) => {
                                  e.stopPropagation();
                                  handleTagToggle(tagName);
                                }}
                              >
                                {tag?.display_name || tagName}
                                <i className="bi bi-x ms-1"></i>
                              </span>
                            );
                          })
                        )}
                        {selectedTags.length > 3 && (
                          <span className="badge bg-secondary">
                            +{selectedTags.length - 3} más
                          </span>
                        )}
                      </div>
                      <i
                        className={`bi bi-chevron-${showTagDropdown ? "up" : "down"}`}
                      ></i>
                    </div>

                    {showTagDropdown && (
                      <div
                        className="card position-absolute w-100 mt-1"
                        style={{
                          zIndex: 1000,
                          maxHeight: "400px",
                          display: "flex",
                          flexDirection: "column",
                        }}
                      >
                        <div className="card-body p-2" style={{ flex: "0 0 auto" }}>
                          <input
                            type="text"
                            className="form-control form-control-sm"
                            placeholder="Buscar tags..."
                            value={tagSearch}
                            onChange={(e) => {
                              setTagSearch(e.target.value);
                            }}
                            onClick={(e) => e.stopPropagation()}
                            onFocus={(e) => e.stopPropagation()}
                          />
                        </div>
                        <div
                          className="border-top"
                          style={{
                            maxHeight: "300px",
                            overflowY: "auto",
                            flex: "1 1 auto",
                          }}
                        >
                          {filteredTags.length === 0 ? (
                            <div className="p-3 text-center text-muted">
                              <small>No se encontraron tags</small>
                            </div>
                          ) : (
                            <div className="list-group list-group-flush">
                              {filteredTags.map((tag) => {
                                const isSelected = selectedTags.includes(tag.name);
                                return (
                                  <button
                                    key={tag.name}
                                    type="button"
                                    className={`list-group-item list-group-item-action d-flex align-items-center justify-content-between ${
                                      isSelected ? "active" : ""
                                    }`}
                                    onClick={() => {
                                      handleTagToggle(tag.name);
                                    }}
                                  >
                                    <div>
                                      <div className="fw-bold">
                                        {tag.display_name || tag.name}
                                      </div>
                                      {tag.description && (
                                        <small className="text-muted">
                                          {tag.description}
                                        </small>
                                      )}
                                    </div>
                                    {isSelected && (
                                      <i className="bi bi-check-circle-fill"></i>
                                    )}
                                  </button>
                                );
                              })}
                            </div>
                          )}
                        </div>
                      </div>
                    )}
                  </div>
                </div>
              </div>
            </div>

            {/* Gráfico - 8 columnas */}
            <div className="col-8">
              {Object.keys(trendsData).length > 0 ? (
                <div className="card h-100">
                  <div className="card-body p-0">
                    <div style={{ width: "100%", height: "600px" }}>
                      <Plot
                        data={plotData.data}
                        layout={plotData.layout}
                        style={{ width: "100%", height: "100%" }}
                        config={{
                          displayModeBar: true,
                          modeBarButtonsToAdd: ["zoom2d", "pan2d", "select2d", "lasso2d", "autoScale2d", "resetScale2d"],
                          displaylogo: false,
                          responsive: true,
                        }}
                      />
                    </div>
                  </div>
                </div>
              ) : (
                <div className="card h-100">
                  <div className="card-body">
                    <div className="text-center py-5 text-muted">
                      <i className="bi bi-graph-up" style={{ fontSize: "3rem" }}></i>
                      <p className="mt-3">Seleccione tags y fechas para visualizar las tendencias</p>
                    </div>
                  </div>
                </div>
              )}
            </div>
          </div>
        </Card>
      </div>
    </div>
  );
}
