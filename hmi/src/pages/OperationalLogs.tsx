import { useEffect, useMemo, useState } from "react";
import { Card } from "../components/Card";
import { Button } from "../components/Button";
import { HistoryResults } from "../components/HistoryResults";
import { MultiSelectSearch } from "../components/MultiSelectSearch";
import { AreaFilter } from "../components/AreaFilter";
import {
  filterLogs,
  createLog,
  type Log,
  type LogFilter,
} from "../services/logs";
import { getAllUsers, type User } from "../services/users";
import { getAlarms, type Alarm } from "../services/alarms";
import { isDbUnavailableError } from "../services/health";
import { socketService } from "../services/socket";
import { useTranslation } from "../hooks/useTranslation";
import { useDisplayTimezone } from "../hooks/useDisplayTimezone";
import { usePlantAreas } from "../hooks/usePlantAreas";
import {
  FILTER_COMPOSE_MS,
  FILTER_DATE_MS,
  FILTER_INSTANT_MS,
  FILTER_LIVE_MS,
  isRequestCanceled,
  useScheduledQuery,
  type ScheduledQueryContext,
} from "../hooks/useScheduledQuery";
import { formatDateTimeLocalForBackend, formatDateTimeLocalInput, formatOperatorTimestamp } from "../utils/timezone";

type PresetDate =
  | "Last Hour"
  | "Last 6 Hours"
  | "Last 12 Hours"
  | "Last Day"
  | "Last Week"
  | "Last Month"
  | "Custom";

type LogView = "notebook" | "comments" | "system" | "all";
type ShiftValue = "" | "morning" | "afternoon" | "night";

const PRESET_DATES: PresetDate[] = [
  "Last Hour",
  "Last 6 Hours",
  "Last 12 Hours",
  "Last Day",
  "Last Week",
  "Last Month",
  "Custom",
];

const WATCHDOG_DESCRIPTION = "memory-watchdog";
const NOTEBOOK_CLASSIFICATIONS = ["General", "Operational"];

function viewFilters(view: LogView): Pick<LogFilter, "classifications" | "exclude_description"> {
  if (view === "notebook") {
    return {
      classifications: NOTEBOOK_CLASSIFICATIONS,
      exclude_description: WATCHDOG_DESCRIPTION,
    };
  }
  if (view === "comments") {
    return { classifications: ["Event", "Alarm"] };
  }
  if (view === "system") {
    return { classifications: ["System"] };
  }
  return {};
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

export function OperationalLogs() {
  const { t, locale } = useTranslation();
  const { timeZone } = useDisplayTimezone();
  const plantAreas = usePlantAreas();
  const { schedule, flushPending, setRunner, isCurrent } = useScheduledQuery();
  const [logs, setLogs] = useState<Log[]>([]);
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

  // Valores seleccionados en los filtros
  const [selectedUsernames, setSelectedUsernames] = useState<string[]>(() => {
    const saved = localStorage.getItem("operational_logs_selectedUsernames");
    return saved ? JSON.parse(saved) : [];
  });
  const [selectedAlarmNames, setSelectedAlarmNames] = useState<string[]>(() => {
    const saved = localStorage.getItem("operational_logs_selectedAlarmNames");
    return saved ? JSON.parse(saved) : [];
  });
  const [selectedArea, setSelectedArea] = useState("");
  const [presetDate, setPresetDate] = useState<PresetDate>(() => {
    const saved = localStorage.getItem("operational_logs_presetDate");
    return (saved as PresetDate) || "Last Day";
  });
  const [startDate, setStartDate] = useState<string>(() => {
    return localStorage.getItem("operational_logs_startDate") || "";
  });
  const [endDate, setEndDate] = useState<string>(() => {
    return localStorage.getItem("operational_logs_endDate") || "";
  });

  // Estado para el formulario de agregar log
  const [showAddLogModal, setShowAddLogModal] = useState(false);
  const [newLogMessage, setNewLogMessage] = useState("");
  const [newLogShift, setNewLogShift] = useState<ShiftValue>("");
  const [newLogArea, setNewLogArea] = useState("");
  const [newLogHandover, setNewLogHandover] = useState(false);
  const [addingLog, setAddingLog] = useState(false);
  const [searchText, setSearchText] = useState(
    () => localStorage.getItem("operational_logs_search") || ""
  );
  const [logView, setLogView] = useState<LogView>(() => {
    const saved = localStorage.getItem("operational_logs_view");
    return (saved as LogView) || "notebook";
  });

  // Cargar opciones para los filtros
  useEffect(() => {
    loadFilterOptions();
  }, []);

  useEffect(() => {
    setRunner((ctx) => loadLogs(ctx));
  });

  useEffect(() => {
    schedule(FILTER_INSTANT_MS);
  }, [timeZone, selectedArea, schedule]);

  useEffect(() => {
    return socketService.onLogUpdate(() => {
      schedule(FILTER_LIVE_MS);
    });
  }, [schedule]);

  // Función helper para convertir Date a formato datetime-local (sin UTC)
  const formatToLocalDateTime = (date: Date): string => formatDateTimeLocalInput(date);

  // Función para convertir el formato de fecha del input al formato esperado por el backend
  const formatDateTimeForBackend = (dateTimeString: string): string => {
    return formatDateTimeLocalForBackend(dateTimeString, timeZone);
  };

  const resolveQueryWindow = (forWrite = false): { start: string; end: string } => {
    if (presetDate !== "Custom") {
      const { start, end } = getPresetDateRange(presetDate);
      return {
        start: formatToLocalDateTime(start),
        end: formatToLocalDateTime(end),
      };
    }
    if (forWrite) {
      const now = formatToLocalDateTime(new Date());
      return {
        start: startDate,
        end: !endDate || endDate < now ? now : endDate,
      };
    }
    return { start: startDate, end: endDate };
  };

  const loadFilterOptions = async () => {
    try {
      // Cargar usuarios
      const users = await getAllUsers();
      setAvailableUsers(users);

      // Cargar nombres de alarmas
      try {
        const alarmsResponse = await getAlarms(1, 5000);
        const alarmNames = alarmsResponse.data?.map((alarm: Alarm) => alarm.name).filter(Boolean) || [];
        const uniqueAlarmNames = Array.from(new Set(alarmNames));
        setAvailableAlarmNames(uniqueAlarmNames);
      } catch (e) {
        console.error("Error loading alarm names:", e);
      }

      // Establecer fechas por defecto solo si no hay fechas guardadas
      if (!startDate || !endDate) {
        const { start, end } = getPresetDateRange("Last Day");
        const now = new Date();
        const finalEnd = end > now ? now : end;
        const startStr = formatToLocalDateTime(start);
        const endStr = formatToLocalDateTime(finalEnd);
        setEndDate(endStr);
        setStartDate(startStr);
        localStorage.setItem("operational_logs_startDate", startStr);
        localStorage.setItem("operational_logs_endDate", endStr);
        schedule(FILTER_INSTANT_MS);
      }
    } catch (e: any) {
      console.error("Error loading filter options:", e);
    }
  };

  const resetToFirstPage = () => {
    localStorage.setItem("operational_logs_page", "1");
    setFilters((prev) => (prev.page === 1 ? prev : { ...prev, page: 1 }));
  };

  const loadLogs = async ({ signal, generation }: ScheduledQueryContext) => {
    setLoading(true);
    setError(null);
    try {
      const payload: LogFilter = {
        ...filters,
      };

      if (selectedUsernames.length > 0) {
        payload.usernames = selectedUsernames;
      }
      if (selectedAlarmNames.length > 0) {
        payload.alarm_names = selectedAlarmNames;
      }
      const trimmedSearch = searchText.trim();
      if (trimmedSearch) {
        payload.search = trimmedSearch;
      }
      Object.assign(payload, viewFilters(logView));
      const queryWindow = resolveQueryWindow(true);
      if (queryWindow.start) {
        payload.greater_than_timestamp = formatDateTimeForBackend(queryWindow.start);
      }
      if (queryWindow.end) {
        payload.less_than_timestamp = formatDateTimeForBackend(queryWindow.end);
      }

      payload.timezone = timeZone;
      if (selectedArea) {
        payload.area = selectedArea;
      }

      const response = await filterLogs(payload, { signal });
      if (!isCurrent(generation, signal)) return;

      setLogs(response.data || []);
      setPagination({
        page: response.pagination.page || 1,
        limit: response.pagination.limit || 20,
        total: response.pagination.total_records || 0,
        pages: response.pagination.total_pages || 0,
      });
      setHasLoaded(true);
    } catch (e: any) {
      if (isRequestCanceled(e) || !isCurrent(generation, signal)) return;
      if (isDbUnavailableError(e)) {
        setError(null);
        setHasLoaded(true);
        return;
      }
      const errorMsg = e?.response?.data?.message || e?.message || "Error al cargar los logs";
      setError(errorMsg);
      setHasLoaded(true);
    } finally {
      if (isCurrent(generation, signal)) {
        setLoading(false);
      }
    }
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
      resetToFirstPage();
      schedule(FILTER_INSTANT_MS);
    }
  };

  const handleEndDateChange = (value: string) => {
    const selectedEnd = new Date(value);
    const now = new Date();
    const finalValue = selectedEnd > now ? formatToLocalDateTime(now) : value;
    setEndDate(finalValue);
    localStorage.setItem("operational_logs_endDate", finalValue);
    resetToFirstPage();
    schedule(FILTER_DATE_MS);
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
        shift: newLogShift || undefined,
        area: newLogArea.trim() || undefined,
        handover: newLogHandover,
      });
      setNewLogMessage("");
      setNewLogShift("");
      setNewLogArea("");
      setNewLogHandover(false);
      setShowAddLogModal(false);
      const window = resolveQueryWindow(true);
      setStartDate(window.start);
      setEndDate(window.end);
      localStorage.setItem("operational_logs_startDate", window.start);
      localStorage.setItem("operational_logs_endDate", window.end);
      if (logView !== "notebook" && logView !== "all") {
        setLogView("notebook");
        localStorage.setItem("operational_logs_view", "notebook");
      }
      const nextFilters = { ...filters, page: 1 };
      setFilters(nextFilters);
      localStorage.setItem("operational_logs_page", "1");
      schedule(FILTER_INSTANT_MS);
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

  const userOptions = useMemo(
    () =>
      availableUsers.map((user) => ({
        value: user.username,
        label: user.username,
        description: user.role?.name,
      })),
    [availableUsers]
  );

  const alarmOptions = useMemo(
    () =>
      availableAlarmNames.map((name) => ({
        value: name,
        label: name,
      })),
    [availableAlarmNames]
  );

  const handleUsernamesChange = (next: string[]) => {
    setSelectedUsernames(next);
    localStorage.setItem("operational_logs_selectedUsernames", JSON.stringify(next));
    resetToFirstPage();
    schedule(FILTER_COMPOSE_MS);
  };

  const handleAlarmNamesChange = (next: string[]) => {
    setSelectedAlarmNames(next);
    localStorage.setItem("operational_logs_selectedAlarmNames", JSON.stringify(next));
    resetToFirstPage();
    schedule(FILTER_COMPOSE_MS);
  };

  const handlePageChange = (newPage: number) => {
    if (newPage >= 1 && newPage <= pagination.pages) {
      setFilters({ ...filters, page: newPage });
      localStorage.setItem("operational_logs_page", String(newPage));
      schedule(FILTER_INSTANT_MS);
    }
  };

  const handleLimitChange = (newLimit: number) => {
    if (newLimit > 0) {
      setFilters({ ...filters, page: 1, limit: newLimit });
      localStorage.setItem("operational_logs_page", "1");
      localStorage.setItem("operational_logs_limit", String(newLimit));
      schedule(FILTER_INSTANT_MS);
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
      const trimmedSearch = searchText.trim();
      if (trimmedSearch) {
        payload.search = trimmedSearch;
      }
      Object.assign(payload, viewFilters(logView));
      if (startDate) {
        payload.greater_than_timestamp = formatDateTimeForBackend(startDate);
      }
      if (endDate) {
        payload.less_than_timestamp = formatDateTimeForBackend(endDate);
      }

      payload.timezone = timeZone;
      if (selectedArea) {
        payload.area = selectedArea;
      }

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
        t("tables.shift"),
        t("tables.area"),
        t("tables.handover"),
        t("tables.alarm"),
        t("tables.event"),
      ];

      const rows = allLogs.map((log: Log) => {
        return [
          log.id || "",
          log.timestamp ? formatOperatorTimestamp(log.timestamp, locale) : "",
          log.user?.username || log.user_name || "",
          log.message || "",
          log.description || "",
          log.classification || "",
          log.shift || "",
          log.area || "",
          log.handover ? t("common.yes") : t("common.no"),
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
    <div className="row g-0 page-fit-viewport">
      <div className="col-12 h-100">
        <Card
          className="page-fit-card"
          title={
            <div className="card-header-stack w-100">
              <div className="d-flex align-items-center gap-2 w-100 flex-wrap">
                <span className="me-auto">{t("navigation.operationalLogs")}</span>
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
                  <div className="d-flex align-items-center gap-1">
                    <label className="form-label small mb-0 me-1">
                      {t("operationalLogs.viewLabel")}
                    </label>
                    <select
                      className="form-select form-select-sm"
                      style={{ width: "140px", maxWidth: "100%" }}
                      value={logView}
                      onChange={(e) => {
                        const next = e.target.value as LogView;
                        setLogView(next);
                        localStorage.setItem("operational_logs_view", next);
                        resetToFirstPage();
                        schedule(FILTER_INSTANT_MS);
                      }}
                    >
                      <option value="notebook">{t("operationalLogs.viewNotebook")}</option>
                      <option value="comments">{t("operationalLogs.viewComments")}</option>
                      <option value="system">{t("operationalLogs.viewSystem")}</option>
                      <option value="all">{t("operationalLogs.viewAll")}</option>
                    </select>
                  </div>
                  <input
                    type="search"
                    className="form-control form-control-sm"
                    style={{ width: "180px", maxWidth: "100%" }}
                    value={searchText}
                    onChange={(e) => {
                      setSearchText(e.target.value);
                      localStorage.setItem("operational_logs_search", e.target.value);
                      resetToFirstPage();
                      schedule(FILTER_COMPOSE_MS);
                    }}
                    onKeyDown={(e) => {
                      if (e.key === "Enter") {
                        resetToFirstPage();
                        schedule(FILTER_INSTANT_MS);
                      }
                    }}
                    placeholder={t("operationalLogs.searchPlaceholder")}
                  />
                  <MultiSelectSearch
                    options={userOptions}
                    selected={selectedUsernames}
                    onChange={handleUsernamesChange}
                    onClose={flushPending}
                    placeholder={t("operationalLogs.selectUsersPlaceholder")}
                    searchPlaceholder={t("operationalLogs.searchUsers")}
                    emptyText={t("operationalLogs.noUsersFound")}
                    selectAllLabel={t("operationalLogs.selectAll")}
                    clearLabel={t("common.clear")}
                    selectedCountLabel={(count) =>
                      t("operationalLogs.selectedCount", { count })
                    }
                    style={{ width: "200px", maxWidth: "100%" }}
                  />
                  <MultiSelectSearch
                    options={alarmOptions}
                    selected={selectedAlarmNames}
                    onChange={handleAlarmNamesChange}
                    onClose={flushPending}
                    placeholder={t("operationalLogs.selectAlarmsPlaceholder")}
                    searchPlaceholder={t("operationalLogs.searchAlarms")}
                    emptyText={t("operationalLogs.noAlarmsFound")}
                    selectAllLabel={t("operationalLogs.selectAll")}
                    clearLabel={t("common.clear")}
                    selectedCountLabel={(count) =>
                      t("operationalLogs.selectedCount", { count })
                    }
                    style={{ width: "200px", maxWidth: "100%" }}
                  />
                  <select
                    className="form-select form-select-sm"
                    style={{ width: "150px", maxWidth: "100%" }}
                    value={presetDate}
                    onChange={(e) => handlePresetDateChange(e.target.value as PresetDate)}
                  >
                    {PRESET_DATES.map((preset) => (
                      <option key={preset} value={preset}>
                        {t(`operationalLogs.preset.${preset}`)}
                      </option>
                    ))}
                  </select>
                  <Button
                    variant="success"
                    className="btn-sm"
                    onClick={() => setShowAddLogModal(true)}
                  >
                    <i className="bi bi-plus-circle me-1"></i>
                    {t("operationalLogs.add")}
                  </Button>
                  <Button
                    variant="primary"
                    className="btn-sm"
                    onClick={handleExportCSV}
                    disabled={logs.length === 0}
                  >
                    <i className="bi bi-download me-1"></i>
                    CSV
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
                      localStorage.setItem("operational_logs_startDate", e.target.value);
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
            <div className="table-responsive">
              <table className="table table-striped table-hover table-sm">
                <thead>
                  <tr>
                    <th>{t("tables.id")}</th>
                    <th>{t("tables.timestamp")}</th>
                    <th>{t("tables.user")}</th>
                    <th>{t("tables.shift")}</th>
                    <th>{t("tables.area")}</th>
                    <th>{t("tables.message")}</th>
                    <th>{t("tables.description")}</th>
                    <th>{t("tables.classification")}</th>
                    <th>{t("tables.handover")}</th>
                    <th>{t("tables.alarm")}</th>
                    <th>{t("tables.event")}</th>
                  </tr>
                </thead>
                <tbody>
                  {logs.length === 0 ? (
                    <tr>
                      <td colSpan={11} className="text-center text-muted py-4">
                        {t("operationalLogs.noLogs")}
                      </td>
                    </tr>
                  ) : (
                    logs.map((log) => (
                      <tr key={log.id ?? `${log.timestamp}-${log.message}`}>
                        <td>{log.id || (log.journaled ? "SAF" : "-")}</td>
                        <td>{formatOperatorTimestamp(log.timestamp, locale)}</td>
                        <td>{log.user?.username || log.user_name || "-"}</td>
                        <td>
                          {log.shift
                            ? t(`operationalLogs.shift${log.shift.charAt(0).toUpperCase()}${log.shift.slice(1)}`)
                            : "-"}
                        </td>
                        <td>{log.area || "-"}</td>
                        <td>
                          {log.message || "-"}
                          {log.journaled ? (
                            <div className="small text-muted">{t("operationalLogs.journaledHint")}</div>
                          ) : null}
                        </td>
                        <td>{log.description || "-"}</td>
                        <td>{log.classification || "-"}</td>
                        <td>{log.handover ? t("common.yes") : t("common.no")}</td>
                        <td>{log.alarm?.name || "-"}</td>
                        <td>{log.event?.id || "-"}</td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
          </HistoryResults>

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
                        maxLength={256}
                        value={newLogMessage}
                        onChange={(e) => setNewLogMessage(e.target.value)}
                        placeholder={t("operationalLogs.messagePlaceholder")}
                      />
                    </div>
                    <div className="row">
                      <div className="col-md-6 mb-3">
                        <label className="form-label">
                          {t("operationalLogs.shiftLabel")}
                        </label>
                        <select
                          className="form-select"
                          value={newLogShift}
                          onChange={(e) => setNewLogShift(e.target.value as ShiftValue)}
                        >
                          <option value="">{t("operationalLogs.shiftNone")}</option>
                          <option value="morning">{t("operationalLogs.shiftMorning")}</option>
                          <option value="afternoon">{t("operationalLogs.shiftAfternoon")}</option>
                          <option value="night">{t("operationalLogs.shiftNight")}</option>
                        </select>
                      </div>
                      <div className="col-md-6 mb-3">
                        <label className="form-label">
                          {t("operationalLogs.areaLabel")}
                        </label>
                        <input
                          type="text"
                          className="form-control"
                          maxLength={64}
                          value={newLogArea}
                          onChange={(e) => setNewLogArea(e.target.value)}
                          placeholder={t("operationalLogs.areaPlaceholder")}
                        />
                      </div>
                    </div>
                    <div className="form-check">
                      <input
                        className="form-check-input"
                        type="checkbox"
                        id="operational-log-handover"
                        checked={newLogHandover}
                        onChange={(e) => setNewLogHandover(e.target.checked)}
                      />
                      <label className="form-check-label" htmlFor="operational-log-handover">
                        {t("operationalLogs.handoverLabel")}
                      </label>
                    </div>
                  </div>
                  <div className="modal-footer">
                    <Button
                      variant="secondary"
                      onClick={() => {
                        setShowAddLogModal(false);
                        setNewLogMessage("");
                        setNewLogShift("");
                        setNewLogArea("");
                        setNewLogHandover(false);
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
