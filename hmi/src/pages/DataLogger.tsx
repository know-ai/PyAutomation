import { useEffect, useMemo, useState } from "react";
import { Card } from "../components/Card";
import { Button } from "../components/Button";
import { HistoryResults } from "../components/HistoryResults";
import { MultiSelectSearch } from "../components/MultiSelectSearch";
import { AreaFilter } from "../components/AreaFilter";
import {
  getHistorianCatalog,
  getTabularData,
  type Tag,
  type TabularDataFilter,
  type TabularDataResponse,
} from "../services/tags";
import { isDbUnavailableError } from "../services/health";
import { useTranslation } from "../hooks/useTranslation";
import { useDisplayTimezone } from "../hooks/useDisplayTimezone";
import { usePlantAreas } from "../hooks/usePlantAreas";
import {
  FILTER_DATE_MS,
  FILTER_HEAVY_MS,
  FILTER_INSTANT_MS,
  isRequestCanceled,
  useScheduledQuery,
  type ScheduledQueryContext,
} from "../hooks/useScheduledQuery";
import { formatDateTimeLocalForBackend, formatDateTimeLocalInput, formatOperatorTimestamp, type UiLocale } from "../utils/timezone";
import { readSessionTags, writeSessionTags } from "../utils/sessionFilters";

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

const DATALOGGER_TIME_OPTS = { fractionalDigits: 3 as const };

const formatDataloggerCell = (cell: unknown, cellIdx: number, locale: UiLocale): string => {
  if (cell === null || cell === undefined) return "-";
  if (cellIdx === 0) {
    return formatOperatorTimestamp(String(cell), locale, DATALOGGER_TIME_OPTS);
  }
  return String(cell);
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
  const { t, locale } = useTranslation();
  const { timeZone } = useDisplayTimezone();
  const plantAreas = usePlantAreas();
  const { schedule, flushPending, setRunner, isCurrent } = useScheduledQuery();
  const [tabularData, setTabularData] = useState<TabularDataResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [hasLoaded, setHasLoaded] = useState(false);
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
  const [selectedTags, setSelectedTags] = useState<string[]>(() => readSessionTags("datalogger_selectedTags"));
  const [selectedArea, setSelectedArea] = useState("");
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

  // Cargar opciones para los filtros
  useEffect(() => {
    loadFilterOptions();
  }, [selectedArea]);

  useEffect(() => {
    setRunner((ctx) => loadTabularData(ctx));
  });

  useEffect(() => {
    schedule(FILTER_INSTANT_MS);
  }, [timeZone, schedule]);

  const loadFilterOptions = async () => {
    try {
      // Catálogo completo (lista slim) para el selector; fallback paginado si falla.
      let allTags: Tag[] = [];
      try {
        allTags = await getHistorianCatalog(selectedArea || undefined);
      } catch (_e) {
        allTags = [];
      }
      setAvailableTags(allTags);

      if (selectedTags.length > 0) {
        // Validar que los tags de esta sesión aún existan
        const validTags = selectedTags.filter(tagName => 
          allTags.some(tag => tag.name === tagName)
        );
        if (validTags.length !== selectedTags.length) {
          setSelectedTags(validTags);
          writeSessionTags("datalogger_selectedTags", validTags);
        }
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
        schedule(FILTER_INSTANT_MS);
      }
    } catch (e: any) {
      console.error("Error loading filter options:", e);
    }
  };

  // Función helper para convertir Date a formato datetime-local (sin UTC)
  const formatToLocalDateTime = (date: Date): string => formatDateTimeLocalInput(date);

  const formatDateTimeForBackend = (dateTimeString: string): string => {
    return formatDateTimeLocalForBackend(dateTimeString, timeZone);
  };

  const resolveQueryWindow = (): { start: string; end: string } => {
    if (presetDate !== "Custom") {
      const { start, end } = getPresetDateRange(presetDate);
      const now = new Date();
      const finalEnd = end > now ? now : end;
      return {
        start: formatToLocalDateTime(start),
        end: formatToLocalDateTime(finalEnd),
      };
    }
    return { start: startDate, end: endDate };
  };

  const resetToFirstPage = () => {
    setFilters((prev) => (prev.page === 1 ? prev : { ...prev, page: 1 }));
  };

  const handlePresetDateChange = (preset: PresetDate) => {
    setPresetDate(preset);
    localStorage.setItem("datalogger_presetDate", preset);
    if (preset !== "Custom") {
      const { start, end } = getPresetDateRange(preset);
      const now = new Date();
      const finalEnd = end > now ? now : end;
      const startStr = formatToLocalDateTime(start);
      const endStr = formatToLocalDateTime(finalEnd);
      setStartDate(startStr);
      setEndDate(endStr);
      localStorage.setItem("datalogger_startDate", startStr);
      localStorage.setItem("datalogger_endDate", endStr);
      resetToFirstPage();
      schedule(FILTER_INSTANT_MS);
    }
  };

  const handleEndDateChange = (value: string) => {
    const selectedEnd = new Date(value);
    const now = new Date();
    const finalValue = selectedEnd > now ? formatToLocalDateTime(now) : value;
    setEndDate(finalValue);
    localStorage.setItem("datalogger_endDate", finalValue);
    resetToFirstPage();
    schedule(FILTER_DATE_MS);
  };

  const loadTabularData = async ({ signal, generation }: ScheduledQueryContext) => {
    if (selectedTags.length === 0) {
      setTabularData(null);
      setError(null);
      setHasLoaded(true);
      setLoading(false);
      return;
    }

    const queryWindow = resolveQueryWindow();
    if (!queryWindow.start || !queryWindow.end) {
      setHasLoaded(true);
      setLoading(false);
      return;
    }

    setLoading(true);
    setError(null);
    try {
      const payload: TabularDataFilter = {
        tags: selectedTags,
        greater_than_timestamp: formatDateTimeForBackend(queryWindow.start),
        less_than_timestamp: formatDateTimeForBackend(queryWindow.end),
        sample_time: sampleTimeToSeconds(sampleTime),
        page: filters.page || 1,
        limit: filters.limit || 20,
        timezone: timeZone,
      };

      const response: TabularDataResponse = await getTabularData(payload, { signal });
      if (!isCurrent(generation, signal)) return;
      setTabularData(response);
      setPagination({
        page: response.pagination?.page || 1,
        limit: response.pagination?.limit || 20,
        total: response.pagination?.total_records || 0,
        pages: response.pagination?.total_pages || 0,
      });
      setHasLoaded(true);
    } catch (e: any) {
      if (isRequestCanceled(e) || !isCurrent(generation, signal)) return;
      if (isDbUnavailableError(e)) {
        setError(null);
        setHasLoaded(true);
        return;
      }
      const data = e?.response?.data;
      const backendMessage =
        (typeof data === "string" ? data : undefined) ??
        data?.message ??
        data?.detail ??
        data?.error;
      const errorMsg = backendMessage || e?.message || t("dataLogger.loadError");
      setError(errorMsg);
      setHasLoaded(true);
    } finally {
      if (isCurrent(generation, signal)) {
        setLoading(false);
      }
    }
  };

  const handlePageChange = (newPage: number) => {
    if (newPage >= 1 && newPage <= pagination.pages) {
      setFilters({ ...filters, page: newPage });
      schedule(FILTER_INSTANT_MS);
    }
  };

  const handleSelectedTagsChange = (next: string[]) => {
    setSelectedTags(next);
    writeSessionTags("datalogger_selectedTags", next);
    resetToFirstPage();
    schedule(FILTER_HEAVY_MS);
  };

  const tagOptions = useMemo(
    () =>
      availableTags.map((tag) => ({
        value: tag.name,
        label: tag.area
          ? `${tag.display_name || tag.name} (${tag.area})`
          : tag.display_name || tag.name,
        description: tag.variable,
      })),
    [availableTags]
  );

  const handleLimitChange = (newLimit: number) => {
    if (newLimit > 0) {
      setFilters({ ...filters, page: 1, limit: newLimit });
      schedule(FILTER_INSTANT_MS);
    }
  };

  const handleExportCSV = async () => {
    if (!tabularData || !tabularData.values || tabularData.values.length === 0) {
      setError(t("dataLogger.noDataToExport"));
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
      payload.timezone = timeZone;

      const response: TabularDataResponse = await getTabularData(payload);
      const allData = response.values || [];
      const tagNames = response.tag_names || [];
      const displayNames = response.display_names || [];

      if (!allData || allData.length === 0) {
        setError(t("dataLogger.noDataToExport"));
        return;
      }

      // Preparar los datos para CSV
      const headers = displayNames.length > 0 ? displayNames : tagNames;

      // Convertir datos a filas CSV
      const rows = allData.map((row) => {
        return row.map((cell: any, cellIdx: number) => {
          if (cell === null || cell === undefined) return "";
          if (cellIdx === 0) {
            const formatted = formatOperatorTimestamp(String(cell), locale, DATALOGGER_TIME_OPTS);
            return formatted === "-" ? "" : formatted;
          }
          return String(cell);
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
      const data = e?.response?.data;
      const backendMessage =
        (typeof data === "string" ? data : undefined) ??
        data?.message ??
        data?.detail ??
        data?.error;
      const errorMsg =
        backendMessage || e?.message || t("dataLogger.exportError");
      setError(errorMsg);
    }
  };

  return (
    <div className="row g-0 page-fit-viewport">
      <div className="col-12 h-100">
        <Card
          className="page-fit-card"
          title={
            <div className="card-header-stack w-100">
              <div className="d-flex align-items-center gap-2 w-100 flex-wrap">
                <span className="me-auto">{t("navigation.dataLogger")}</span>
                <div className="d-flex align-items-center gap-2 flex-wrap">
                  <AreaFilter
                    value={selectedArea}
                    areas={plantAreas}
                    plantLabel={t("common.plantWide")}
                    onChange={(area) => {
                      setSelectedArea(area);
                      resetToFirstPage();
                    }}
                  />
                  <MultiSelectSearch
                    options={tagOptions}
                    selected={selectedTags}
                    onChange={handleSelectedTagsChange}
                    onClose={flushPending}
                    placeholder={t("dataLogger.selectTagsPlaceholder")}
                    searchPlaceholder={t("dataLogger.searchTags")}
                    emptyText={t("dataLogger.noTagsFound")}
                    selectAllLabel={t("dataLogger.selectAll")}
                    clearLabel={t("common.clear")}
                    selectedCountLabel={(count) =>
                      t("dataLogger.selectedCount", { count })
                    }
                    style={{ width: "220px", maxWidth: "100%" }}
                  />
                  <select
                    className="form-select form-select-sm"
                    style={{ width: "150px", maxWidth: "100%" }}
                    value={presetDate}
                    onChange={(e) => handlePresetDateChange(e.target.value as PresetDate)}
                  >
                    {PRESET_DATES.map((preset) => {
                      const presetKey = preset === "Last hour" ? "Lasthour" : preset.replace(/\s+/g, "");
                      return (
                        <option key={preset} value={preset}>
                          {t(`dataLogger.preset.${presetKey}`)}
                        </option>
                      );
                    })}
                  </select>
                  <div className="d-flex align-items-center gap-1">
                    <label className="form-label small mb-0 me-1">{t("dataLogger.sample")}:</label>
                    <select
                      className="form-select form-select-sm"
                      style={{ width: "120px", maxWidth: "100%" }}
                      value={sampleTime}
                      onChange={(e) => {
                        const newSampleTime = e.target.value as SampleTimeOption;
                        setSampleTime(newSampleTime);
                        localStorage.setItem("datalogger_sampleTime", newSampleTime);
                        resetToFirstPage();
                        schedule(FILTER_INSTANT_MS);
                      }}
                    >
                      {SAMPLE_TIME_OPTIONS.map((option) => (
                        <option key={option} value={option}>
                          {t(`dataLogger.sampleTime.${option.replace(/\s+/g, "")}`)}
                        </option>
                      ))}
                    </select>
                  </div>
                  <Button
                    variant="primary"
                    className="btn-sm"
                    onClick={handleExportCSV}
                    disabled={!tabularData || !tabularData.values || tabularData.values.length === 0}
                  >
                    <i className="bi bi-download me-1"></i>
                    {t("common.csv")}
                  </Button>
                </div>
              </div>
              {presetDate === "Custom" && (
                <div className="card-header-stack__row d-flex align-items-center gap-2 flex-wrap pt-2 mt-1 border-top">
                  <input
                    type="datetime-local"
                    step="1"
                    className="form-control form-control-sm"
                    style={{ width: "180px", maxWidth: "100%" }}
                    value={startDate}
                    onChange={(e) => {
                      setStartDate(e.target.value);
                      localStorage.setItem("datalogger_startDate", e.target.value);
                      resetToFirstPage();
                      schedule(FILTER_DATE_MS);
                    }}
                    onBlur={flushPending}
                  />
                  <input
                    type="datetime-local"
                    step="1"
                    className="form-control form-control-sm"
                    style={{ width: "180px", maxWidth: "100%" }}
                    value={endDate}
                    onChange={(e) => handleEndDateChange(e.target.value)}
                    onBlur={flushPending}
                    max={new Date().toISOString().slice(0, 16)}
                  />
                </div>
              )}
            </div>
          }
          footer={
            <div className="d-flex justify-content-between align-items-center">
              <div className="d-flex align-items-center gap-2">
                <label className="mb-0 small">{t("pagination.itemsPerPage")}</label>
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
                  {t("pagination.pageOf", {
                    current: pagination.page,
                    total: pagination.pages,
                    count: pagination.total,
                  })}
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

          <HistoryResults loading={loading} hasLoaded={hasLoaded} loadingLabel={t("common.loading")}>
            {tabularData ? (
            <div className="table-responsive">
              <table className="table table-striped table-hover table-sm">
                <thead>
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
                        {t("dataLogger.noDataAvailable")}
                      </td>
                    </tr>
                  ) : (
                    tabularData.values.map((row, rowIdx) => (
                      <tr key={rowIdx}>
                        {row.map((cell, cellIdx) => (
                          <td key={cellIdx}>{formatDataloggerCell(cell, cellIdx, locale)}</td>
                        ))}
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
            ) : (
              <div className="text-muted text-center py-4">{t("dataLogger.selectAtLeastOneTag")}</div>
            )}
          </HistoryResults>
        </Card>
      </div>
    </div>
  );
}
