import { useEffect, useState } from "react";
import { Card } from "../components/Card";
import { Button } from "../components/Button";
import {
  getTags,
  getTabularData,
  type Tag,
  type TagsResponse,
  type TabularDataFilter,
  type TabularDataResponse,
} from "../services/tags";
import { getTimezones } from "../services/tags";

type PresetDate = 
  | "Last Minute"
  | "Last 2 Minutes"
  | "Last 5 Minutes"
  | "Last 10 Minutes"
  | "Last 30 Minutes"
  | "Last hour"
  | "Last 2 Hours"
  | "Last 6 Hours"
  | "Last 12 Hours"
  | "Last Day"
  | "Custom";

type SampleTimeOption = 
  | "1 Seg"
  | "5 Seg"
  | "10 Seg"
  | "30 Seg"
  | "1 Min"
  | "5 Min"
  | "10 Min"
  | "30 Min"
  | "1 Hr"
  | "2 Hr"
  | "6 Hr"
  | "12 Hr"
  | "1 Day";

const SAMPLE_TIME_OPTIONS: SampleTimeOption[] = [
  "1 Seg",
  "5 Seg",
  "10 Seg",
  "30 Seg",
  "1 Min",
  "5 Min",
  "10 Min",
  "30 Min",
  "1 Hr",
  "2 Hr",
  "6 Hr",
  "12 Hr",
  "1 Day",
];

const PRESET_DATES: PresetDate[] = [
  "Last Minute",
  "Last 2 Minutes",
  "Last 5 Minutes",
  "Last 10 Minutes",
  "Last 30 Minutes",
  "Last hour",
  "Last 2 Hours",
  "Last 6 Hours",
  "Last 12 Hours",
  "Last Day",
  "Custom",
];

// Convertir sample time a segundos
const sampleTimeToSeconds = (option: SampleTimeOption): number => {
  const conversions: Record<SampleTimeOption, number> = {
    "1 Seg": 1,
    "5 Seg": 5,
    "10 Seg": 10,
    "30 Seg": 30,
    "1 Min": 60,
    "5 Min": 300,
    "10 Min": 600,
    "30 Min": 1800,
    "1 Hr": 3600,
    "2 Hr": 7200,
    "6 Hr": 21600,
    "12 Hr": 43200,
    "1 Day": 86400,
  };
  return conversions[option] || 30;
};

// Calcular fecha basada en preset
const getPresetDateRange = (preset: PresetDate): { start: Date; end: Date } => {
  const end = new Date();
  let start = new Date();

  switch (preset) {
    case "Last Minute":
      start = new Date(end.getTime() - 1 * 60 * 1000);
      break;
    case "Last 2 Minutes":
      start = new Date(end.getTime() - 2 * 60 * 1000);
      break;
    case "Last 5 Minutes":
      start = new Date(end.getTime() - 5 * 60 * 1000);
      break;
    case "Last 10 Minutes":
      start = new Date(end.getTime() - 10 * 60 * 1000);
      break;
    case "Last 30 Minutes":
      start = new Date(end.getTime() - 30 * 60 * 1000);
      break;
    case "Last hour":
      start = new Date(end.getTime() - 60 * 60 * 1000);
      break;
    case "Last 2 Hours":
      start = new Date(end.getTime() - 2 * 60 * 60 * 1000);
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
    case "Custom":
      // No hacer nada, usar las fechas personalizadas
      break;
  }

  return { start, end };
};

export function DataLogger() {
  const [tabularData, setTabularData] = useState<TabularDataResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [pagination, setPagination] = useState({
    page: 1,
    limit: 20,
    total: 0,
    pages: 0,
  });

  // Filtros
  const [filters, setFilters] = useState<TabularDataFilter>({
    tags: [],
    greater_than_timestamp: "",
    less_than_timestamp: "",
    sample_time: 30,
    page: 1,
    limit: 20,
  });

  // Opciones para los filtros
  const [availableTags, setAvailableTags] = useState<Tag[]>([]);
  const [selectedTags, setSelectedTags] = useState<string[]>(() => {
    const saved = localStorage.getItem("datalogger_selectedTags");
    return saved ? JSON.parse(saved) : [];
  });
  const [presetDate, setPresetDate] = useState<PresetDate>(() => {
    const saved = localStorage.getItem("datalogger_presetDate");
    return (saved as PresetDate) || "Last 30 Minutes";
  });
  const [startDate, setStartDate] = useState<string>(() => {
    return localStorage.getItem("datalogger_startDate") || "";
  });
  const [endDate, setEndDate] = useState<string>(() => {
    return localStorage.getItem("datalogger_endDate") || "";
  });
  const [sampleTime, setSampleTime] = useState<SampleTimeOption>(() => {
    const saved = localStorage.getItem("datalogger_sampleTime");
    return (saved as SampleTimeOption) || "30 Seg";
  });
  const [availableTimezones, setAvailableTimezones] = useState<string[]>([]);
  const [selectedTimezone, setSelectedTimezone] = useState<string>(() => {
    return localStorage.getItem("datalogger_timezone") || "";
  });

  // Cargar opciones para los filtros
  useEffect(() => {
    loadFilterOptions();
  }, []);

  // Cargar datos cuando cambian los filtros (paginación)
  useEffect(() => {
    if (selectedTags.length > 0 && startDate && endDate && filters.page && filters.limit) {
      loadTabularDataWithFilters();
    }
  }, [filters.page, filters.limit]);

  const loadFilterOptions = async () => {
    try {
      // Detectar zona horaria del navegador
      const browserTimezone = Intl.DateTimeFormat().resolvedOptions().timeZone;
      
      // Cargar tags (necesitamos varios para tener opciones por defecto)
      const tagsResponse: TagsResponse = await getTags(1, 100);
      const allTags = tagsResponse.data || [];
      setAvailableTags(allTags);

      // Seleccionar 3-4 tags por defecto solo si no hay tags guardados
      if (allTags.length > 0 && selectedTags.length === 0) {
        const defaultTags = allTags.slice(0, Math.min(4, allTags.length)).map((t) => t.name);
        setSelectedTags(defaultTags);
        localStorage.setItem("datalogger_selectedTags", JSON.stringify(defaultTags));
      } else if (selectedTags.length > 0) {
        // Validar que los tags guardados aún existan
        const validTags = selectedTags.filter(tagName => 
          allTags.some(tag => tag.name === tagName)
        );
        if (validTags.length !== selectedTags.length) {
          setSelectedTags(validTags);
          localStorage.setItem("datalogger_selectedTags", JSON.stringify(validTags));
        }
      }

      // Cargar timezones
      const timezones = await getTimezones();
      setAvailableTimezones(timezones);
      
      // Intentar usar la zona horaria del navegador, si está disponible
      if (timezones.length > 0) {
        const browserTzInList = timezones.find(tz => tz === browserTimezone);
        if (browserTzInList) {
          setSelectedTimezone(browserTimezone);
        } else {
          // Si no está en la lista, buscar una zona horaria similar
          // Por ejemplo, si el navegador está en "America/Caracas", buscar otras de "America/"
          const browserRegion = browserTimezone.split("/")[0];
          const similarTz = timezones.find(tz => tz.startsWith(browserRegion + "/"));
          if (similarTz) {
            setSelectedTimezone(similarTz);
            localStorage.setItem("datalogger_timezone", similarTz);
          } else {
            setSelectedTimezone(timezones[0]);
            localStorage.setItem("datalogger_timezone", timezones[0]);
          }
        }
      } else if (selectedTimezone) {
        // Si ya hay un timezone guardado, usarlo
        localStorage.setItem("datalogger_timezone", selectedTimezone);
      }

      // Establecer fechas por defecto solo si no hay fechas guardadas
      if (!startDate || !endDate) {
        const { start, end } = getPresetDateRange("Last 30 Minutes");
        const now = new Date();
        const finalEnd = end > now ? now : end;
        const startStr = formatToLocalDateTime(start);
        const endStr = formatToLocalDateTime(finalEnd);
        setEndDate(endStr);
        setStartDate(startStr);
        localStorage.setItem("datalogger_startDate", startStr);
        localStorage.setItem("datalogger_endDate", endStr);
      }
    } catch (e: any) {
      console.error("Error loading filter options:", e);
    }
  };

  // Función helper para convertir Date a formato datetime-local (sin UTC)
  const formatToLocalDateTime = (date: Date): string => {
    const year = date.getFullYear();
    const month = String(date.getMonth() + 1).padStart(2, "0");
    const day = String(date.getDate()).padStart(2, "0");
    const hours = String(date.getHours()).padStart(2, "0");
    const minutes = String(date.getMinutes()).padStart(2, "0");
    return `${year}-${month}-${day}T${hours}:${minutes}`;
  };

  const handlePresetDateChange = (preset: PresetDate) => {
    setPresetDate(preset);
    localStorage.setItem("datalogger_presetDate", preset);
    if (preset !== "Custom") {
      const { start, end } = getPresetDateRange(preset);
      const now = new Date();
      // Asegurar que la fecha final no exceda la actual
      const finalEnd = end > now ? now : end;
      const startStr = formatToLocalDateTime(start);
      const endStr = formatToLocalDateTime(finalEnd);
      setStartDate(startStr);
      setEndDate(endStr);
      localStorage.setItem("datalogger_startDate", startStr);
      localStorage.setItem("datalogger_endDate", endStr);
    }
  };

  const handleEndDateChange = (value: string) => {
    const selectedEnd = new Date(value);
    const now = new Date();
    
    // Validar que la fecha final no exceda la actual
    const finalValue = selectedEnd > now ? formatToLocalDateTime(now) : value;
    setEndDate(finalValue);
    localStorage.setItem("datalogger_endDate", finalValue);
  };

  // Función para convertir el formato de fecha del input al formato esperado por el backend
  const formatDateTimeForBackend = (dateTimeString: string): string => {
    if (!dateTimeString) return "";
    return dateTimeString.replace("T", " ") + ":00.00";
  };


  const handleApplyFilters = () => {
    // Actualizar los filtros y cargar datos
    const newFilters = {
      ...filters,
      page: 1, // Resetear a la primera página al aplicar filtros
    };
    setFilters(newFilters);
    
    // Cargar datos inmediatamente
    if (selectedTags.length > 0 && startDate && endDate) {
      loadTabularDataWithFilters(newFilters);
    }
  };

  const loadTabularDataWithFilters = async (customFilters?: TabularDataFilter) => {
    const filtersToUse = customFilters || filters;
    
    if (selectedTags.length === 0) {
      setError("Debe seleccionar al menos un tag");
      return;
    }

    setLoading(true);
    setError(null);
    try {
      const payload: TabularDataFilter = {
        tags: selectedTags,
        greater_than_timestamp: formatDateTimeForBackend(startDate),
        less_than_timestamp: formatDateTimeForBackend(endDate),
        sample_time: sampleTimeToSeconds(sampleTime),
        page: filtersToUse.page || 1,
        limit: filtersToUse.limit || 20,
      };

      // Siempre enviar timezone, usar el seleccionado o el detectado del navegador
      const timezoneToUse = selectedTimezone || Intl.DateTimeFormat().resolvedOptions().timeZone;
      payload.timezone = timezoneToUse;

      const response: TabularDataResponse = await getTabularData(payload);
      setTabularData(response);
      setPagination({
        page: response.pagination?.page || 1,
        limit: response.pagination?.limit || 20,
        total: response.pagination?.total_records || 0,
        pages: response.pagination?.total_pages || 0,
      });
    } catch (e: any) {
      const errorMsg = e?.response?.data?.message || e?.message || "Error al cargar los datos";
      setError(errorMsg);
      setTabularData(null);
    } finally {
      setLoading(false);
    }
  };

  const handlePageChange = (newPage: number) => {
    if (newPage >= 1 && newPage <= pagination.pages) {
      setFilters({ ...filters, page: newPage });
    }
  };

  const handleLimitChange = (newLimit: number) => {
    if (newLimit > 0) {
      setFilters({ ...filters, page: 1, limit: newLimit });
    }
  };

  const handleExportCSV = async () => {
    if (!tabularData || !tabularData.values || tabularData.values.length === 0) {
      setError("No hay datos para exportar");
      return;
    }

    try {
      setError(null);

      // Obtener todos los datos (sin límite de página)
      const payload: TabularDataFilter = {
        tags: selectedTags,
        greater_than_timestamp: formatDateTimeForBackend(startDate),
        less_than_timestamp: formatDateTimeForBackend(endDate),
        sample_time: sampleTimeToSeconds(sampleTime),
        page: 1,
        limit: 10000, // Obtener todos los registros
      };

      // Siempre enviar timezone, usar el seleccionado o el detectado del navegador
      const timezoneToUse = selectedTimezone || Intl.DateTimeFormat().resolvedOptions().timeZone;
      payload.timezone = timezoneToUse;

      const response: TabularDataResponse = await getTabularData(payload);
      const allData = response.values || [];
      const tagNames = response.tag_names || [];
      const displayNames = response.display_names || [];

      if (!allData || allData.length === 0) {
        setError("No hay datos para exportar");
        return;
      }

      // Preparar los datos para CSV
      const headers = displayNames.length > 0 ? displayNames : tagNames;

      // Convertir datos a filas CSV
      const rows = allData.map((row) => {
        return row.map((cell: any) => {
          return cell !== null && cell !== undefined ? String(cell) : "";
        });
      });

      // Crear contenido CSV
      const csvContent = [
        headers.join(","),
        ...rows.map((row) =>
          row
            .map((cell) => {
              const cellStr = String(cell);
              if (cellStr.includes(",") || cellStr.includes('"') || cellStr.includes("\n")) {
                return `"${cellStr.replace(/"/g, '""')}"`;
              }
              return cellStr;
            })
            .join(",")
        ),
      ].join("\n");

      // Crear blob y descargar
      const blob = new Blob([csvContent], { type: "text/csv;charset=utf-8;" });
      const link = document.createElement("a");
      const url = URL.createObjectURL(blob);

      link.setAttribute("href", url);
      link.setAttribute(
        "download",
        `datalogger_${new Date().toISOString().split("T")[0]}.csv`
      );
      link.style.visibility = "hidden";

      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);

      URL.revokeObjectURL(url);
    } catch (e: any) {
      const errorMsg =
        e?.response?.data?.message || e?.message || "Error al exportar datos a CSV";
      setError(errorMsg);
    }
  };

  return (
    <div className="row">
      <div className="col-12">
        <Card
          title={
            <div className="d-flex align-items-center gap-2 w-100 flex-wrap">
              <span className="me-auto">DataLogger</span>
              <div className="d-flex align-items-center gap-2">
                <div className="d-flex align-items-center gap-1">
                  <label className="form-label small mb-0 me-1">Rango:</label>
                  <select
                    className="form-select form-select-sm"
                    style={{ width: "150px" }}
                    value={presetDate}
                    onChange={(e) => handlePresetDateChange(e.target.value as PresetDate)}
                  >
                    {PRESET_DATES.map((preset) => (
                      <option key={preset} value={preset}>
                        {preset}
                      </option>
                    ))}
                  </select>
                </div>
                {presetDate === "Custom" && (
                  <>
                    <div className="d-flex align-items-center gap-1">
                      <label className="form-label small mb-0 me-1">Inicio:</label>
                      <input
                        type="datetime-local"
                        className="form-control form-control-sm"
                        style={{ width: "180px" }}
                      value={startDate}
                      onChange={(e) => {
                        setStartDate(e.target.value);
                        localStorage.setItem("datalogger_startDate", e.target.value);
                      }}
                      />
                    </div>
                    <div className="d-flex align-items-center gap-1">
                      <label className="form-label small mb-0 me-1">Fin:</label>
                      <input
                        type="datetime-local"
                        className="form-control form-control-sm"
                        style={{ width: "180px" }}
                        value={endDate}
                        onChange={(e) => handleEndDateChange(e.target.value)}
                        max={new Date().toISOString().slice(0, 16)}
                      />
                    </div>
                  </>
                )}
                <div className="d-flex align-items-center gap-1">
                  <label className="form-label small mb-0 me-1">Sample:</label>
                  <select
                    className="form-select form-select-sm"
                    style={{ width: "120px" }}
                    value={sampleTime}
                    onChange={(e) => {
                      const newSampleTime = e.target.value as SampleTimeOption;
                      setSampleTime(newSampleTime);
                      localStorage.setItem("datalogger_sampleTime", newSampleTime);
                    }}
                  >
                    {SAMPLE_TIME_OPTIONS.map((option) => (
                      <option key={option} value={option}>
                        {option}
                      </option>
                    ))}
                  </select>
                </div>
                <Button variant="primary" className="btn-sm" onClick={handleApplyFilters} disabled={loading}>
                  Aplicar
                </Button>
                <Button
                  variant="primary"
                  className="btn-sm"
                  onClick={handleExportCSV}
                  disabled={loading || !tabularData || !tabularData.values || tabularData.values.length === 0}
                >
                  <i className="bi bi-download me-1"></i>
                  CSV
                </Button>
              </div>
            </div>
          }
          footer={
            <div className="d-flex justify-content-between align-items-center">
              <div className="d-flex align-items-center gap-2">
                <label className="mb-0 small">Items por página:</label>
                <select
                  className="form-select form-select-sm"
                  style={{ width: "auto" }}
                  value={pagination.limit}
                  onChange={(e) => handleLimitChange(Number(e.target.value))}
                  disabled={loading}
                >
                  <option value={10}>10</option>
                  <option value={20}>20</option>
                  <option value={50}>50</option>
                  <option value={100}>100</option>
                </select>
              </div>
              <div className="d-flex align-items-center gap-2">
                <span className="small text-muted">
                  Página {pagination.page} de {pagination.pages} ({pagination.total} total)
                </span>
                <div className="btn-group" role="group">
                  <Button
                    variant="secondary"
                    className="btn-sm"
                    onClick={() => handlePageChange(1)}
                    disabled={loading || pagination.page === 1}
                  >
                    «
                  </Button>
                  <Button
                    variant="secondary"
                    className="btn-sm"
                    onClick={() => handlePageChange(pagination.page - 1)}
                    disabled={loading || pagination.page === 1}
                  >
                    ‹
                  </Button>
                  <Button
                    variant="secondary"
                    className="btn-sm"
                    onClick={() => handlePageChange(pagination.page + 1)}
                    disabled={loading || pagination.page >= pagination.pages}
                  >
                    ›
                  </Button>
                  <Button
                    variant="secondary"
                    className="btn-sm"
                    onClick={() => handlePageChange(pagination.pages)}
                    disabled={loading || pagination.page >= pagination.pages}
                  >
                    »
                  </Button>
                </div>
              </div>
            </div>
          }
        >
          {error && (
            <div className="alert alert-danger mb-3" role="alert">
              {error}
            </div>
          )}

          {/* Filtro de tags */}
          <div className="mb-3">
            <div className="d-flex align-items-center gap-2 flex-wrap">
              <label className="form-label mb-0 me-2">Tag Names:</label>
              <div className="d-flex align-items-center gap-2 flex-wrap">
                {availableTags.map((tag) => {
                  const isSelected = selectedTags.includes(tag.name);
                  return (
                    <button
                      key={tag.name}
                      type="button"
                      className={`btn btn-sm ${isSelected ? "btn-primary" : "btn-outline-secondary"}`}
                      onClick={() => {
                        const newSelectedTags = isSelected
                          ? selectedTags.filter((t) => t !== tag.name)
                          : [...selectedTags, tag.name];
                        setSelectedTags(newSelectedTags);
                        localStorage.setItem("datalogger_selectedTags", JSON.stringify(newSelectedTags));
                      }}
                    >
                      {tag.display_name || tag.name}
                    </button>
                  );
                })}
              </div>
            </div>
          </div>

          {loading && (
            <div className="text-center py-4">
              <div className="spinner-border text-primary" role="status">
                <span className="visually-hidden">Cargando...</span>
              </div>
            </div>
          )}

          {!loading && tabularData && (
            <div className="table-responsive" style={{ maxHeight: "70vh", overflowY: "auto" }}>
              <table className="table table-striped table-hover table-sm">
                <thead className="table-light" style={{ position: "sticky", top: 0, zIndex: 10 }}>
                  <tr>
                    {tabularData.display_names && tabularData.display_names.length > 0
                      ? tabularData.display_names.map((name, idx) => (
                          <th key={idx}>{name}</th>
                        ))
                      : tabularData.tag_names?.map((name, idx) => (
                          <th key={idx}>{name}</th>
                        ))}
                  </tr>
                </thead>
                <tbody>
                  {!tabularData.values || tabularData.values.length === 0 ? (
                    <tr>
                      <td
                        colSpan={
                          tabularData.display_names?.length || tabularData.tag_names?.length || 1
                        }
                        className="text-center text-muted py-4"
                      >
                        No hay datos disponibles
                      </td>
                    </tr>
                  ) : (
                    tabularData.values.map((row, rowIdx) => (
                      <tr key={rowIdx}>
                        {row.map((cell, cellIdx) => (
                          <td key={cellIdx}>{cell !== null && cell !== undefined ? String(cell) : "-"}</td>
                        ))}
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
          )}
        </Card>
      </div>
    </div>
  );
}
