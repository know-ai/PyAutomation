import { useEffect, useState } from "react";
import { Card } from "../components/Card";
import { Button } from "../components/Button";
import {
  filterLogs,
  createLog,
  type Log,
  type LogFilter,
  type LogResponse,
} from "../services/logs";
import { getTimezones } from "../services/tags";
import { getAllUsers, type User } from "../services/users";
import { getAlarms, type Alarm } from "../services/alarms";
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

export function OperationalLogs() {
  const { t } = useTranslation();
  const [logs, setLogs] = useState<Log[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [pagination, setPagination] = useState({
    page: 1,
    limit: 20,
    total: 0,
    pages: 0,
  });

  // Filtros
  const [filters, setFilters] = useState<LogFilter>(() => {
    const savedPage = localStorage.getItem("operational_logs_page");
    const savedLimit = localStorage.getItem("operational_logs_limit");
    return {
      page: savedPage ? Number(savedPage) : 1,
      limit: savedLimit ? Number(savedLimit) : 20,
    };
  });

  // Opciones para los filtros
  const [availableUsers, setAvailableUsers] = useState<User[]>([]);
  const [availableAlarmNames, setAvailableAlarmNames] = useState<string[]>([]);
  const [availableTimezones, setAvailableTimezones] = useState<string[]>([]);

  // Valores seleccionados en los filtros
  const [selectedUsernames, setSelectedUsernames] = useState<string[]>(() => {
    const saved = localStorage.getItem("operational_logs_selectedUsernames");
    return saved ? JSON.parse(saved) : [];
  });
  const [selectedAlarmNames, setSelectedAlarmNames] = useState<string[]>(() => {
    const saved = localStorage.getItem("operational_logs_selectedAlarmNames");
    return saved ? JSON.parse(saved) : [];
  });
  const [presetDate, setPresetDate] = useState<PresetDate>(() => {
    const saved = localStorage.getItem("operational_logs_presetDate");
    return (saved as PresetDate) || "Last Hour";
  });
  const [startDate, setStartDate] = useState<string>(() => {
    return localStorage.getItem("operational_logs_startDate") || "";
  });
  const [endDate, setEndDate] = useState<string>(() => {
    return localStorage.getItem("operational_logs_endDate") || "";
  });
  const [selectedTimezone, setSelectedTimezone] = useState<string>(() => {
    return localStorage.getItem("operational_logs_timezone") || "";
  });

  // Estado para el formulario de agregar log
  const [showAddLogModal, setShowAddLogModal] = useState(false);
  const [newLogMessage, setNewLogMessage] = useState("");
  const [addingLog, setAddingLog] = useState(false);

  // Cargar opciones para los filtros
  useEffect(() => {
    loadFilterOptions();
  }, []);

  // Cargar datos cuando cambian los filtros
  useEffect(() => {
    loadLogs();
  }, [filters]);

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

      // Cargar nombres de alarmas
      try {
        const alarmsResponse = await getAlarms(1, 1000);
        const alarmNames = alarmsResponse.data?.map((alarm: Alarm) => alarm.name).filter(Boolean) || [];
        const uniqueAlarmNames = Array.from(new Set(alarmNames));
        setAvailableAlarmNames(uniqueAlarmNames);
      } catch (e) {
        console.error("Error loading alarm names:", e);
      }

      // Cargar timezones
      const timezones = await getTimezones();
      setAvailableTimezones(timezones);
      
      // Intentar usar la zona horaria del navegador, si está disponible
      if (timezones.length > 0) {
        const browserTzInList = timezones.find(tz => tz === browserTimezone);
        if (browserTzInList) {
          setSelectedTimezone(browserTimezone);
          localStorage.setItem("operational_logs_timezone", browserTimezone);
        } else {
          const browserRegion = browserTimezone.split("/")[0];
          const similarTz = timezones.find(tz => tz.startsWith(browserRegion + "/"));
          if (similarTz) {
            setSelectedTimezone(similarTz);
            localStorage.setItem("operational_logs_timezone", similarTz);
          } else {
            setSelectedTimezone(timezones[0]);
            localStorage.setItem("operational_logs_timezone", timezones[0]);
          }
        }
      } else if (selectedTimezone) {
        localStorage.setItem("operational_logs_timezone", selectedTimezone);
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
        localStorage.setItem("operational_logs_startDate", startStr);
        localStorage.setItem("operational_logs_endDate", endStr);
      }
    } catch (e: any) {
      console.error("Error loading filter options:", e);
    }
  };

  const loadLogs = async () => {
    setLoading(true);
    setError(null);
    try {
      const payload: LogFilter = {
        ...filters,
      };

      // Agregar filtros solo si tienen valores
      if (selectedUsernames.length > 0) {
        payload.usernames = selectedUsernames;
      }
      if (selectedAlarmNames.length > 0) {
        payload.alarm_names = selectedAlarmNames;
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

      const response = await filterLogs(payload);
      
      // El backend ahora siempre retorna un objeto con paginación
      setLogs(response.data || []);
      setPagination({
        page: response.pagination.page || 1,
        limit: response.pagination.limit || 20,
        total: response.pagination.total_records || 0,
        pages: response.pagination.total_pages || 0,
      });
    } catch (e: any) {
      const errorMsg = e?.response?.data?.message || e?.message || "Error al cargar los logs";
      setError(errorMsg);
      setLogs([]);
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
    localStorage.setItem("operational_logs_page", "1");
    localStorage.setItem("operational_logs_limit", String(newFilters.limit || 20));
  };

  const handlePresetDateChange = (preset: PresetDate) => {
    setPresetDate(preset);
    localStorage.setItem("operational_logs_presetDate", preset);
    if (preset !== "Custom") {
      const { start, end } = getPresetDateRange(preset);
      const now = new Date();
      const finalEnd = end > now ? now : end;
      const startStr = formatToLocalDateTime(start);
      const endStr = formatToLocalDateTime(finalEnd);
      setStartDate(startStr);
      setEndDate(endStr);
      localStorage.setItem("operational_logs_startDate", startStr);
      localStorage.setItem("operational_logs_endDate", endStr);
    }
  };

  const handleEndDateChange = (value: string) => {
    const selectedEnd = new Date(value);
    const now = new Date();
    const finalValue = selectedEnd > now ? formatToLocalDateTime(now) : value;
    setEndDate(finalValue);
    localStorage.setItem("operational_logs_endDate", finalValue);
  };

  const handleAddLog = async () => {
    if (!newLogMessage.trim()) {
      setError(t("operationalLogs.messageRequired"));
      return;
    }

    setAddingLog(true);
    setError(null);
    try {
      await createLog({
        message: newLogMessage.trim(),
      });
      setNewLogMessage("");
      setShowAddLogModal(false);
      // Recargar logs
      loadLogs();
    } catch (e: any) {
      const errorMsg =
        e?.response?.data?.message ||
        e?.message ||
        t("operationalLogs.createLogError");
      setError(errorMsg);
    } finally {
      setAddingLog(false);
    }
  };

  const handleClearFilters = () => {
    setSelectedUsernames([]);
    setSelectedAlarmNames([]);
    localStorage.removeItem("operational_logs_selectedUsernames");
    localStorage.removeItem("operational_logs_selectedAlarmNames");
    setPresetDate("Last Hour");
    localStorage.setItem("operational_logs_presetDate", "Last Hour");
    const { start, end } = getPresetDateRange("Last Hour");
    const now = new Date();
    const finalEnd = end > now ? now : end;
    const startStr = formatToLocalDateTime(start);
    const endStr = formatToLocalDateTime(finalEnd);
    setEndDate(endStr);
    setStartDate(startStr);
    localStorage.setItem("operational_logs_startDate", startStr);
    localStorage.setItem("operational_logs_endDate", endStr);
    setFilters({
      page: 1,
      limit: 20,
    });
    localStorage.setItem("operational_logs_page", "1");
    localStorage.setItem("operational_logs_limit", "20");
  };

  const handlePageChange = (newPage: number) => {
    if (newPage >= 1 && newPage <= pagination.pages) {
      setFilters({ ...filters, page: newPage });
      localStorage.setItem("operational_logs_page", String(newPage));
    }
  };

  const handleLimitChange = (newLimit: number) => {
    if (newLimit > 0) {
      setFilters({ ...filters, page: 1, limit: newLimit });
      localStorage.setItem("operational_logs_page", "1");
      localStorage.setItem("operational_logs_limit", String(newLimit));
    }
  };

  const handleExportCSV = async () => {
    try {
      setError(null);
      
      const payload: LogFilter = {
        ...filters,
        page: 1,
        limit: 10000,
      };

      if (selectedUsernames.length > 0) {
        payload.usernames = selectedUsernames;
      }
      if (selectedAlarmNames.length > 0) {
        payload.alarm_names = selectedAlarmNames;
      }
      if (startDate) {
        payload.greater_than_timestamp = formatDateTimeForBackend(startDate);
      }
      if (endDate) {
        payload.less_than_timestamp = formatDateTimeForBackend(endDate);
      }

      const timezoneToUse = selectedTimezone || Intl.DateTimeFormat().resolvedOptions().timeZone;
      payload.timezone = timezoneToUse;

      const response = await filterLogs(payload);
      const allLogs = response.data || [];

      if (!allLogs || allLogs.length === 0) {
        setError(t("operationalLogs.noDataToExport"));
        return;
      }

      const headers = [
        t("tables.id"),
        t("tables.timestamp"),
        t("tables.user"),
        t("tables.message"),
        t("tables.description"),
        t("tables.classification"),
        t("tables.alarm"),
        t("tables.event"),
      ];

      const rows = allLogs.map((log: Log) => {
        return [
          log.id || "",
          log.timestamp || "",
          log.user?.username || "",
          log.message || "",
          log.description || "",
          log.classification || "",
          log.alarm?.name || "",
          log.event?.id || "",
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
        `operational_logs_${new Date().toISOString().split("T")[0]}.csv`
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
        t("operationalLogs.exportError");
      setError(errorMsg);
    }
  };

  return (
    <div className="row">
      <div className="col-12">
        <Card
          title={
            <div className="d-flex align-items-center gap-2 w-100 flex-wrap">
              <span className="me-auto">{t("navigation.operationalLogs")}</span>
              <div className="d-flex align-items-center gap-2">
                <div className="d-flex align-items-center gap-1">
                  <label className="form-label small mb-0 me-1">
                    {t("operationalLogs.range")}
                  </label>
                  <select
                    className="form-select form-select-sm"
                    style={{ width: "150px" }}
                    value={presetDate}
                    onChange={(e) => handlePresetDateChange(e.target.value as PresetDate)}
                  >
                    {PRESET_DATES.map((preset) => (
                      <option key={preset} value={preset}>
                        {t(`operationalLogs.preset.${preset}`)}
                      </option>
                    ))}
                  </select>
                </div>
                {presetDate === "Custom" && (
                  <>
                    <div className="d-flex align-items-center gap-1">
                      <label className="form-label small mb-0 me-1">
                        {t("operationalLogs.start")}
                      </label>
                      <input
                        type="datetime-local"
                        className="form-control form-control-sm"
                        style={{ width: "180px" }}
                        value={startDate}
                        onChange={(e) => {
                          setStartDate(e.target.value);
                          localStorage.setItem("operational_logs_startDate", e.target.value);
                        }}
                      />
                    </div>
                    <div className="d-flex align-items-center gap-1">
                      <label className="form-label small mb-0 me-1">
                        {t("operationalLogs.end")}
                      </label>
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
                <Button
                  variant="primary"
                  className="btn-sm"
                  onClick={handleApplyFilters}
                  disabled={loading}
                >
                  {t("common.filter")}
                </Button>
                <Button
                  variant="success"
                  className="btn-sm"
                  onClick={() => setShowAddLogModal(true)}
                  disabled={loading}
                >
                  <i className="bi bi-plus-circle me-1"></i>
                  {t("operationalLogs.add")}
                </Button>
                <Button
                  variant="primary"
                  className="btn-sm"
                  onClick={handleExportCSV}
                  disabled={loading || logs.length === 0}
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

          {/* Filtros */}
          <div className="mb-3">
            <div className="d-flex align-items-center gap-2 flex-wrap">
              <label className="form-label mb-0 me-2">
                {t("operationalLogs.usernames")}
              </label>
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
                        localStorage.setItem("operational_logs_selectedUsernames", JSON.stringify(newSelectedUsernames));
                      }}
                    >
                      {user.username}
                    </button>
                  );
                })}
              </div>
            </div>
          </div>

          <div className="mb-3">
            <div className="d-flex align-items-center gap-2 flex-wrap">
              <label className="form-label mb-0 me-2">
                {t("operationalLogs.alarmNames")}
              </label>
              <div className="d-flex align-items-center gap-2 flex-wrap">
                {availableAlarmNames.map((alarmName) => {
                  const isSelected = selectedAlarmNames.includes(alarmName);
                  return (
                    <button
                      key={alarmName}
                      type="button"
                      className={`btn btn-sm ${isSelected ? "btn-primary" : "btn-outline-secondary"}`}
                      onClick={() => {
                        const newSelectedAlarmNames = isSelected
                          ? selectedAlarmNames.filter((a) => a !== alarmName)
                          : [...selectedAlarmNames, alarmName];
                        setSelectedAlarmNames(newSelectedAlarmNames);
                        localStorage.setItem("operational_logs_selectedAlarmNames", JSON.stringify(newSelectedAlarmNames));
                      }}
                    >
                      {alarmName}
                    </button>
                  );
                })}
              </div>
            </div>
          </div>

          {loading && (
            <div className="text-center py-4">
              <div className="spinner-border text-primary" role="status">
                <span className="visually-hidden">{t("common.loading")}</span>
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
                    <th>{t("tables.alarm")}</th>
                    <th>{t("tables.event")}</th>
                  </tr>
                </thead>
                <tbody>
                  {logs.length === 0 ? (
                    <tr>
                      <td colSpan={8} className="text-center text-muted py-4">
                        {t("operationalLogs.noLogs")}
                      </td>
                    </tr>
                  ) : (
                    logs.map((log) => (
                      <tr key={log.id}>
                        <td>{log.id || "-"}</td>
                        <td>{log.timestamp || "-"}</td>
                        <td>{log.user?.username || "-"}</td>
                        <td>{log.message || "-"}</td>
                        <td>{log.description || "-"}</td>
                        <td>{log.classification || "-"}</td>
                        <td>{log.alarm?.name || "-"}</td>
                        <td>{log.event?.id || "-"}</td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
          )}

          {/* Modal para agregar log */}
          {showAddLogModal && (
            <div
              className="modal show d-block"
              style={{ backgroundColor: "rgba(0,0,0,0.5)" }}
              onClick={() => setShowAddLogModal(false)}
            >
              <div className="modal-dialog" onClick={(e) => e.stopPropagation()}>
                <div className="modal-content">
                  <div className="modal-header">
                    <h5 className="modal-title">
                      {t("operationalLogs.addOperationalLog")}
                    </h5>
                    <button
                      type="button"
                      className="btn-close"
                      onClick={() => setShowAddLogModal(false)}
                    ></button>
                  </div>
                  <div className="modal-body">
                    <div className="mb-3">
                      <label className="form-label">
                        {t("operationalLogs.messageLabel")}
                      </label>
                      <textarea
                        className="form-control"
                        rows={4}
                        value={newLogMessage}
                        onChange={(e) => setNewLogMessage(e.target.value)}
                        placeholder={t("operationalLogs.messagePlaceholder")}
                      />
                    </div>
                  </div>
                  <div className="modal-footer">
                    <Button
                      variant="secondary"
                      onClick={() => {
                        setShowAddLogModal(false);
                        setNewLogMessage("");
                      }}
                      disabled={addingLog}
                    >
                      {t("common.cancel")}
                    </Button>
                    <Button
                      variant="primary"
                      onClick={handleAddLog}
                      disabled={addingLog || !newLogMessage.trim()}
                      loading={addingLog}
                    >
                      {t("operationalLogs.add")}
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
