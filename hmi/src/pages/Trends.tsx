import { useEffect, useState, useCallback, useMemo, useRef } from "react";
import { Card } from "../components/Card";
import { Button } from "../components/Button";
import { MultiSelectSearch } from "../components/MultiSelectSearch";
import {
  getTags,
  getTagsList,
  getTrends,
  type Tag,
  type TagsResponse,
  type TrendsFilter,
  type TrendsResponse,
} from "../services/tags";
import { isDbUnavailableError } from "../services/health";
import Plot from "react-plotly.js";
import type { Data, Layout, PlotRelayoutEvent } from "plotly.js";
import axios from "axios";
import { useTheme } from "../hooks/useTheme";
import { useTranslation } from "../hooks/useTranslation";
import { useDisplayTimezone } from "../hooks/useDisplayTimezone";
import { TimezoneBadge } from "../components/TimezoneBadge";
import { formatInstantForBackend } from "../utils/timezone";

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

const localDateTimeInputToMs = (value: string): number => {
  const [datePart, timePart = "00:00"] = value.split("T");
  const [year, month, day] = datePart.split("-").map(Number);
  const [hours, minutes, seconds] = timePart.split(":").map(Number);
  return new Date(year, (month || 1) - 1, day || 1, hours || 0, minutes || 0, seconds || 0).getTime();
};

/** Interpreta el rango de Plotly como hora civil local (igual que los Date del eje X). */
const plotlyRangeValueToMs = (value: string | number): number | null => {
  if (typeof value === "number" && Number.isFinite(value)) {
    return value;
  }
  if (typeof value !== "string") {
    return null;
  }
  const match = value.trim().match(
    /^(\d{4})-(\d{2})-(\d{2})[ T](\d{2}):(\d{2})(?::(\d{2})(?:\.(\d+))?)?/
  );
  if (match) {
    const ms = match[7] ? Number(match[7].padEnd(3, "0").slice(0, 3)) : 0;
    return new Date(
      Number(match[1]),
      Number(match[2]) - 1,
      Number(match[3]),
      Number(match[4]),
      Number(match[5]),
      Number(match[6] || 0),
      ms
    ).getTime();
  }
  const parsed = Date.parse(value);
  return Number.isNaN(parsed) ? null : parsed;
};

const rangesNearlyEqual = (
  aStart: number,
  aEnd: number,
  bStart: number,
  bEnd: number,
  toleranceMs = 1000
): boolean =>
  Math.abs(aStart - bStart) <= toleranceMs && Math.abs(aEnd - bEnd) <= toleranceMs;

type TrendsRangeCache = {
  startMs: number;
  endMs: number;
  data: TrendsResponse;
};

const ZOOM_DEBOUNCE_MS = 220;
const ZOOM_CACHE_LIMIT = 8;

export function Trends() {
  const { t } = useTranslation();
  const { mode } = useTheme();
  const { timeZone } = useDisplayTimezone();
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
  const [availableTags, setAvailableTags] = useState<Tag[]>([]);
  const [loading, setLoading] = useState(false);
  const [zoomLoading, setZoomLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [trendsData, setTrendsData] = useState<TrendsResponse>({});
  const [dataRevision, setDataRevision] = useState(0);
  const [axisRange, setAxisRange] = useState<[Date, Date] | null>(null);

  // Estado para controlar si ya se cargaron las opciones
  const [optionsLoaded, setOptionsLoaded] = useState(false);

  const abortRef = useRef<AbortController | null>(null);
  const fetchIdRef = useRef(0);
  const ignoreRelayoutRef = useRef(false);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const relayoutTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const queriedRangeRef = useRef<{ startMs: number; endMs: number } | null>(null);
  const baseCacheRef = useRef<TrendsRangeCache | null>(null);
  const zoomCacheRef = useRef<TrendsRangeCache[]>([]);
  const loadedTagsRef = useRef<string[]>([]);
  const loadedTimezoneRef = useRef<string>("");
  const loadingRef = useRef(false);

  // Cargar opciones al montar
  useEffect(() => {
    const loadOptions = async () => {
      try {
        let allTagsList: Tag[] = [];
        try {
          allTagsList = await getTagsList();
        } catch (_e) {
          let page = 1;
          let hasMore = true;
          while (hasMore) {
            const response: TagsResponse = await getTags(page, 100);
            allTagsList.push(...(response.data || []));
            hasMore = page < response.pagination.pages;
            page++;
          }
        }
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
        const errorMsg = backendMessage || e?.message || t("trends.loadOptionsError");
        setError(errorMsg);
        setOptionsLoaded(true);
      }
    };
    loadOptions();
  }, []);

  const tagOptions = useMemo(
    () =>
      availableTags.map((tag) => ({
        value: tag.name,
        label: tag.display_name || tag.name,
        description: tag.variable || tag.description,
      })),
    [availableTags]
  );

  const handleSelectedTagsChange = (next: string[]) => {
    setSelectedTags(next);
  };

  const cancelInFlight = useCallback(() => {
    if (debounceRef.current) {
      clearTimeout(debounceRef.current);
      debounceRef.current = null;
    }
    if (relayoutTimeoutRef.current) {
      clearTimeout(relayoutTimeoutRef.current);
      relayoutTimeoutRef.current = null;
    }
    abortRef.current?.abort();
    fetchIdRef.current += 1;
    setZoomLoading(false);
  }, []);

  const applyTrendsData = useCallback(
    (data: TrendsResponse, range: { startMs: number; endMs: number }, isBase = false) => {
      ignoreRelayoutRef.current = true;
      queriedRangeRef.current = range;
      setTrendsData(data);
      setDataRevision((n) => n + 1);
      setAxisRange(isBase ? null : [new Date(range.startMs), new Date(range.endMs)]);
      if (relayoutTimeoutRef.current) {
        clearTimeout(relayoutTimeoutRef.current);
      }
      relayoutTimeoutRef.current = window.setTimeout(() => {
        ignoreRelayoutRef.current = false;
        relayoutTimeoutRef.current = null;
      }, 200);
    },
    []
  );

  const rememberZoomCache = useCallback((entry: TrendsRangeCache) => {
    const cache = zoomCacheRef.current.filter(
      (item) => !rangesNearlyEqual(item.startMs, item.endMs, entry.startMs, entry.endMs)
    );
    cache.unshift(entry);
    zoomCacheRef.current = cache.slice(0, ZOOM_CACHE_LIMIT);
  }, []);

  const findCachedRange = useCallback(
    (startMs: number, endMs: number): { data: TrendsResponse; isBase: boolean } | null => {
      const base = baseCacheRef.current;
      if (base && rangesNearlyEqual(startMs, endMs, base.startMs, base.endMs)) {
        return { data: base.data, isBase: true };
      }
      const hit = zoomCacheRef.current.find((item) =>
        rangesNearlyEqual(startMs, endMs, item.startMs, item.endMs)
      );
      return hit ? { data: hit.data, isBase: false } : null;
    },
    []
  );

  const fetchTrendsForRange = useCallback(
    async (
      startMs: number,
      endMs: number,
      options: { asBase?: boolean; silent?: boolean } = {}
    ) => {
      const tags = options.asBase ? selectedTags : loadedTagsRef.current;
      const timezone = options.asBase ? timeZone : loadedTimezoneRef.current;
      if (tags.length === 0 || !timezone || endMs <= startMs) {
        return;
      }

      const current = queriedRangeRef.current;
      if (current && rangesNearlyEqual(startMs, endMs, current.startMs, current.endMs)) {
        return;
      }

      const cached = findCachedRange(startMs, endMs);
      if (cached) {
        cancelInFlight();
        applyTrendsData(cached.data, { startMs, endMs }, cached.isBase);
        return;
      }

      abortRef.current?.abort();
      const controller = new AbortController();
      abortRef.current = controller;
      const fetchId = ++fetchIdRef.current;

      if (options.silent) {
        setZoomLoading(true);
      } else {
        setLoading(true);
        loadingRef.current = true;
        setError(null);
      }

      try {
        const filters: TrendsFilter = {
          tags,
          greater_than_timestamp: formatInstantForBackend(new Date(startMs), timezone),
          less_than_timestamp: formatInstantForBackend(new Date(endMs), timezone),
          timezone,
        };
        const data = await getTrends(filters, { signal: controller.signal });
        if (fetchId !== fetchIdRef.current) {
          return;
        }
        const range = { startMs, endMs };
        if (options.asBase) {
          baseCacheRef.current = { ...range, data };
          zoomCacheRef.current = [];
          loadedTagsRef.current = tags;
          loadedTimezoneRef.current = timezone;
        } else {
          rememberZoomCache({ ...range, data });
        }
        applyTrendsData(data, range, Boolean(options.asBase));
      } catch (e: any) {
        if (axios.isCancel(e) || e?.code === "ERR_CANCELED" || e?.name === "CanceledError") {
          return;
        }
        if (fetchId !== fetchIdRef.current) {
          return;
        }
        if (isDbUnavailableError(e)) {
          return;
        }
        if (!options.silent) {
          const data = e?.response?.data;
          const backendMessage =
            (typeof data === "string" ? data : undefined) ??
            data?.message ??
            data?.detail ??
            data?.error;
          setError(backendMessage || e?.message || t("trends.loadError"));
          setTrendsData({});
          queriedRangeRef.current = null;
        }
      } finally {
        if (fetchId === fetchIdRef.current) {
          if (options.silent) {
            setZoomLoading(false);
          } else {
            setLoading(false);
            loadingRef.current = false;
          }
        }
      }
    },
    [applyTrendsData, cancelInFlight, findCachedRange, rememberZoomCache, selectedTags, timeZone, t]
  );

  const handleLoadTrends = useCallback(async () => {
    if (selectedTags.length === 0) {
      setError(t("trends.selectAtLeastOneTag"));
      return;
    }

    if (!startDate || !endDate) {
      setError(t("trends.selectDateRange"));
      return;
    }

    const startMs = localDateTimeInputToMs(startDate);
    const endMs = localDateTimeInputToMs(endDate);
    if (endMs > Date.now()) {
      setError(t("trends.endDateCannotBeFuture"));
      return;
    }

    if (startMs >= endMs) {
      setError(t("trends.startDateMustBeBeforeEnd"));
      return;
    }

    queriedRangeRef.current = null;
    baseCacheRef.current = null;
    zoomCacheRef.current = [];
    cancelInFlight();
    await fetchTrendsForRange(startMs, endMs, { asBase: true });
  }, [selectedTags, startDate, endDate, fetchTrendsForRange, cancelInFlight, t]);

  const restoreBaseRange = useCallback(() => {
    const base = baseCacheRef.current;
    if (!base) {
      return;
    }
    const current = queriedRangeRef.current;
    if (current && rangesNearlyEqual(current.startMs, current.endMs, base.startMs, base.endMs)) {
      return;
    }
    cancelInFlight();
    applyTrendsData(base.data, { startMs: base.startMs, endMs: base.endMs }, true);
  }, [applyTrendsData, cancelInFlight]);

  const scheduleZoomQuery = useCallback(
    (startMs: number, endMs: number) => {
      const base = baseCacheRef.current;
      if (!base) {
        return;
      }

      const clampedStart = Math.max(startMs, base.startMs);
      const clampedEnd = Math.min(endMs, base.endMs);
      if (clampedEnd - clampedStart < 1000) {
        return;
      }

      if (rangesNearlyEqual(clampedStart, clampedEnd, base.startMs, base.endMs)) {
        restoreBaseRange();
        return;
      }

      const current = queriedRangeRef.current;
      if (current) {
        const currentSpan = current.endMs - current.startMs;
        const nextSpan = clampedEnd - clampedStart;
        const isTinyInset =
          currentSpan > 0 &&
          nextSpan / currentSpan > 0.95 &&
          Math.abs(clampedStart - current.startMs) <= Math.max(1500, currentSpan * 0.03) &&
          Math.abs(clampedEnd - current.endMs) <= Math.max(1500, currentSpan * 0.03);
        if (isTinyInset) {
          return;
        }
      }

      if (debounceRef.current) {
        clearTimeout(debounceRef.current);
      }
      debounceRef.current = setTimeout(() => {
        debounceRef.current = null;
        void fetchTrendsForRange(clampedStart, clampedEnd, { silent: true });
      }, ZOOM_DEBOUNCE_MS);
    },
    [fetchTrendsForRange, restoreBaseRange]
  );

  const handleRelayout = useCallback(
    (event: PlotRelayoutEvent) => {
      if (ignoreRelayoutRef.current || loadingRef.current) {
        return;
      }

      const autoX = event["xaxis.autorange"] === true;
      const rangeTuple = event["xaxis.range"];
      const rangeFromArray = Array.isArray(rangeTuple) ? rangeTuple : null;
      const startRaw = rangeFromArray ? rangeFromArray[0] : event["xaxis.range[0]"];
      const endRaw = rangeFromArray ? rangeFromArray[1] : event["xaxis.range[1]"];

      if (autoX) {
        restoreBaseRange();
        return;
      }

      if (startRaw === undefined || endRaw === undefined) {
        return;
      }

      const startMs = plotlyRangeValueToMs(startRaw as string | number);
      const endMs = plotlyRangeValueToMs(endRaw as string | number);
      if (startMs === null || endMs === null || endMs <= startMs) {
        return;
      }

      scheduleZoomQuery(startMs, endMs);
    },
    [restoreBaseRange, scheduleZoomQuery]
  );

  useEffect(() => {
    return () => {
      if (debounceRef.current) {
        clearTimeout(debounceRef.current);
      }
      abortRef.current?.abort();
    };
  }, []);

  // Ref para evitar cargar múltiples veces
  const hasAutoLoadedRef = useRef(false);

  useEffect(() => {
    hasAutoLoadedRef.current = false;
  }, [timeZone]);

  // Cargar automáticamente los trends si hay filtros válidos guardados
  useEffect(() => {
    if (!optionsLoaded || hasAutoLoadedRef.current) return;

    // Solo cargar automáticamente si hay filtros válidos
    if (
      selectedTags.length > 0 &&
      startDate &&
      endDate &&
      timeZone
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
  }, [optionsLoaded, selectedTags, startDate, endDate, timeZone, handleLoadTrends]);

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

    // Paleta cualitativa: un color distinto por traza, independiente del eje/unidad.
    const TRACE_COLORS = [
      "#1f77b4",
      "#ff7f0e",
      "#2ca02c",
      "#d62728",
      "#9467bd",
      "#8c564b",
      "#e377c2",
      "#17becf",
      "#bcbd22",
      "#393b79",
      "#e6550d",
      "#31a354",
      "#756bb1",
      "#843c39",
      "#3182bd",
      "#637939",
      "#7b4173",
      "#636363",
    ];

    const AXIS_COLORS = [
      "#4c78a8",
      "#f58518",
      "#54a24b",
      "#e45756",
      "#b279a2",
      "#9d755d",
    ];

    // Crear trazas y asignar ejes Y
    const data: Data[] = [];
    const unitArray = Array.from(tagsByUnit.keys());
    let traceColorIndex = 0;

    unitArray.forEach((unit, unitIndex) => {
      const tags = tagsByUnit.get(unit)!;
      const yAxisKey = unitIndex === 0 ? "y" : `y${unitIndex + 1}`;

      tags.forEach((tag) => {
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
        const tagColor = TRACE_COLORS[traceColorIndex % TRACE_COLORS.length];
        traceColorIndex += 1;

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
        title: t("trends.time"),
        type: "date",
        ...(axisRange
          ? { range: axisRange, autorange: false }
          : { autorange: true }),
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
      uirevision: "trends",
      datarevision: dataRevision,
      legend: {
        orientation: "h",
        x: 0,
        y: 1.02,
        xanchor: "left",
        yanchor: "bottom",
        font: {
          color: textColor,
        },
        bgcolor: "rgba(0,0,0,0)",
        bordercolor: "rgba(0,0,0,0)",
      },
      margin: { l: 56, r: 48, t: 36, b: 48 },
      autosize: true,
    };

    // Agregar ejes Y dinámicamente con colores y posiciones mejoradas
    // Lógica: 1 eje = izquierda, 2 ejes = izquierda y derecha, más de 2 = izquierda y resto a la derecha con separación
    const totalAxes = unitArray.length;
    const axisSpacing = 0.25; // Separación entre ejes a la derecha
    
    unitArray.forEach((unit, index) => {
      const unitColor = AXIS_COLORS[index % AXIS_COLORS.length];
      
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
    const leftMargin = 56;
    const rightMargin = 48 + (totalAxes > 1 ? (totalAxes - 1) * 52 : 0);

    layout.margin = {
      l: leftMargin,
      r: rightMargin,
      t: 36,
      b: 48,
    };

    return { data, layout };
  }, [trendsData, mode, dataRevision, axisRange, t]);

  return (
    <div className="row g-0 trends-fit-viewport">
      <div className="col-12 h-100">
        <Card
          className="trends-fit-card"
          style={{ display: "flex", flexDirection: "column", height: "100%", minHeight: 0 }}
          bodyClassName="p-2 d-flex flex-column"
          title={
            <div className="card-header-stack w-100">
              <div className="d-flex justify-content-between align-items-center w-100 flex-wrap gap-2">
                <div className="d-flex align-items-center gap-2">
                  <h3 className="card-title m-0">{t("navigation.trends")}</h3>
                  <TimezoneBadge />
                </div>
                <div className="d-flex align-items-center gap-2 flex-wrap">
                  <label className="form-label small mb-0">{t("trends.selectTags")}:</label>
                  <MultiSelectSearch
                    options={tagOptions}
                    selected={selectedTags}
                    onChange={handleSelectedTagsChange}
                    placeholder={t("trends.selectTagsPlaceholder")}
                    searchPlaceholder={t("trends.searchTags")}
                    emptyText={t("trends.noTagsFound")}
                    selectAllLabel={t("trends.selectAll")}
                    clearLabel={t("common.clear")}
                    selectedCountLabel={(count) => t("trends.selectedCount", { count })}
                    disabled={loading}
                    style={{ width: "220px", maxWidth: "100%" }}
                  />
                  <select
                    className="form-select form-select-sm"
                    style={{ width: "auto", minWidth: "140px", maxWidth: "100%" }}
                    value={presetDate}
                    onChange={(e) => {
                      const newPreset = e.target.value as PresetDate;
                      setPresetDate(newPreset);
                      localStorage.setItem("trends_presetDate", newPreset);
                    }}
                    disabled={loading}
                  >
                    {PRESET_DATES.map((preset) => {
                      const presetKey = preset === "Last Hour" ? "LastHour" : preset.replace(/\s+/g, "");
                      return (
                        <option key={preset} value={preset}>
                          {t(`trends.preset.${presetKey}`)}
                        </option>
                      );
                    })}
                  </select>
                  <Button
                    variant="primary"
                    className="btn-sm"
                    onClick={handleLoadTrends}
                    disabled={loading || selectedTags.length === 0}
                    loading={loading}
                  >
                    <i className="bi bi-graph-up me-1"></i>
                    {t("trends.loadTrends")}
                  </Button>
                </div>
              </div>
              {presetDate === "Custom" && (
                <div className="card-header-stack__row d-flex align-items-center gap-2 flex-wrap pt-2 mt-1 border-top">
                  <label className="form-label small mb-0">{t("trends.time")}:</label>
                  <input
                    type="datetime-local"
                    className="form-control form-control-sm"
                    style={{ width: "180px", maxWidth: "100%" }}
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
                    style={{ width: "180px", maxWidth: "100%" }}
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
                </div>
              )}
            </div>
          }
        >
          {error && (
            <div className="alert alert-danger py-2 mb-2" role="alert">
              {error}
            </div>
          )}

          {Object.keys(trendsData).length > 0 ? (
            <div className="trends-plot-host">
              <Plot
                data={plotData.data}
                layout={plotData.layout}
                style={{ width: "100%", height: "100%" }}
                config={{
                  displayModeBar: true,
                  modeBarButtonsToAdd: [
                    "zoom2d",
                    "pan2d",
                    "select2d",
                    "lasso2d",
                    "autoScale2d",
                    "resetScale2d",
                  ],
                  displaylogo: false,
                  responsive: true,
                }}
                useResizeHandler={true}
                revision={dataRevision}
                onRelayout={handleRelayout}
              />
              {zoomLoading && (
                <div className="trends-plot-overlay" role="status" aria-live="polite">
                  <span className="spinner-border" aria-hidden="true"></span>
                  <span>{t("trends.loadingDetail")}</span>
                </div>
              )}
            </div>
          ) : (
            <div className="trends-plot-host d-flex flex-column justify-content-center text-center text-muted">
              <i className="bi bi-graph-up" style={{ fontSize: "3rem" }}></i>
              <p className="mt-3 mb-0">{t("trends.selectTagsAndDates")}</p>
            </div>
          )}
        </Card>
      </div>
    </div>
  );
}
