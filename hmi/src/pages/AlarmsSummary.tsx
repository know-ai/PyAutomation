import { useEffect, useState } from "react";
import { Card } from "../components/Card";
import { Button } from "../components/Button";
import {
  filterAlarmsSummary,
  type AlarmSummary,
  type AlarmSummaryFilter,
  type AlarmSummaryResponse,
} from "../services/alarms";
import { getTimezones } from "../services/tags";

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
  const [filters, setFilters] = useState<AlarmSummaryFilter>({
    page: 1,
    limit: 20,
  });

  // Opciones para los filtros
  const [availableStates, setAvailableStates] = useState<string[]>([]);
  const [availableTimezones, setAvailableTimezones] = useState<string[]>([]);

  // Valores seleccionados en los filtros
  const [selectedStates, setSelectedStates] = useState<string[]>([]);
  const [startDate, setStartDate] = useState<string>("");
  const [endDate, setEndDate] = useState<string>("");
  const [selectedTimezone, setSelectedTimezone] = useState<string>("");

  // Cargar opciones para los filtros
  useEffect(() => {
    loadFilterOptions();
  }, []);

  // Cargar datos cuando cambian los filtros
  useEffect(() => {
    loadAlarmsSummary();
  }, [filters]);

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

      // Establecer fechas por defecto (últimos 30 minutos)
      const now = new Date();
      const thirtyMinutesAgo = new Date(now.getTime() - 30 * 60 * 1000);
      setEndDate(now.toISOString().slice(0, 16));
      setStartDate(thirtyMinutesAgo.toISOString().slice(0, 16));
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
      setPagination(response.pagination || {
        page: 1,
        limit: 20,
        total: 0,
        pages: 0,
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
    setFilters({
      ...filters,
      page: 1, // Resetear a la primera página al aplicar filtros
    });
  };

  const handleClearFilters = () => {
    setSelectedStates([]);
    const now = new Date();
    const thirtyMinutesAgo = new Date(now.getTime() - 30 * 60 * 1000);
    setEndDate(now.toISOString().slice(0, 16));
    setStartDate(thirtyMinutesAgo.toISOString().slice(0, 16));
    setSelectedTimezone(availableTimezones[0] || "");
    setFilters({
      page: 1,
      limit: 20,
    });
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
                  <label className="form-label small mb-0 me-1">Inicio:</label>
                  <input
                    type="datetime-local"
                    className="form-control form-control-sm"
                    style={{ width: "180px" }}
                    value={startDate}
                    onChange={(e) => setStartDate(e.target.value)}
                  />
                </div>
                <div className="d-flex align-items-center gap-1">
                  <label className="form-label small mb-0 me-1">Fin:</label>
                  <input
                    type="datetime-local"
                    className="form-control form-control-sm"
                    style={{ width: "180px" }}
                    value={endDate}
                    onChange={(e) => setEndDate(e.target.value)}
                  />
                </div>
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
                        if (isSelected) {
                          setSelectedStates(selectedStates.filter((s) => s !== state));
                        } else {
                          setSelectedStates([...selectedStates, state]);
                        }
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
                      <tr key={alarm.id}>
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
        </Card>
      </div>
    </div>
  );
}
