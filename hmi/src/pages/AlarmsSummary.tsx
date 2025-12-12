import { useEffect, useState, useRef } from "react";
import { Card } from "../components/Card";
import { Button } from "../components/Button";
import {
  filterAlarmsSummary,
  type AlarmSummary,
  type AlarmSummaryFilter,
  type AlarmSummaryResponse,
} from "../services/alarms";
import { getTimezones } from "../services/tags";
import { createLog } from "../services/logs";

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
  const [availableTimezones, setAvailableTimezones] = useState<string[]>([]);

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
  const [selectedTimezone, setSelectedTimezone] = useState<string>(() => {
    return localStorage.getItem("alarms_summary_timezone") || "";
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

  // Cargar opciones para los filtros
  useEffect(() => {
    loadFilterOptions();
  }, []);

  // Cargar datos cuando cambian los filtros
  useEffect(() => {
    loadAlarmsSummary();
  }, [filters]);

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
    // El input datetime-local devuelve formato: YYYY-MM-DDTHH:mm
    // El backend espera: YYYY-MM-DD HH:mm:ss.00
    return dateTimeString.replace("T", " ") + ":00.00";
  };

  const loadFilterOptions = async () => {
    try {
      // Cargar timezones
      const timezones = await getTimezones();
      setAvailableTimezones(timezones);
      if (timezones.length > 0 && !selectedTimezone) {
        setSelectedTimezone(timezones[0]);
        localStorage.setItem("alarms_summary_timezone", timezones[0]);
      } else if (selectedTimezone) {
        // Guardar el timezone si ya existe
        localStorage.setItem("alarms_summary_timezone", selectedTimezone);
      }

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

      const response: AlarmSummaryResponse = await filterAlarmsSummary(payload);
      setAlarmsSummary(response.data || []);
      setPagination({
        page: response.pagination?.page || 1,
        limit: response.pagination?.limit || 20,
        total: response.pagination?.total_records || 0,
        pages: response.pagination?.total_pages || 0,
      });
    } catch (e: any) {
      const errorMsg = e?.response?.data?.message || e?.message || "Error al cargar el resumen de alarmas";
      setError(errorMsg);
      setAlarmsSummary([]);
    } finally {
      setLoading(false);
    }
  };

  const handleApplyFilters = () => {
    const newFilters = {
      ...filters,
      page: 1, // Resetear a la primera página al aplicar filtros
    };
    setFilters(newFilters);
    localStorage.setItem("alarms_summary_page", "1");
    localStorage.setItem("alarms_summary_limit", String(newFilters.limit || 20));
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
    const defaultTimezone = availableTimezones[0] || "";
    setSelectedTimezone(defaultTimezone);
    localStorage.setItem("alarms_summary_timezone", defaultTimezone);
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
      setError("El mensaje es requerido");
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
      const errorMsg = e?.response?.data?.message || e?.message || "Error al agregar el comentario";
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

      const response: AlarmSummaryResponse = await filterAlarmsSummary(payload);
      const allAlarms = response.data || [];

      if (!allAlarms || allAlarms.length === 0) {
        setError("No hay datos para exportar");
        return;
      }

      // Preparar los datos para CSV
      const headers = [
        "ID",
        "Nombre",
        "Tag",
        "Descripción",
        "Estado",
        "Fecha/Hora Alarma",
        "Fecha/Hora ACK",
        "Tiene Comentarios",
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
          alarm.has_comments ? "Sí" : "No",
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
      const errorMsg =
        e?.response?.data?.message || e?.message || "Error al exportar resumen de alarmas a CSV";
      setError(errorMsg);
    }
  };

  return (
    <div className="row">
      <div className="col-12">
        <Card
          title={
            <div className="d-flex align-items-center gap-2 w-100 flex-wrap">
              <span className="me-auto">Resumen de Alarmas</span>
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
                          localStorage.setItem("alarms_summary_startDate", e.target.value);
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
                <Button variant="primary" className="btn-sm" onClick={handleApplyFilters} disabled={loading}>
                  Aplicar
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

          {/* Filtro de estados */}
          <div className="mb-3">
            <div className="d-flex align-items-center gap-2 flex-wrap">
              <label className="form-label mb-0 me-2">Estado:</label>
              <div className="d-flex align-items-center gap-2 flex-wrap">
                {availableStates.map((state) => {
                  const isSelected = selectedStates.includes(state);
                  return (
                    <button
                      key={state}
                      type="button"
                      className={`btn btn-sm ${isSelected ? "btn-primary" : "btn-outline-secondary"}`}
                      onClick={() => {
                        const newSelectedStates = isSelected
                          ? selectedStates.filter((s) => s !== state)
                          : [...selectedStates, state];
                        setSelectedStates(newSelectedStates);
                        localStorage.setItem("alarms_summary_selectedStates", JSON.stringify(newSelectedStates));
                      }}
                    >
                      {state}
                    </button>
                  );
                })}
              </div>
              <Button variant="secondary" className="btn-sm ms-auto" onClick={handleClearFilters} disabled={loading}>
                Limpiar
              </Button>
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
            <div className="table-responsive">
              <table className="table table-striped table-hover table-sm">
                <thead>
                  <tr>
                    <th>ID</th>
                    <th>Nombre</th>
                    <th>Tag</th>
                    <th>Descripción</th>
                    <th>Estado</th>
                    <th>Fecha/Hora Alarma</th>
                    <th>Fecha/Hora ACK</th>
                    <th>Comentarios</th>
                  </tr>
                </thead>
                <tbody>
                  {alarmsSummary.length === 0 ? (
                    <tr>
                      <td colSpan={8} className="text-center text-muted py-4">
                        No hay registros de alarmas disponibles
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
                            <i className="bi bi-check-circle text-success" title="Tiene comentarios"></i>
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
                        placeholder="Ingrese el comentario para esta alarma"
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
        </Card>
      </div>
    </div>
  );
}
