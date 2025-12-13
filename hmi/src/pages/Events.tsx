import { useEffect, useState, useRef } from "react";
import { Card } from "../components/Card";
import { Button } from "../components/Button";
import {
  filterEvents,
  getEventComments,
  type Event,
  type EventFilter,
  type EventResponse,
} from "../services/events";
import { getTimezones } from "../services/tags";
import { getAllUsers, type User } from "../services/users";
import { createLog } from "../services/logs";
import { useTranslation } from "../hooks/useTranslation";

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
      start = new Date(end.getTime() - 30 * 24 * 60 * 60 * 1000);
      break;
    case "Custom":
      break;
  }

  return { start, end };
};

export function Events() {
  const { t } = useTranslation();
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
  const [availableTimezones, setAvailableTimezones] = useState<string[]>([]);

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
  const [selectedTimezone, setSelectedTimezone] = useState<string>(() => {
    return localStorage.getItem("events_timezone") || "";
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

  // Cargar opciones para los filtros
  useEffect(() => {
    loadFilterOptions();
  }, []);

  // Cargar datos cuando cambian los filtros
  useEffect(() => {
    loadEvents();
  }, [filters]);

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
  const formatToLocalDateTime = (date: Date): string => {
    const year = date.getFullYear();
    const month = String(date.getMonth() + 1).padStart(2, "0");
    const day = String(date.getDate()).padStart(2, "0");
    const hours = String(date.getHours()).padStart(2, "0");
    const minutes = String(date.getMinutes()).padStart(2, "0");
    return `${year}-${month}-${day}T${hours}:${minutes}`;
  };

  // Función para convertir el formato de fecha del input al formato esperado por el backend
  const formatDateTimeForBackend = (dateTimeString: string): string => {
    if (!dateTimeString) return "";
    return dateTimeString.replace("T", " ") + ":00.00";
  };

  const loadFilterOptions = async () => {
    try {
      // Detectar zona horaria del navegador
      const browserTimezone = Intl.DateTimeFormat().resolvedOptions().timeZone;

      // Cargar usuarios
      const users = await getAllUsers();
      setAvailableUsers(users);

      // Cargar timezones
      const timezones = await getTimezones();
      setAvailableTimezones(timezones);
      
      // Intentar usar la zona horaria del navegador, si está disponible
      if (timezones.length > 0) {
        const browserTzInList = timezones.find(tz => tz === browserTimezone);
        if (browserTzInList) {
          setSelectedTimezone(browserTimezone);
          localStorage.setItem("events_timezone", browserTimezone);
        } else {
          const browserRegion = browserTimezone.split("/")[0];
          const similarTz = timezones.find(tz => tz.startsWith(browserRegion + "/"));
          if (similarTz) {
            setSelectedTimezone(similarTz);
            localStorage.setItem("events_timezone", similarTz);
          } else {
            setSelectedTimezone(timezones[0]);
            localStorage.setItem("events_timezone", timezones[0]);
          }
        }
      } else if (selectedTimezone) {
        localStorage.setItem("events_timezone", selectedTimezone);
      }

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
      const timezoneToUse = selectedTimezone || Intl.DateTimeFormat().resolvedOptions().timeZone;
      payload.timezone = timezoneToUse;

      const response: EventResponse = await filterEvents(payload);
      setEvents(response.data || []);
      setPagination({
        page: response.pagination?.page || 1,
        limit: response.pagination?.limit || 20,
        total: response.pagination?.total_records || 0,
        pages: response.pagination?.total_pages || 0,
      });
    } catch (e: any) {
      const errorMsg = e?.response?.data?.message || e?.message || "Error al cargar los eventos";
      setError(errorMsg);
      setEvents([]);
    } finally {
      setLoading(false);
    }
  };

  const handleApplyFilters = () => {
    const newFilters = {
      ...filters,
      page: 1,
    };
    setFilters(newFilters);
    localStorage.setItem("events_page", "1");
    localStorage.setItem("events_limit", String(newFilters.limit || 20));
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
      setError("El mensaje es requerido");
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
      const errorMsg = e?.response?.data?.message || e?.message || "Error al agregar el comentario";
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
      const errorMsg = e?.response?.data?.message || e?.message || "Error al cargar los comentarios";
      setError(errorMsg);
      setComments([]);
    } finally {
      setLoadingComments(false);
    }
  };

  const handleExportCommentsCSV = () => {
    if (!comments || comments.length === 0) {
      setError("No hay comentarios para exportar");
      return;
    }

    try {
      // Preparar los datos para CSV
      const headers = [
        "ID",
        "Timestamp",
        "Usuario",
        "Mensaje",
        "Descripción",
        "Clasificación",
        "Evento",
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
      const errorMsg = e?.message || "Error al exportar comentarios a CSV";
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

      const timezoneToUse = selectedTimezone || Intl.DateTimeFormat().resolvedOptions().timeZone;
      payload.timezone = timezoneToUse;

      const response: EventResponse = await filterEvents(payload);
      const allEvents = response.data || [];

      if (!allEvents || allEvents.length === 0) {
        setError("No hay datos para exportar");
        return;
      }

      const headers = [
        "ID",
        "Timestamp",
        "Usuario",
        "Mensaje",
        "Descripción",
        "Clasificación",
        "Prioridad",
        "Criticidad",
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
        e?.response?.data?.message || e?.message || "Error al exportar eventos a CSV";
      setError(errorMsg);
    }
  };

  return (
    <div className="row">
      <div className="col-12">
        <Card
          title={
            <div className="d-flex align-items-center gap-2 w-100 flex-wrap">
              <span className="me-auto">Events</span>
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
                          localStorage.setItem("events_startDate", e.target.value);
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
                  <label className="form-label small mb-0 me-1">Prioridad:</label>
                  <select
                    className="form-select form-select-sm"
                    style={{ width: "100px" }}
                    value={selectedPriorities.length > 0 ? String(selectedPriorities[0]) : ""}
                    onChange={(e) => {
                      const value = e.target.value === "" ? [] : [Number(e.target.value)];
                      setSelectedPriorities(value);
                      localStorage.setItem("events_selectedPriorities", JSON.stringify(value));
                    }}
                  >
                    <option value="">Todos</option>
                    {PRIORITY_OPTIONS.map((priority) => (
                      <option key={priority} value={String(priority)}>
                        {priority}
                      </option>
                    ))}
                  </select>
                </div>
                <div className="d-flex align-items-center gap-1">
                  <label className="form-label small mb-0 me-1">Criticidad:</label>
                  <select
                    className="form-select form-select-sm"
                    style={{ width: "100px" }}
                    value={selectedCriticities.length > 0 ? String(selectedCriticities[0]) : ""}
                    onChange={(e) => {
                      const value = e.target.value === "" ? [] : [Number(e.target.value)];
                      setSelectedCriticities(value);
                      localStorage.setItem("events_selectedCriticities", JSON.stringify(value));
                    }}
                  >
                    <option value="">Todos</option>
                    {CRITICITY_OPTIONS.map((criticity) => (
                      <option key={criticity} value={String(criticity)}>
                        {criticity}
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
                  disabled={loading || events.length === 0}
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

          {/* Filtro de usuarios */}
          <div className="mb-3">
            <div className="d-flex align-items-center gap-2 flex-wrap">
              <label className="form-label mb-0 me-2">Usernames:</label>
              <div className="d-flex align-items-center gap-2 flex-wrap">
                {availableUsers.map((user) => {
                  const isSelected = selectedUsernames.includes(user.username);
                  return (
                    <button
                      key={user.username}
                      type="button"
                      className={`btn btn-sm ${isSelected ? "btn-primary" : "btn-outline-secondary"}`}
                      onClick={() => {
                        const newSelectedUsernames = isSelected
                          ? selectedUsernames.filter((u) => u !== user.username)
                          : [...selectedUsernames, user.username];
                        setSelectedUsernames(newSelectedUsernames);
                        localStorage.setItem("events_selectedUsernames", JSON.stringify(newSelectedUsernames));
                      }}
                    >
                      {user.username}
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

          {!loading && (
            <div className="table-responsive" style={{ maxHeight: "70vh", overflowY: "auto" }}>
              <table className="table table-striped table-hover table-sm">
                <thead className="table-light" style={{ position: "sticky", top: 0, zIndex: 10 }}>
                  <tr>
                    <th>{t("tables.id")}</th>
                    <th>{t("tables.timestamp")}</th>
                    <th>{t("tables.user")}</th>
                    <th>{t("tables.message")}</th>
                    <th>{t("tables.description")}</th>
                    <th>{t("tables.classification")}</th>
                    <th>{t("tables.priority")}</th>
                    <th>{t("tables.criticity")}</th>
                    <th>{t("tables.comments")}</th>
                  </tr>
                </thead>
                <tbody>
                  {events.length === 0 ? (
                    <tr>
                      <td colSpan={9} className="text-center text-muted py-4">
                        No hay eventos disponibles
                      </td>
                    </tr>
                  ) : (
                    events.map((event) => (
                      <tr
                        key={event.id}
                        onContextMenu={(e) => handleRowContextMenu(e, event)}
                        style={{ cursor: "context-menu" }}
                      >
                        <td>{event.id || "-"}</td>
                        <td>{event.timestamp || "-"}</td>
                        <td>{event.user?.username || event.username || "-"}</td>
                        <td>{event.message || "-"}</td>
                        <td>{event.description || "-"}</td>
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
                              title="Tiene comentarios - Click para ver"
                              style={{ cursor: "pointer" }}
                              onClick={() => handleViewComments(event)}
                            ></i>
                          ) : (
                            <i className="bi bi-x-circle text-muted" title="Sin comentarios"></i>
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
                Agregar comentario
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
                    <h5 className="modal-title">Agregar Comentario</h5>
                    <button
                      type="button"
                      className="btn-close"
                      onClick={handleCancelComment}
                    ></button>
                  </div>
                  <div className="modal-body">
                    <div className="mb-3">
                      <label className="form-label">Mensaje *</label>
                      <textarea
                        className="form-control"
                        rows={4}
                        value={commentMessage}
                        onChange={(e) => setCommentMessage(e.target.value)}
                        placeholder="Ingrese el comentario para este evento"
                      />
                    </div>
                  </div>
                  <div className="modal-footer">
                    <Button
                      variant="secondary"
                      onClick={handleCancelComment}
                      disabled={addingComment}
                    >
                      Cancelar
                    </Button>
                    <Button
                      variant="primary"
                      onClick={handleSaveComment}
                      disabled={addingComment || !commentMessage.trim()}
                      loading={addingComment}
                    >
                      Agregar
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
                      Comentarios - Evento #{selectedEventForComments.id || "N/A"}
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
                          <span className="visually-hidden">Cargando...</span>
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
                                  No hay comentarios disponibles
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
                      Cerrar
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
