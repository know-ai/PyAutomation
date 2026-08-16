import { useEffect, useMemo, useState, useRef } from "react";
import { Card } from "../components/Card";
import { Button } from "../components/Button";
import { MultiSelectSearch } from "../components/MultiSelectSearch";
import {
  filterAlarmsSummary,
  getAlarmSummaryComments,
  type AlarmSummary,
  type AlarmSummaryFilter,
  type AlarmSummaryResponse,
} from "../services/alarms";
import { createLog } from "../services/logs";
import { isDbUnavailableError } from "../services/health";
import { useTranslation } from "../hooks/useTranslation";
import { useDisplayTimezone } from "../hooks/useDisplayTimezone";
import { formatDateTimeLocalForBackend, formatDateTimeLocalInput } from "../utils/timezone";

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
      start = new Date(end.getTime() - 60 * 60 * 1000);
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
      // Aproximadamente 30 días
      start = new Date(end.getTime() - 30 * 24 * 60 * 60 * 1000);
      break;
    case "Custom":
      // No hacer nada, usar las fechas personalizadas
      break;
  }

  return { start, end };
};

export function AlarmsSummary() {
  const { t } = useTranslation();
  const { timeZone } = useDisplayTimezone();
  const [alarmsSummary, setAlarmsSummary] = useState<AlarmSummary[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [pagination, setPagination] = useState({
    page: 1,
    limit: 20,
    total: 0,
    pages: 0,
  });

  // Filtros
  const [filters, setFilters] = useState<AlarmSummaryFilter>(() => {
    const savedPage = localStorage.getItem("alarms_summary_page");
    const savedLimit = localStorage.getItem("alarms_summary_limit");
    return {
      page: savedPage ? Number(savedPage) : 1,
      limit: savedLimit ? Number(savedLimit) : 20,
    };
  });

  // Opciones para los filtros
  const [availableStates, setAvailableStates] = useState<string[]>([]);

  // Valores seleccionados en los filtros
  const [selectedStates, setSelectedStates] = useState<string[]>(() => {
    const saved = localStorage.getItem("alarms_summary_selectedStates");
    return saved ? JSON.parse(saved) : [];
  });
  const [presetDate, setPresetDate] = useState<PresetDate>(() => {
    const saved = localStorage.getItem("alarms_summary_presetDate");
    return (saved as PresetDate) || "Last Hour";
  });
  const [startDate, setStartDate] = useState<string>(() => {
    return localStorage.getItem("alarms_summary_startDate") || "";
  });
  const [endDate, setEndDate] = useState<string>(() => {
    return localStorage.getItem("alarms_summary_endDate") || "";
  });

  // Estado para el menú contextual y comentarios
  const [contextMenu, setContextMenu] = useState<{
    visible: boolean;
    x: number;
    y: number;
    alarmId: number | undefined;
  }>({
    visible: false,
    x: 0,
    y: 0,
    alarmId: undefined,
  });
  const [selectedAlarmId, setSelectedAlarmId] = useState<number | undefined>(undefined);
  const [showCommentModal, setShowCommentModal] = useState(false);
  const [commentMessage, setCommentMessage] = useState("");
  const [addingComment, setAddingComment] = useState(false);
  const contextMenuRef = useRef<HTMLDivElement>(null);
  
  // Estado para el modal de visualización de comentarios
  const [showCommentsModal, setShowCommentsModal] = useState(false);
  const [selectedAlarmForComments, setSelectedAlarmForComments] = useState<AlarmSummary | null>(null);
  const [comments, setComments] = useState<any[]>([]);
  const [loadingComments, setLoadingComments] = useState(false);

  // Cargar opciones para los filtros
  useEffect(() => {
    loadFilterOptions();
  }, []);

  // Cargar datos cuando cambian los filtros
  useEffect(() => {
    loadAlarmsSummary();
  }, [filters, timeZone]);

  // Cerrar menú contextual al hacer click fuera
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (contextMenuRef.current && !contextMenuRef.current.contains(event.target as Node)) {
        setContextMenu({ visible: false, x: 0, y: 0, alarmId: undefined });
      }
    };

    if (contextMenu.visible) {
      document.addEventListener("mousedown", handleClickOutside);
      return () => {
        document.removeEventListener("mousedown", handleClickOutside);
      };
    }
  }, [contextMenu.visible]);

  // Función helper para convertir Date a formato datetime-local (sin UTC)
  const formatToLocalDateTime = (date: Date): string => formatDateTimeLocalInput(date);

  // Función para convertir el formato de fecha del input al formato esperado por el backend
  const formatDateTimeForBackend = (dateTimeString: string): string => {
    return formatDateTimeLocalForBackend(dateTimeString, timeZone);
  };

  const loadFilterOptions = async () => {
    try {
      // Estados comunes de alarmas (ISA 18.2)
      const commonStates = [
        "Normal",
        "Unacknowledged",
        "Acknowledged",
        "RTN Unacknowledged",
        "Shelved",
        "Suppressed By Design",
        "Out Of Service",
      ];
      setAvailableStates(commonStates);

      // Establecer fechas por defecto solo si no hay fechas guardadas
      if (!startDate || !endDate) {
        const { start, end } = getPresetDateRange("Last Hour");
        const now = new Date();
        const finalEnd = end > now ? now : end;
        const startStr = formatToLocalDateTime(start);
        const endStr = formatToLocalDateTime(finalEnd);
        setEndDate(endStr);
        setStartDate(startStr);
        localStorage.setItem("alarms_summary_startDate", startStr);
        localStorage.setItem("alarms_summary_endDate", endStr);
      }
    } catch (e: any) {
      console.error("Error loading filter options:", e);
    }
  };

  const loadAlarmsSummary = async () => {
    setLoading(true);
    setError(null);
    try {
      const payload: AlarmSummaryFilter = {
        ...filters,
      };

      // Agregar filtros solo si tienen valores
      if (selectedStates.length > 0) {
        payload.states = selectedStates;
      }
      if (startDate) {
        payload.greater_than_timestamp = formatDateTimeForBackend(startDate);
      }
      if (endDate) {
        payload.less_than_timestamp = formatDateTimeForBackend(endDate);
      }
      if (timeZone) {
        payload.timezone = timeZone;
      }

      const response: AlarmSummaryResponse = await filterAlarmsSummary(payload);
      setAlarmsSummary(response.data || []);
      setPagination({
        page: response.pagination?.page || 1,
        limit: response.pagination?.limit || 20,
        total: response.pagination?.total_records || 0,
        pages: response.pagination?.total_pages || 0,
      });
    } catch (e: any) {
      if (isDbUnavailableError(e)) {
        setError(null);
        setAlarmsSummary([]);
        return;
      }
      const data = e?.response?.data;
      const backendMessage =
        (typeof data === "string" ? data : undefined) ??
        data?.message ??
        data?.detail ??
        data?.error;
      const errorMsg =
        backendMessage || e?.message || t("alarmsSummary.loadError");
      setError(errorMsg);
      setAlarmsSummary([]);
    } finally {
      setLoading(false);
    }
  };

  const handleApplyFilters = () => {
    if (presetDate !== "Custom") {
      const { start, end } = getPresetDateRange(presetDate);
      const startStr = formatToLocalDateTime(start);
      const endStr = formatToLocalDateTime(end);
      setStartDate(startStr);
      setEndDate(endStr);
      localStorage.setItem("alarms_summary_startDate", startStr);
      localStorage.setItem("alarms_summary_endDate", endStr);
    }
    const newFilters = {
      ...filters,
      page: 1,
    };
    setFilters(newFilters);
    localStorage.setItem("alarms_summary_page", "1");
    localStorage.setItem("alarms_summary_limit", String(newFilters.limit || 20));
  };

  const stateOptions = useMemo(
    () =>
      availableStates.map((state) => ({
        value: state,
        label: t(`alarmsSummary.states.${state}`),
      })),
    [availableStates, t]
  );

  const handleStatesChange = (next: string[]) => {
    setSelectedStates(next);
    localStorage.setItem("alarms_summary_selectedStates", JSON.stringify(next));
  };

  const handlePresetDateChange = (preset: PresetDate) => {
    setPresetDate(preset);
    localStorage.setItem("alarms_summary_presetDate", preset);
    if (preset !== "Custom") {
      const { start, end } = getPresetDateRange(preset);
      const now = new Date();
      // Asegurar que la fecha final no exceda la actual
      const finalEnd = end > now ? now : end;
      const startStr = formatToLocalDateTime(start);
      const endStr = formatToLocalDateTime(finalEnd);
      setStartDate(startStr);
      setEndDate(endStr);
      localStorage.setItem("alarms_summary_startDate", startStr);
      localStorage.setItem("alarms_summary_endDate", endStr);
    }
  };

  const handleEndDateChange = (value: string) => {
    const selectedEnd = new Date(value);
    const now = new Date();
    
    // Validar que la fecha final no exceda la actual
    const finalValue = selectedEnd > now ? formatToLocalDateTime(now) : value;
    setEndDate(finalValue);
    localStorage.setItem("alarms_summary_endDate", finalValue);
  };

  const handleClearFilters = () => {
    setSelectedStates([]);
    localStorage.removeItem("alarms_summary_selectedStates");
    setPresetDate("Last Hour");
    localStorage.setItem("alarms_summary_presetDate", "Last Hour");
    const { start, end } = getPresetDateRange("Last Hour");
    const now = new Date();
    const finalEnd = end > now ? now : end;
    const startStr = formatToLocalDateTime(start);
    const endStr = formatToLocalDateTime(finalEnd);
    setEndDate(endStr);
    setStartDate(startStr);
    localStorage.setItem("alarms_summary_startDate", startStr);
    localStorage.setItem("alarms_summary_endDate", endStr);
    setFilters({
      page: 1,
      limit: 20,
    });
    localStorage.setItem("alarms_summary_page", "1");
    localStorage.setItem("alarms_summary_limit", "20");
  };

  const handlePageChange = (newPage: number) => {
    if (newPage >= 1 && newPage <= pagination.pages) {
      setFilters({ ...filters, page: newPage });
      localStorage.setItem("alarms_summary_page", String(newPage));
    }
  };

  const handleLimitChange = (newLimit: number) => {
    if (newLimit > 0) {
      setFilters({ ...filters, page: 1, limit: newLimit });
      localStorage.setItem("alarms_summary_page", "1");
      localStorage.setItem("alarms_summary_limit", String(newLimit));
    }
  };

  const handleRowContextMenu = (e: React.MouseEvent, alarm: AlarmSummary) => {
    e.preventDefault();
    const alarmId = typeof alarm.id === "number" ? alarm.id : typeof alarm.id === "string" ? Number(alarm.id) : undefined;
    setContextMenu({
      visible: true,
      x: e.clientX,
      y: e.clientY,
      alarmId: alarmId || undefined,
    });
  };

  const handleAddComment = () => {
    if (contextMenu.alarmId) {
      setSelectedAlarmId(contextMenu.alarmId);
      setShowCommentModal(true);
    }
    setContextMenu({ visible: false, x: 0, y: 0, alarmId: undefined });
  };

  const handleSaveComment = async () => {
    if (!commentMessage.trim() || !selectedAlarmId) {
      setError(t("alarmsSummary.messageRequired"));
      return;
    }

    setAddingComment(true);
    setError(null);
    try {
      await createLog({
        message: commentMessage.trim(),
        alarm_summary_id: selectedAlarmId,
      });
      setCommentMessage("");
      setShowCommentModal(false);
      setSelectedAlarmId(undefined);
      // Recargar alarmas para actualizar has_comments
      loadAlarmsSummary();
    } catch (e: any) {
      const data = e?.response?.data;
      const backendMessage =
        (typeof data === "string" ? data : undefined) ??
        data?.message ??
        data?.detail ??
        data?.error;
      const errorMsg =
        backendMessage || e?.message || t("alarmsSummary.addCommentError");
      setError(errorMsg);
    } finally {
      setAddingComment(false);
    }
  };

  const handleCancelComment = () => {
    setShowCommentModal(false);
    setCommentMessage("");
    setSelectedAlarmId(undefined);
  };

  const handleViewComments = async (alarm: AlarmSummary) => {
    if (!alarm.id) return;
    
    setSelectedAlarmForComments(alarm);
    setShowCommentsModal(true);
    setLoadingComments(true);
    setError(null);
    
    try {
      const alarmId = typeof alarm.id === "string" ? Number(alarm.id) : alarm.id;
      const commentsData = await getAlarmSummaryComments(alarmId);
      setComments(commentsData || []);
    } catch (e: any) {
      const data = e?.response?.data;
      const backendMessage =
        (typeof data === "string" ? data : undefined) ??
        data?.message ??
        data?.detail ??
        data?.error;
      const errorMsg =
        backendMessage || e?.message || t("alarmsSummary.loadCommentsError");
      setError(errorMsg);
      setComments([]);
    } finally {
      setLoadingComments(false);
    }
  };

  const handleExportCommentsCSV = () => {
    if (!comments || comments.length === 0) {
      setError(t("alarmsSummary.noCommentsToExport"));
      return;
    }

    try {
      // Preparar los datos para CSV
      const headers = [
        t("tables.id"),
        t("tables.timestamp"),
        t("tables.user"),
        t("tables.message"),
        t("tables.description"),
        t("tables.classification"),
        t("tables.alarm"),
      ];

      // Convertir comentarios a filas CSV
      const rows = comments.map((comment: any) => {
        return [
          comment.id || "",
          comment.timestamp || "",
          comment.user?.username || "",
          comment.message || "",
          comment.description || "",
          comment.classification || "",
          comment.alarm?.name || "",
        ];
      });

      // Crear contenido CSV
      const csvContent = [
        headers.join(","),
        ...rows.map((row) =>
          row
            .map((cell) => {
              // Escapar comillas y envolver en comillas si contiene comas o comillas
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
        `alarm_comments_${selectedAlarmForComments?.name || "alarm"}_${new Date().toISOString().split("T")[0]}.csv`
      );
      link.style.visibility = "hidden";

      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);

      URL.revokeObjectURL(url);
    } catch (e: any) {
      const errorMsg = e?.message || t("alarmsSummary.exportCommentsError");
      setError(errorMsg);
    }
  };

  const handleExportCSV = async () => {
    try {
      setError(null);
      
      // Obtener todos los datos con los filtros actuales (sin límite de página)
      const payload: AlarmSummaryFilter = {
        ...filters,
        page: 1,
        limit: 10000, // Obtener todos los registros
      };

      if (selectedStates.length > 0) {
        payload.states = selectedStates;
      }
      if (startDate) {
        payload.greater_than_timestamp = formatDateTimeForBackend(startDate);
      }
      if (endDate) {
        payload.less_than_timestamp = formatDateTimeForBackend(endDate);
      }
      if (timeZone) {
        payload.timezone = timeZone;
      }

      const response: AlarmSummaryResponse = await filterAlarmsSummary(payload);
      const allAlarms = response.data || [];

      if (!allAlarms || allAlarms.length === 0) {
        setError(t("alarmsSummary.noDataToExport"));
        return;
      }

      // Preparar los datos para CSV
      const headers = [
        t("tables.id"),
        t("tables.name"),
        t("tables.tag"),
        t("tables.description"),
        t("tables.status"),
        t("tables.alarmDateTime"),
        t("tables.ackDateTime"),
        t("alarmsSummary.hasComments"),
      ];

      // Convertir alarmas a filas CSV
      const rows = allAlarms.map((alarm: AlarmSummary) => {
        return [
          alarm.id || "",
          alarm.name || "",
          alarm.tag || "",
          alarm.description || "",
          alarm.state || "",
          alarm.alarm_time || "",
          alarm.ack_time || "",
          alarm.has_comments ? t("common.yes") : t("common.no"),
        ];
      });

      // Crear contenido CSV
      const csvContent = [
        headers.join(","),
        ...rows.map((row) =>
          row
            .map((cell) => {
              // Escapar comillas y envolver en comillas si contiene comas o comillas
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
        `alarms_summary_${new Date().toISOString().split("T")[0]}.csv`
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
        backendMessage ||
        e?.message ||
        t("alarmsSummary.exportError");
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
                <span className="me-auto">{t("navigation.alarmsSummary")}</span>
                <div className="d-flex align-items-center gap-2 flex-wrap">
                  <div className="d-flex align-items-center gap-1">
                    <label className="form-label small mb-0 me-1">{t("alarmsSummary.state")}:</label>
                    <MultiSelectSearch
                      options={stateOptions}
                      selected={selectedStates}
                      onChange={handleStatesChange}
                      placeholder={t("alarmsSummary.selectStatesPlaceholder")}
                      searchPlaceholder={t("alarmsSummary.searchStates")}
                      emptyText={t("alarmsSummary.noStatesFound")}
                      selectAllLabel={t("alarmsSummary.selectAll")}
                      clearLabel={t("common.clear")}
                      selectedCountLabel={(count) => t("alarmsSummary.selectedCount", { count })}
                      disabled={loading}
                      style={{ width: "200px", maxWidth: "100%" }}
                    />
                  </div>
                  <div className="d-flex align-items-center gap-1">
                    <label className="form-label small mb-0 me-1">{t("alarmsSummary.range")}:</label>
                    <select
                      className="form-select form-select-sm"
                      style={{ width: "150px", maxWidth: "100%" }}
                      value={presetDate}
                      onChange={(e) => handlePresetDateChange(e.target.value as PresetDate)}
                    >
                      {PRESET_DATES.map((preset) => (
                        <option key={preset} value={preset}>
                          {t(`alarmsSummary.preset.${preset}`)}
                        </option>
                      ))}
                    </select>
                  </div>
                  <Button variant="primary" className="btn-sm" onClick={handleApplyFilters} disabled={loading}>
                    {t("common.filter")}
                  </Button>
                  <Button
                    variant="primary"
                    className="btn-sm"
                    onClick={handleExportCSV}
                    disabled={loading || alarmsSummary.length === 0}
                  >
                    <i className="bi bi-download me-1"></i>
                    CSV
                  </Button>
                  <Button variant="secondary" className="btn-sm" onClick={handleClearFilters} disabled={loading}>
                    {t("common.clear")}
                  </Button>
                </div>
              </div>
              {presetDate === "Custom" && (
                <div className="card-header-stack__row d-flex align-items-center gap-2 flex-wrap pt-2 mt-1 border-top">
                  <div className="d-flex align-items-center gap-1">
                    <label className="form-label small mb-0 me-1">{t("alarmsSummary.start")}:</label>
                    <input
                      type="datetime-local"
                      step="1"
                      className="form-control form-control-sm"
                      style={{ width: "180px", maxWidth: "100%" }}
                      value={startDate}
                      onChange={(e) => {
                        setStartDate(e.target.value);
                        localStorage.setItem("alarms_summary_startDate", e.target.value);
                      }}
                    />
                  </div>
                  <div className="d-flex align-items-center gap-1">
                    <label className="form-label small mb-0 me-1">{t("alarmsSummary.end")}:</label>
                    <input
                      type="datetime-local"
                      step="1"
                      className="form-control form-control-sm"
                      style={{ width: "180px", maxWidth: "100%" }}
                      value={endDate}
                      onChange={(e) => handleEndDateChange(e.target.value)}
                      max={new Date().toISOString().slice(0, 16)}
                    />
                  </div>
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

          {loading && (
            <div className="text-center py-4">
              <div className="spinner-border text-primary" role="status">
                <span className="visually-hidden">{t("common.loading")}</span>
              </div>
            </div>
          )}

          {!loading && (
            <div className="table-responsive">
              <table className="table table-striped table-hover table-sm">
                <thead>
                  <tr>
                    <th>{t("tables.id")}</th>
                    <th>{t("tables.name")}</th>
                    <th>{t("tables.tag")}</th>
                    <th>{t("tables.description")}</th>
                    <th>{t("tables.status")}</th>
                    <th>{t("tables.alarmDateTime")}</th>
                    <th>{t("tables.ackDateTime")}</th>
                    <th>{t("tables.comments")}</th>
                  </tr>
                </thead>
                <tbody>
                  {alarmsSummary.length === 0 ? (
                    <tr>
                      <td colSpan={8} className="text-center text-muted py-4">
                        {t("alarmsSummary.noAlarmsAvailable")}
                      </td>
                    </tr>
                  ) : (
                    alarmsSummary.map((alarm) => (
                      <tr
                        key={alarm.id}
                        onContextMenu={(e) => handleRowContextMenu(e, alarm)}
                        style={{ cursor: "context-menu" }}
                      >
                        <td>{alarm.id || "-"}</td>
                        <td>
                          <strong>{alarm.name || "-"}</strong>
                        </td>
                        <td>{alarm.tag || "-"}</td>
                        <td>{alarm.description || "-"}</td>
                        <td>
                          <span className="badge bg-secondary">{alarm.state || "-"}</span>
                        </td>
                        <td>{alarm.alarm_time || "-"}</td>
                        <td>{alarm.ack_time || "-"}</td>
                        <td>
                          {alarm.has_comments ? (
                            <i 
                              className="bi bi-check-circle text-success" 
                              title={t("alarmsSummary.hasCommentsClick")}
                              style={{ cursor: "pointer" }}
                              onClick={() => handleViewComments(alarm)}
                            ></i>
                          ) : (
                            <i className="bi bi-x-circle text-muted" title={t("alarmsSummary.noComments")}></i>
                          )}
                        </td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
          )}

          {/* Menú contextual */}
          {contextMenu.visible && (
            <div
              ref={contextMenuRef}
              className="dropdown-menu show"
              style={{
                position: "fixed",
                top: `${contextMenu.y}px`,
                left: `${contextMenu.x}px`,
                zIndex: 1000,
              }}
            >
              <button
                className="dropdown-item"
                onClick={handleAddComment}
              >
                <i className="bi bi-chat-left-text me-2"></i>
                {t("alarmsSummary.addComment")}
              </button>
            </div>
          )}

          {/* Modal para agregar comentario */}
          {showCommentModal && (
            <div
              className="modal show d-block"
              style={{ backgroundColor: "rgba(0,0,0,0.5)" }}
              onClick={handleCancelComment}
            >
              <div className="modal-dialog" onClick={(e) => e.stopPropagation()}>
                <div className="modal-content">
                  <div className="modal-header">
                    <h5 className="modal-title">{t("alarmsSummary.addCommentTitle")}</h5>
                    <button
                      type="button"
                      className="btn-close"
                      onClick={handleCancelComment}
                    ></button>
                  </div>
                  <div className="modal-body">
                    <div className="mb-3">
                      <label className="form-label">{t("alarmsSummary.messageLabel")}</label>
                      <textarea
                        className="form-control"
                        rows={4}
                        value={commentMessage}
                        onChange={(e) => setCommentMessage(e.target.value)}
                        placeholder={t("alarmsSummary.commentPlaceholder")}
                      />
                    </div>
                  </div>
                  <div className="modal-footer">
                    <Button
                      variant="secondary"
                      onClick={handleCancelComment}
                      disabled={addingComment}
                    >
                      {t("common.cancel")}
                    </Button>
                    <Button
                      variant="primary"
                      onClick={handleSaveComment}
                      disabled={addingComment || !commentMessage.trim()}
                      loading={addingComment}
                    >
                      {t("alarmsSummary.add")}
                    </Button>
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* Modal para visualizar comentarios */}
          {showCommentsModal && selectedAlarmForComments && (
            <div
              className="modal show d-block"
              style={{ backgroundColor: "rgba(0,0,0,0.5)" }}
              onClick={() => {
                setShowCommentsModal(false);
                setSelectedAlarmForComments(null);
                setComments([]);
              }}
            >
              <div className="modal-dialog modal-xl" onClick={(e) => e.stopPropagation()}>
                <div className="modal-content">
                  <div className="modal-header d-flex justify-content-between align-items-center w-100">
                    <h5 className="modal-title mb-0">
                      {t("alarmsSummary.commentsTitle", { name: selectedAlarmForComments.name || t("tables.alarm") })}
                    </h5>
                    <div className="d-flex align-items-center gap-2">
                      <Button
                        variant="primary"
                        className="btn-sm"
                        onClick={handleExportCommentsCSV}
                        disabled={loadingComments || comments.length === 0}
                      >
                        <i className="bi bi-download me-1"></i>
                        CSV
                      </Button>
                      <button
                        type="button"
                        className="btn-close"
                        onClick={() => {
                          setShowCommentsModal(false);
                          setSelectedAlarmForComments(null);
                          setComments([]);
                        }}
                      ></button>
                    </div>
                  </div>
                  <div className="modal-body">
                    {loadingComments ? (
                      <div className="text-center py-4">
                        <div className="spinner-border text-primary" role="status">
                          <span className="visually-hidden">{t("common.loading")}</span>
                        </div>
                      </div>
                    ) : (
                      <div className="table-responsive" style={{ maxHeight: "60vh", overflowY: "auto" }}>
                        <table className="table table-striped table-hover table-sm">
                          <thead className="table-light" style={{ position: "sticky", top: 0, zIndex: 10 }}>
                            <tr>
                              <th>{t("tables.id")}</th>
                              <th>{t("tables.timestamp")}</th>
                              <th>{t("tables.user")}</th>
                              <th>{t("tables.message")}</th>
                              <th>{t("tables.description")}</th>
                              <th>{t("tables.classification")}</th>
                              <th>{t("tables.alarm")}</th>
                            </tr>
                          </thead>
                          <tbody>
                            {comments.length === 0 ? (
                              <tr>
                                <td colSpan={7} className="text-center text-muted py-4">
                                  {t("alarmsSummary.noCommentsAvailable")}
                                </td>
                              </tr>
                            ) : (
                              comments.map((comment) => (
                                <tr key={comment.id}>
                                  <td>{comment.id || "-"}</td>
                                  <td>{comment.timestamp || "-"}</td>
                                  <td>{comment.user?.username || "-"}</td>
                                  <td>{comment.message || "-"}</td>
                                  <td>{comment.description || "-"}</td>
                                  <td>{comment.classification || "-"}</td>
                                  <td>{comment.alarm?.name || "-"}</td>
                                </tr>
                              ))
                            )}
                          </tbody>
                        </table>
                      </div>
                    )}
                  </div>
                  <div className="modal-footer">
                    <Button
                      variant="secondary"
                      onClick={() => {
                        setShowCommentsModal(false);
                        setSelectedAlarmForComments(null);
                        setComments([]);
                      }}
                    >
                      {t("common.close")}
                    </Button>
                  </div>
                </div>
              </div>
            </div>
          )}
        </Card>
      </div>
    </div>
  );
}
