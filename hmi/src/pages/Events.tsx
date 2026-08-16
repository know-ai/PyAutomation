import { useEffect, useMemo, useState, useRef } from "react";
import { Card } from "../components/Card";
import { Button } from "../components/Button";
import { MultiSelectSearch } from "../components/MultiSelectSearch";
import {
  filterEvents,
  getEventComments,
  type Event,
  type EventFilter,
  type EventResponse,
} from "../services/events";
import { getAllUsers, type User } from "../services/users";
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

/** Backend sends `%f` microseconds (6 digits). Table shows a single fractional second. */
function formatEventTimestamp(value?: string | null): string {
  if (!value) return "-";
  const dot = value.lastIndexOf(".");
  if (dot === -1) return `${value}.0`;
  const fraction = value.slice(dot + 1).replace(/\D.*$/, "");
  const suffix = value.slice(dot + 1).slice(fraction.length);
  return `${value.slice(0, dot)}.${(fraction + "0").slice(0, 1)}${suffix}`;
}

function displayValue(value: unknown): string {
  if (value === null || value === undefined || value === "") return "-";
  return String(value);
}

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
      start = new Date(end.getTime() - 30 * 24 * 60 * 60 * 1000);
      break;
    case "Custom":
      break;
  }

  return { start, end };
};

export function Events() {
  const { t } = useTranslation();
  const { timeZone } = useDisplayTimezone();
  const [events, setEvents] = useState<Event[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [pagination, setPagination] = useState({
    page: 1,
    limit: 20,
    total: 0,
    pages: 0,
  });

  // Filtros
  const [filters, setFilters] = useState<EventFilter>(() => {
    const savedPage = localStorage.getItem("events_page");
    const savedLimit = localStorage.getItem("events_limit");
    return {
      page: savedPage ? Number(savedPage) : 1,
      limit: savedLimit ? Number(savedLimit) : 20,
    };
  });

  // Opciones para los filtros
  const [availableUsers, setAvailableUsers] = useState<User[]>([]);

  // Valores seleccionados en los filtros
  const [selectedUsernames, setSelectedUsernames] = useState<string[]>(() => {
    const saved = localStorage.getItem("events_selectedUsernames");
    return saved ? JSON.parse(saved) : [];
  });
  const [selectedPriorities, setSelectedPriorities] = useState<number[]>(() => {
    const saved = localStorage.getItem("events_selectedPriorities");
    return saved ? JSON.parse(saved) : [];
  });
  const [selectedCriticities, setSelectedCriticities] = useState<number[]>(() => {
    const saved = localStorage.getItem("events_selectedCriticities");
    return saved ? JSON.parse(saved) : [];
  });
  const [presetDate, setPresetDate] = useState<PresetDate>(() => {
    const saved = localStorage.getItem("events_presetDate");
    return (saved as PresetDate) || "Last Hour";
  });
  const [startDate, setStartDate] = useState<string>(() => {
    return localStorage.getItem("events_startDate") || "";
  });
  const [endDate, setEndDate] = useState<string>(() => {
    return localStorage.getItem("events_endDate") || "";
  });

  const PRIORITY_OPTIONS = [0, 1, 2, 3, 4, 5];
  const CRITICITY_OPTIONS = [0, 1, 2, 3, 4, 5];

  // Estado para el menú contextual y comentarios
  const [contextMenu, setContextMenu] = useState<{
    visible: boolean;
    x: number;
    y: number;
    eventId: number | undefined;
  }>({
    visible: false,
    x: 0,
    y: 0,
    eventId: undefined,
  });
  const [selectedEventId, setSelectedEventId] = useState<number | undefined>(undefined);
  const [showCommentModal, setShowCommentModal] = useState(false);
  const [commentMessage, setCommentMessage] = useState("");
  const [addingComment, setAddingComment] = useState(false);
  const contextMenuRef = useRef<HTMLDivElement>(null);
  
  // Estado para el modal de visualización de comentarios
  const [showCommentsModal, setShowCommentsModal] = useState(false);
  const [selectedEventForComments, setSelectedEventForComments] = useState<Event | null>(null);
  const [comments, setComments] = useState<any[]>([]);
  const [loadingComments, setLoadingComments] = useState(false);
  const [selectedEventDetail, setSelectedEventDetail] = useState<Event | null>(null);

  // Cargar opciones para los filtros
  useEffect(() => {
    loadFilterOptions();
  }, []);

  // Cargar datos cuando cambian los filtros
  useEffect(() => {
    loadEvents();
  }, [filters, timeZone]);

  // Cerrar menú contextual al hacer click fuera
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (contextMenuRef.current && !contextMenuRef.current.contains(event.target as Node)) {
        setContextMenu({ visible: false, x: 0, y: 0, eventId: undefined });
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
      // Cargar usuarios
      const users = await getAllUsers();
      setAvailableUsers(users);

      // Establecer fechas por defecto solo si no hay fechas guardadas
      if (!startDate || !endDate) {
        const { start, end } = getPresetDateRange("Last Hour");
        const now = new Date();
        const finalEnd = end > now ? now : end;
        const startStr = formatToLocalDateTime(start);
        const endStr = formatToLocalDateTime(finalEnd);
        setEndDate(endStr);
        setStartDate(startStr);
        localStorage.setItem("events_startDate", startStr);
        localStorage.setItem("events_endDate", endStr);
      }
    } catch (e: any) {
      console.error("Error loading filter options:", e);
    }
  };

  const loadEvents = async () => {
    setLoading(true);
    setError(null);
    try {
      const payload: EventFilter = {
        ...filters,
      };

      // Agregar filtros solo si tienen valores
      if (selectedUsernames.length > 0) {
        payload.usernames = selectedUsernames;
      }
      if (selectedPriorities.length > 0) {
        payload.priorities = selectedPriorities;
      }
      if (selectedCriticities.length > 0) {
        payload.criticities = selectedCriticities;
      }
      if (startDate) {
        payload.greater_than_timestamp = formatDateTimeForBackend(startDate);
      }
      if (endDate) {
        payload.less_than_timestamp = formatDateTimeForBackend(endDate);
      }

      // Siempre enviar timezone, usar el seleccionado o el detectado del navegador
      payload.timezone = timeZone;

      const response: EventResponse = await filterEvents(payload);
      setEvents(response.data || []);
      setPagination({
        page: response.pagination?.page || 1,
        limit: response.pagination?.limit || 20,
        total: response.pagination?.total_records || 0,
        pages: response.pagination?.total_pages || 0,
      });
    } catch (e: any) {
      if (isDbUnavailableError(e)) {
        setError(null);
        setEvents([]);
        return;
      }
      const data = e?.response?.data;
      const backendMessage =
        (typeof data === "string" ? data : undefined) ??
        data?.message ??
        data?.detail ??
        data?.error;
      const errorMsg = backendMessage || e?.message || t("events.loadError");
      setError(errorMsg);
      setEvents([]);
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
      localStorage.setItem("events_startDate", startStr);
      localStorage.setItem("events_endDate", endStr);
    }
    const newFilters = {
      ...filters,
      page: 1,
    };
    setFilters(newFilters);
    localStorage.setItem("events_page", "1");
    localStorage.setItem("events_limit", String(newFilters.limit || 20));
  };

  const userOptions = useMemo(
    () =>
      availableUsers.map((user) => ({
        value: user.username,
        label: user.username,
        description: user.role?.name,
      })),
    [availableUsers]
  );

  const priorityOptions = useMemo(
    () =>
      PRIORITY_OPTIONS.map((priority) => ({
        value: String(priority),
        label: String(priority),
      })),
    []
  );

  const criticityOptions = useMemo(
    () =>
      CRITICITY_OPTIONS.map((criticity) => ({
        value: String(criticity),
        label: String(criticity),
      })),
    []
  );

  const handleUsernamesChange = (next: string[]) => {
    setSelectedUsernames(next);
    localStorage.setItem("events_selectedUsernames", JSON.stringify(next));
  };

  const handlePrioritiesChange = (next: string[]) => {
    const values = next.map(Number).filter((n) => Number.isFinite(n));
    setSelectedPriorities(values);
    localStorage.setItem("events_selectedPriorities", JSON.stringify(values));
  };

  const handleCriticitiesChange = (next: string[]) => {
    const values = next.map(Number).filter((n) => Number.isFinite(n));
    setSelectedCriticities(values);
    localStorage.setItem("events_selectedCriticities", JSON.stringify(values));
  };

  const handlePresetDateChange = (preset: PresetDate) => {
    setPresetDate(preset);
    localStorage.setItem("events_presetDate", preset);
    if (preset !== "Custom") {
      const { start, end } = getPresetDateRange(preset);
      const now = new Date();
      const finalEnd = end > now ? now : end;
      const startStr = formatToLocalDateTime(start);
      const endStr = formatToLocalDateTime(finalEnd);
      setStartDate(startStr);
      setEndDate(endStr);
      localStorage.setItem("events_startDate", startStr);
      localStorage.setItem("events_endDate", endStr);
    }
  };

  const handleEndDateChange = (value: string) => {
    const selectedEnd = new Date(value);
    const now = new Date();
    const finalValue = selectedEnd > now ? formatToLocalDateTime(now) : value;
    setEndDate(finalValue);
    localStorage.setItem("events_endDate", finalValue);
  };

  const handleRowContextMenu = (e: React.MouseEvent, event: Event) => {
    e.preventDefault();
    const eventId = typeof event.id === "number" ? event.id : typeof event.id === "string" ? Number(event.id) : undefined;
    setContextMenu({
      visible: true,
      x: e.clientX,
      y: e.clientY,
      eventId: eventId || undefined,
    });
  };

  const handleAddComment = () => {
    if (contextMenu.eventId) {
      setSelectedEventId(contextMenu.eventId);
      setShowCommentModal(true);
    }
    setContextMenu({ visible: false, x: 0, y: 0, eventId: undefined });
  };

  const handleSaveComment = async () => {
    if (!commentMessage.trim() || !selectedEventId) {
      setError(t("events.messageRequired"));
      return;
    }

    setAddingComment(true);
    setError(null);
    try {
      await createLog({
        message: commentMessage.trim(),
        event_id: selectedEventId,
      });
      setCommentMessage("");
      setShowCommentModal(false);
      setSelectedEventId(undefined);
      // Recargar eventos
      loadEvents();
    } catch (e: any) {
      const errorMsg =
        e?.response?.data?.message ||
        e?.message ||
        t("events.addCommentError");
      setError(errorMsg);
    } finally {
      setAddingComment(false);
    }
  };

  const handleCancelComment = () => {
    setShowCommentModal(false);
    setCommentMessage("");
    setSelectedEventId(undefined);
  };

  const handleViewComments = async (event: Event) => {
    if (!event.id) return;
    
    setSelectedEventForComments(event);
    setShowCommentsModal(true);
    setLoadingComments(true);
    setError(null);
    
    try {
      const eventId = typeof event.id === "string" ? Number(event.id) : event.id;
      const commentsData = await getEventComments(eventId);
      setComments(commentsData || []);
    } catch (e: any) {
      const data = e?.response?.data;
      const backendMessage =
        (typeof data === "string" ? data : undefined) ??
        data?.message ??
        data?.detail ??
        data?.error;
      const errorMsg = backendMessage || e?.message || t("events.loadCommentsError");
      setError(errorMsg);
      setComments([]);
    } finally {
      setLoadingComments(false);
    }
  };

  const handleExportCommentsCSV = () => {
    if (!comments || comments.length === 0) {
      setError(t("events.noCommentsToExport"));
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
        t("tables.event"),
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
          comment.event?.id || "",
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
        `event_comments_${selectedEventForComments?.id || "event"}_${new Date().toISOString().split("T")[0]}.csv`
      );
      link.style.visibility = "hidden";

      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);

      URL.revokeObjectURL(url);
    } catch (e: any) {
      const errorMsg = e?.message || t("events.exportCommentsError");
      setError(errorMsg);
    }
  };

  const handleClearFilters = () => {
    setSelectedUsernames([]);
    setSelectedPriorities([]);
    setSelectedCriticities([]);
    localStorage.removeItem("events_selectedUsernames");
    localStorage.removeItem("events_selectedPriorities");
    localStorage.removeItem("events_selectedCriticities");
    setPresetDate("Last Hour");
    localStorage.setItem("events_presetDate", "Last Hour");
    const { start, end } = getPresetDateRange("Last Hour");
    const now = new Date();
    const finalEnd = end > now ? now : end;
    const startStr = formatToLocalDateTime(start);
    const endStr = formatToLocalDateTime(finalEnd);
    setEndDate(endStr);
    setStartDate(startStr);
    localStorage.setItem("events_startDate", startStr);
    localStorage.setItem("events_endDate", endStr);
    setFilters({
      page: 1,
      limit: 20,
    });
    localStorage.setItem("events_page", "1");
    localStorage.setItem("events_limit", "20");
  };

  const handlePageChange = (newPage: number) => {
    if (newPage >= 1 && newPage <= pagination.pages) {
      setFilters({ ...filters, page: newPage });
      localStorage.setItem("events_page", String(newPage));
    }
  };

  const handleLimitChange = (newLimit: number) => {
    if (newLimit > 0) {
      setFilters({ ...filters, page: 1, limit: newLimit });
      localStorage.setItem("events_page", "1");
      localStorage.setItem("events_limit", String(newLimit));
    }
  };

  const handleExportCSV = async () => {
    try {
      setError(null);
      
      const payload: EventFilter = {
        ...filters,
        page: 1,
        limit: 10000,
      };

      if (selectedUsernames.length > 0) {
        payload.usernames = selectedUsernames;
      }
      if (selectedPriorities.length > 0) {
        payload.priorities = selectedPriorities;
      }
      if (selectedCriticities.length > 0) {
        payload.criticities = selectedCriticities;
      }
      if (startDate) {
        payload.greater_than_timestamp = formatDateTimeForBackend(startDate);
      }
      if (endDate) {
        payload.less_than_timestamp = formatDateTimeForBackend(endDate);
      }

      payload.timezone = timeZone;

      const response: EventResponse = await filterEvents(payload);
      const allEvents = response.data || [];

      if (!allEvents || allEvents.length === 0) {
        setError(t("events.noDataToExport"));
        return;
      }

      const headers = [
        t("tables.id"),
        t("tables.timestamp"),
        t("tables.user"),
        t("tables.message"),
        t("tables.description"),
        t("tables.classification"),
        t("tables.priority"),
        t("tables.criticity"),
      ];

      const rows = allEvents.map((event: Event) => {
        return [
          event.id || "",
          event.timestamp || "",
          event.user?.username || event.username || "",
          event.message || "",
          event.description || "",
          event.classification || "",
          event.priority !== null && event.priority !== undefined ? String(event.priority) : "",
          event.criticity !== null && event.criticity !== undefined ? String(event.criticity) : "",
        ];
      });

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

      const blob = new Blob([csvContent], { type: "text/csv;charset=utf-8;" });
      const link = document.createElement("a");
      const url = URL.createObjectURL(blob);

      link.setAttribute("href", url);
      link.setAttribute(
        "download",
        `events_${new Date().toISOString().split("T")[0]}.csv`
      );
      link.style.visibility = "hidden";

      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);

      URL.revokeObjectURL(url);
    } catch (e: any) {
      const errorMsg =
        e?.response?.data?.message ||
        e?.message ||
        t("events.exportError");
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
                <span className="me-auto">{t("navigation.events")}</span>
                <div className="d-flex align-items-center gap-2 flex-wrap">
                  <div className="d-flex align-items-center gap-1">
                    <label className="form-label small mb-0 me-1">
                      {t("events.usernames")}
                    </label>
                    <MultiSelectSearch
                      options={userOptions}
                      selected={selectedUsernames}
                      onChange={handleUsernamesChange}
                      placeholder={t("events.selectUsersPlaceholder")}
                      searchPlaceholder={t("events.searchUsers")}
                      emptyText={t("events.noUsersFound")}
                      selectAllLabel={t("events.selectAll")}
                      clearLabel={t("common.clear")}
                      selectedCountLabel={(count) => t("events.selectedCount", { count })}
                      disabled={loading}
                      style={{ width: "180px", maxWidth: "100%" }}
                    />
                  </div>
                  <div className="d-flex align-items-center gap-1">
                    <label className="form-label small mb-0 me-1">
                      {t("events.priority")}
                    </label>
                    <MultiSelectSearch
                      options={priorityOptions}
                      selected={selectedPriorities.map(String)}
                      onChange={handlePrioritiesChange}
                      placeholder={t("events.selectPriorityPlaceholder")}
                      searchPlaceholder={t("events.searchPriority")}
                      emptyText={t("events.noPriorityFound")}
                      selectAllLabel={t("events.selectAll")}
                      clearLabel={t("common.clear")}
                      selectedCountLabel={(count) => t("events.selectedCount", { count })}
                      disabled={loading}
                      style={{ width: "150px", maxWidth: "100%" }}
                    />
                  </div>
                  <div className="d-flex align-items-center gap-1">
                    <label className="form-label small mb-0 me-1">
                      {t("events.criticity")}
                    </label>
                    <MultiSelectSearch
                      options={criticityOptions}
                      selected={selectedCriticities.map(String)}
                      onChange={handleCriticitiesChange}
                      placeholder={t("events.selectCriticityPlaceholder")}
                      searchPlaceholder={t("events.searchCriticity")}
                      emptyText={t("events.noCriticityFound")}
                      selectAllLabel={t("events.selectAll")}
                      clearLabel={t("common.clear")}
                      selectedCountLabel={(count) => t("events.selectedCount", { count })}
                      disabled={loading}
                      style={{ width: "150px", maxWidth: "100%" }}
                    />
                  </div>
                  <div className="d-flex align-items-center gap-1">
                    <label className="form-label small mb-0 me-1">
                      {t("events.range")}
                    </label>
                    <select
                      className="form-select form-select-sm"
                      style={{ width: "150px", maxWidth: "100%" }}
                      value={presetDate}
                      onChange={(e) => handlePresetDateChange(e.target.value as PresetDate)}
                    >
                      {PRESET_DATES.map((preset) => (
                        <option key={preset} value={preset}>
                          {t(`events.preset.${preset}`)}
                        </option>
                      ))}
                    </select>
                  </div>
                  <Button
                    variant="primary"
                    className="btn-sm"
                    onClick={handleApplyFilters}
                    disabled={loading}
                  >
                    {t("common.filter")}
                  </Button>
                  <Button
                    variant="primary"
                    className="btn-sm"
                    onClick={handleExportCSV}
                    disabled={loading || events.length === 0}
                  >
                    <i className="bi bi-download me-1"></i>
                    {t("common.csv")}
                  </Button>
                </div>
              </div>
              {presetDate === "Custom" && (
                <div className="card-header-stack__row d-flex align-items-center gap-2 flex-wrap pt-2 mt-1 border-top">
                  <div className="d-flex align-items-center gap-1">
                    <label className="form-label small mb-0 me-1">
                      {t("events.start")}
                    </label>
                    <input
                      type="datetime-local"
                      step="1"
                      className="form-control form-control-sm"
                      style={{ width: "180px", maxWidth: "100%" }}
                      value={startDate}
                      onChange={(e) => {
                        setStartDate(e.target.value);
                        localStorage.setItem("events_startDate", e.target.value);
                      }}
                    />
                  </div>
                  <div className="d-flex align-items-center gap-1">
                    <label className="form-label small mb-0 me-1">
                      {t("events.end")}
                    </label>
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
                    <th>{t("tables.timestamp")}</th>
                    <th>{t("tables.user")}</th>
                    <th>{t("tables.message")}</th>
                    <th>{t("tables.classification")}</th>
                    <th>{t("tables.priority")}</th>
                    <th>{t("tables.criticity")}</th>
                    <th>{t("tables.comments")}</th>
                  </tr>
                </thead>
                <tbody>
                  {events.length === 0 ? (
                    <tr>
                      <td colSpan={8} className="text-center text-muted py-4">
                        {t("events.noEvents")}
                      </td>
                    </tr>
                  ) : (
                    events.map((event) => (
                      <tr
                        key={event.id}
                        onContextMenu={(e) => handleRowContextMenu(e, event)}
                        onDoubleClick={() => setSelectedEventDetail(event)}
                        style={{ cursor: "pointer" }}
                        title={t("events.detailHint")}
                      >
                        <td>{event.id || "-"}</td>
                        <td>{formatEventTimestamp(event.timestamp)}</td>
                        <td>{event.user?.username || event.username || "-"}</td>
                        <td>{event.message || "-"}</td>
                        <td>{event.classification || "-"}</td>
                        <td>
                          {event.priority !== null && event.priority !== undefined ? (
                            <span className="badge bg-info">{event.priority}</span>
                          ) : (
                            "-"
                          )}
                        </td>
                        <td>
                          {event.criticity !== null && event.criticity !== undefined ? (
                            <span className="badge bg-warning">{event.criticity}</span>
                          ) : (
                            "-"
                          )}
                        </td>
                        <td>
                          {event.has_comments ? (
                            <i
                              className="bi bi-check-circle text-success"
                              title={t("events.hasCommentsClick")}
                              style={{ cursor: "pointer" }}
                              onClick={(e) => {
                                e.stopPropagation();
                                handleViewComments(event);
                              }}
                              onDoubleClick={(e) => e.stopPropagation()}
                            ></i>
                          ) : (
                            <i className="bi bi-x-circle text-muted" title={t("events.noComments")}></i>
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
                {t("events.addComment")}
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
                    <h5 className="modal-title">
                      {t("events.addComment")}
                    </h5>
                    <button
                      type="button"
                      className="btn-close"
                      onClick={handleCancelComment}
                    ></button>
                  </div>
                  <div className="modal-body">
                    <div className="mb-3">
                      <label className="form-label">
                        {t("events.messageLabel")}
                      </label>
                      <textarea
                        className="form-control"
                        rows={4}
                        value={commentMessage}
                        onChange={(e) => setCommentMessage(e.target.value)}
                        placeholder={t("events.commentPlaceholder")}
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
                      {t("events.addComment")}
                    </Button>
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* Modal para visualizar comentarios */}
          {showCommentsModal && selectedEventForComments && (
            <div
              className="modal show d-block"
              style={{ backgroundColor: "rgba(0,0,0,0.5)" }}
              onClick={() => {
                setShowCommentsModal(false);
                setSelectedEventForComments(null);
                setComments([]);
              }}
            >
              <div className="modal-dialog modal-xl" onClick={(e) => e.stopPropagation()}>
                <div className="modal-content">
                  <div className="modal-header d-flex justify-content-between align-items-center w-100">
                    <h5 className="modal-title mb-0">
                      {t("events.commentsTitle", { id: selectedEventForComments.id || "N/A" })}
                    </h5>
                    <div className="d-flex align-items-center gap-2">
                      <Button
                        variant="primary"
                        className="btn-sm"
                        onClick={handleExportCommentsCSV}
                        disabled={loadingComments || comments.length === 0}
                      >
                        <i className="bi bi-download me-1"></i>
                        {t("common.csv")}
                      </Button>
                      <button
                        type="button"
                        className="btn-close"
                        onClick={() => {
                          setShowCommentsModal(false);
                          setSelectedEventForComments(null);
                          setComments([]);
                        }}
                      ></button>
                    </div>
                  </div>
                  <div className="modal-body">
                    {loadingComments ? (
                      <div className="text-center py-4">
                        <div className="spinner-border text-primary" role="status">
                          <span className="visually-hidden">{t("events.loading")}</span>
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
                              <th>{t("tables.event")}</th>
                            </tr>
                          </thead>
                          <tbody>
                            {comments.length === 0 ? (
                              <tr>
                                <td colSpan={7} className="text-center text-muted py-4">
                                  {t("events.noCommentsAvailable")}
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
                                  <td>{comment.event?.id || "-"}</td>
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
                        setSelectedEventForComments(null);
                        setComments([]);
                      }}
                    >
                      {t("events.close")}
                    </Button>
                  </div>
                </div>
              </div>
            </div>
          )}

          {selectedEventDetail && (
            <div
              className="modal show d-block"
              style={{ backgroundColor: "rgba(0,0,0,0.5)" }}
              onClick={() => setSelectedEventDetail(null)}
            >
              <div className="modal-dialog modal-lg modal-dialog-scrollable" onClick={(e) => e.stopPropagation()}>
                <div className="modal-content">
                  <div className="modal-header">
                    <h5 className="modal-title">
                      {t("events.detailTitle", { id: selectedEventDetail.id || "N/A" })}
                    </h5>
                    <button
                      type="button"
                      className="btn-close"
                      onClick={() => setSelectedEventDetail(null)}
                    ></button>
                  </div>
                  <div className="modal-body">
                    <dl className="row mb-0">
                      <dt className="col-sm-4">{t("tables.id")}</dt>
                      <dd className="col-sm-8">{displayValue(selectedEventDetail.id)}</dd>

                      <dt className="col-sm-4">{t("tables.timestamp")}</dt>
                      <dd className="col-sm-8">{displayValue(selectedEventDetail.timestamp)}</dd>

                      <dt className="col-sm-4">{t("tables.user")}</dt>
                      <dd className="col-sm-8">
                        {displayValue(selectedEventDetail.user?.username || selectedEventDetail.username)}
                      </dd>

                      <dt className="col-sm-4">{t("tables.name")}</dt>
                      <dd className="col-sm-8">{displayValue(selectedEventDetail.user?.name)}</dd>

                      <dt className="col-sm-4">{t("tables.lastname")}</dt>
                      <dd className="col-sm-8">{displayValue(selectedEventDetail.user?.lastname)}</dd>

                      <dt className="col-sm-4">{t("tables.email")}</dt>
                      <dd className="col-sm-8">{displayValue(selectedEventDetail.user?.email)}</dd>

                      <dt className="col-sm-4">{t("tables.role")}</dt>
                      <dd className="col-sm-8">{displayValue(selectedEventDetail.user?.role?.name)}</dd>

                      <dt className="col-sm-4">{t("tables.message")}</dt>
                      <dd className="col-sm-8">{displayValue(selectedEventDetail.message)}</dd>

                      <dt className="col-sm-4">{t("tables.description")}</dt>
                      <dd className="col-sm-8">{displayValue(selectedEventDetail.description)}</dd>

                      <dt className="col-sm-4">{t("tables.classification")}</dt>
                      <dd className="col-sm-8">{displayValue(selectedEventDetail.classification)}</dd>

                      <dt className="col-sm-4">{t("tables.priority")}</dt>
                      <dd className="col-sm-8">
                        {selectedEventDetail.priority !== null && selectedEventDetail.priority !== undefined ? (
                          <span className="badge bg-info">{selectedEventDetail.priority}</span>
                        ) : (
                          "-"
                        )}
                      </dd>

                      <dt className="col-sm-4">{t("tables.criticity")}</dt>
                      <dd className="col-sm-8">
                        {selectedEventDetail.criticity !== null && selectedEventDetail.criticity !== undefined ? (
                          <span className="badge bg-warning">{selectedEventDetail.criticity}</span>
                        ) : (
                          "-"
                        )}
                      </dd>

                      <dt className="col-sm-4">{t("tables.segment")}</dt>
                      <dd className="col-sm-8">{displayValue(selectedEventDetail.segment)}</dd>

                      <dt className="col-sm-4">{t("tables.manufacturer")}</dt>
                      <dd className="col-sm-8">{displayValue(selectedEventDetail.manufacturer)}</dd>

                      <dt className="col-sm-4">{t("tables.comments")}</dt>
                      <dd className="col-sm-8">
                        {selectedEventDetail.has_comments ? t("common.yes") : t("common.no")}
                      </dd>
                    </dl>
                  </div>
                  <div className="modal-footer">
                    <Button variant="secondary" onClick={() => setSelectedEventDetail(null)}>
                      {t("events.close")}
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
