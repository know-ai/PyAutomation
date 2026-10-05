import { useCallback, useEffect, useState, useMemo, useRef, type ReactNode } from "react";
import { Card } from "../components/Card";
import { Button } from "../components/Button";
import { MultiSelectSearch, type MultiSelectOption } from "../components/MultiSelectSearch";
import { getMachines, transitionMachine, type Machine } from "../services/machines";
import { getMachinesSummaryColumns, putMachinesSummaryColumns } from "../services/machinesSummaryColumns";
import { useTranslation } from "../hooks/useTranslation";
import { showToast } from "../utils/toast";
import { useAppSelector } from "../hooks/useAppSelector";
import { useAppDispatch } from "../hooks/useAppDispatch";
import { loadAllMachines } from "../store/slices/machinesSlice";
import { socketService } from "../services/socket";
import { tx, translateMachineClassification } from "../utils/domainI18n";
import { criticityBadgeStyle } from "../utils/criticityBadge";
import { useAuthz } from "../hooks/useAuthz";
import { useOperatorConfirmation } from "../components/OperatorConfirmationProvider";
import { actorMayConfigureMachineColumns } from "../utils/userAccount";
import {
  DEFAULT_SUMMARY_COLUMNS,
  normalizeSummaryColumns,
  uniqueMachineColumnKeys,
} from "../utils/machinesSummaryColumns";
import { useShowInfraMachines } from "../hooks/useShowInfraMachines";
import { visibleMachineTabs } from "../utils/infraMachines";
import { LeakLikelihoodBar } from "../components/LeakLikelihoodBar";

const ITEMS_PER_PAGE = 10;

function columnLabel(t: (key: string, params?: Record<string, string | number>) => string, key: string) {
  return tx(t, key.replace(/_/g, " "), `machines.attrs.${key}`);
}

function formatCsvCell(t: (key: string, params?: Record<string, string | number>) => string, machine: Machine, key: string) {
  const value = machine[key];
  if (value == null || value === "") return "";
  if (key === "classification") return translateMachineClassification(t, String(value));
  if (typeof value === "object" && value && "value" in value) {
    const raw = (value as { value?: unknown; unit?: unknown }).value;
    const unit = (value as { unit?: unknown }).unit;
    if (raw == null || raw === "") return "";
    return unit ? `${raw} ${unit}` : String(raw);
  }
  return String(value);
}

function CriticityBadge({ value }: { value: number | undefined }) {
  if (value === undefined || value === null) return <>-</>;
  const numeric = typeof value === "number" ? value : Number(value);
  const badge = Number.isFinite(numeric) ? criticityBadgeStyle(numeric) : null;
  if (!badge) return <>{String(value)}</>;
  return (
    <span className={badge.className} style={badge.style}>
      {numeric}
    </span>
  );
}

export function Machines() {
  const { t } = useTranslation();
  const { confirm } = useOperatorConfirmation();
  const { canExportCsv } = useAuthz();
  const { showInfra } = useShowInfraMachines();
  const dispatch = useAppDispatch();
  const role = useAppSelector((state) => state.auth.user?.role);
  const canConfigureColumns = actorMayConfigureMachineColumns(role);
  const realTimeMachines = useAppSelector((state) => state.machines.machines);
  const [savedColumns, setSavedColumns] = useState<string[] | null>(null);
  const [machines, setMachines] = useState<Machine[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [currentPage, setCurrentPage] = useState(1);
  const [updatingMachine, setUpdatingMachine] = useState<string | null>(null);

  // Estado para el modal de confirmación de transición
  const [showTransitionModal, setShowTransitionModal] = useState(false);
  const [pendingTransition, setPendingTransition] = useState<{
    machineName: string;
    oldState: string;
    newState: string;
  } | null>(null);

  // Buffer para actualizaciones de máquinas en tiempo real (patrón de 1 segundo)
  const pendingMachineUpdatesRef = useRef<Map<string, Machine>>(new Map());
  const machineUpdateIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const machineNamesRef = useRef<Set<string>>(new Set());

  // Cargar máquinas
  const loadMachines = async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await getMachines();
      setMachines(data);
      machineNamesRef.current = new Set(
        (data || []).map((machine) => machine.name).filter((name): name is string => Boolean(name))
      );
      // Cargar máquinas iniciales en el store para sincronizar con tiempo real
      dispatch(loadAllMachines(data));
    } catch (err: any) {
      const data = err?.response?.data;
      const backendMessage =
        (typeof data === "string" ? data : undefined) ??
        data?.message ??
        data?.detail ??
        data?.error;
      const errorMessage =
        backendMessage || err?.message || t("machines.loadError");
      setError(errorMessage);
      console.error("Error loading machines:", err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadMachines();
  }, [dispatch]);

  useEffect(() => {
    let cancelled = false;
    getMachinesSummaryColumns()
      .then((loaded) => {
        if (!cancelled) setSavedColumns(loaded);
      })
      .catch(() => {
        if (!cancelled) setSavedColumns([...DEFAULT_SUMMARY_COLUMNS]);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  // Suscripción a eventos de máquinas en tiempo real con buffering
  useEffect(() => {
    // Función para aplicar las actualizaciones pendientes
    const flushMachineUpdates = () => {
      if (pendingMachineUpdatesRef.current.size === 0) {
        return;
      }

      // Aplicar todas las actualizaciones acumuladas
      setMachines((prev) => {
        const updated = [...prev];
        let hasUpdates = false;

        // Iterar sobre todas las actualizaciones pendientes
        pendingMachineUpdatesRef.current.forEach((updatedMachine, machineName) => {
          // Buscar la máquina en el array actual
          const index = updated.findIndex((m) => m.name === machineName);
          
          if (index !== -1) {
            hasUpdates = true;
            // Actualizar la máquina con los nuevos datos
            updated[index] = updatedMachine;
          }
        });

        // Limpiar el buffer después de aplicar
        pendingMachineUpdatesRef.current.clear();

        return hasUpdates ? updated : prev;
      });
    };

    // Iniciar intervalo para hacer flush cada 1 segundo
    machineUpdateIntervalRef.current = setInterval(() => {
      if (typeof document !== "undefined" && document.hidden) {
        return;
      }
      flushMachineUpdates();
    }, 1000);

    // Suscribirse a actualizaciones de máquinas
    const cleanup = socketService.onMachineUpdate((machine) => {
      if (machine.name && machineNamesRef.current.has(machine.name)) {
        pendingMachineUpdatesRef.current.set(machine.name, machine);
      }
    });

    // Cleanup al desmontar
    return () => {
      cleanup();
      if (machineUpdateIntervalRef.current) {
        clearInterval(machineUpdateIntervalRef.current);
        machineUpdateIntervalRef.current = null;
      }
      // Aplicar cualquier actualización pendiente antes de limpiar
      flushMachineUpdates();
      pendingMachineUpdatesRef.current.clear();
    };
  }, []); // Sin dependencias - se suscribe una sola vez

  // Combinar máquinas iniciales con actualizaciones en tiempo real
  const machinesWithRealTime = useMemo(() => {
    // Crear un mapa de máquinas iniciales
    const machinesMap = new Map<string, Machine>();
    machines.forEach((machine) => {
      if (machine.name) {
        machinesMap.set(machine.name, machine);
      }
    });

    // Actualizar con datos en tiempo real del store
    Object.values(realTimeMachines).forEach((realTimeMachine) => {
      if (realTimeMachine.name) {
        machinesMap.set(realTimeMachine.name, realTimeMachine);
      }
    });

    // Convertir de vuelta a array
    return Array.from(machinesMap.values());
  }, [machines, realTimeMachines]);

  const visibleMachines = useMemo(
    () => visibleMachineTabs(machinesWithRealTime, showInfra),
    [machinesWithRealTime, showInfra],
  );

  const availableColumns = useMemo(
    () => uniqueMachineColumnKeys(visibleMachines),
    [visibleMachines],
  );
  const columns = useMemo(
    () => normalizeSummaryColumns(savedColumns, availableColumns),
    [savedColumns, availableColumns],
  );

  const persistColumns = useCallback(
    (next: string[]) => {
      const normalized = normalizeSummaryColumns(next, availableColumns);
      setSavedColumns(normalized);
      putMachinesSummaryColumns(normalized).catch(() => {
        showToast(t("machines.columnsSaveError"), "error");
      });
    },
    [availableColumns, t],
  );

  const columnOptions = useMemo<MultiSelectOption[]>(
    () =>
      availableColumns.map((key) => ({
        value: key,
        label: columnLabel(t, key),
        description: key === "name" || key === "state" ? t("machines.columnsLocked") : undefined,
        locked: key === "name" || key === "state",
      })),
    [availableColumns, t],
  );
  const selectedCountLabel = useCallback(
    (count: number) => t("machines.columnsCount", { count }),
    [t],
  );

  // Paginación
  const totalPages = Math.ceil(visibleMachines.length / ITEMS_PER_PAGE);
  const paginatedMachines = useMemo(() => {
    const startIndex = (currentPage - 1) * ITEMS_PER_PAGE;
    const endIndex = startIndex + ITEMS_PER_PAGE;
    return visibleMachines.slice(startIndex, endIndex);
  }, [visibleMachines, currentPage]);

  useEffect(() => {
    const pages = Math.max(1, totalPages);
    if (currentPage > pages) {
      setCurrentPage(pages);
    }
  }, [currentPage, totalPages]);

  // Manejar cambio de estado
  const handleStateChange = (machine: Machine, newState: string) => {
    if (newState === machine.state) {
      return; // No hay cambio
    }

    // Mostrar modal de confirmación
    setPendingTransition({
      machineName: machine.name,
      oldState: machine.state,
      newState,
    });
    setShowTransitionModal(true);
  };

  // Confirmar transición
  const handleConfirmTransition = async () => {
    if (!pendingTransition) return;

    const target = pendingTransition.newState.trim().toLowerCase();
    let confirmation: string | null = null;
    if (target === "restart" || target === "restarting") {
      const confirmed = await confirm({
        method: "PUT",
        path: `/api/machines/${encodeURIComponent(pendingTransition.machineName)}/transition`,
        to: pendingTransition.newState,
        title: t("operatorConfirm.title"),
        detail: t("operatorConfirm.restart", { name: pendingTransition.machineName }),
      });
      if (!confirmed) return;
      confirmation = confirmed.token;
    }

    setUpdatingMachine(pendingTransition.machineName);
    try {
      const response = await transitionMachine(
        pendingTransition.machineName,
        pendingTransition.newState,
        confirmation
      );

      // Actualizar la máquina en el estado local
      setMachines((prev) =>
        prev.map((m) =>
          m.name === pendingTransition.machineName
            ? { ...m, ...response.data, state: pendingTransition.newState }
            : m
        )
      );
      // Recargar máquinas para sincronizar con el store
      loadMachines();

      // Mostrar mensaje amigable con detalles de la transición
      const successMessage = t("machines.transitionSuccessDetail", {
        machineName: pendingTransition.machineName,
        oldState: pendingTransition.oldState,
        newState: pendingTransition.newState,
      });
      showToast(successMessage, "success");
      setShowTransitionModal(false);
      setPendingTransition(null);
    } catch (err: any) {
      const data = err?.response?.data;
      const backendMessage =
        (typeof data === "string" ? data : undefined) ??
        data?.message ??
        data?.detail ??
        data?.error;
      
      // Crear mensaje de error más amigable
      let errorMessage: string;
      if (backendMessage || err?.message) {
        // Si hay un mensaje del backend, crear un mensaje más amigable
        errorMessage = t("machines.transitionErrorDetail", {
          machineName: pendingTransition?.machineName || "",
          newState: pendingTransition?.newState || "",
          error: backendMessage || err?.message || "",
        });
      } else {
        errorMessage = t("machines.transitionError");
      }
      
      showToast(errorMessage, "error");
      console.error("Error executing transition:", err);
    } finally {
      setUpdatingMachine(null);
    }
  };

  // Cancelar transición
  const handleCancelTransition = () => {
    setShowTransitionModal(false);
    setPendingTransition(null);
  };

  // Exportar a CSV
  const handleExportCSV = () => {
    if (!canExportCsv()) return;
    if (visibleMachines.length === 0) {
      showToast(t("machines.noDataToExport"), "error");
      return;
    }

    try {
      // Preparar los datos para CSV
      const headers = columns.map((key) => columnLabel(t, key));

      const rows = visibleMachines.map((machine) => columns.map((key) => formatCsvCell(t, machine, key)));

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

      // Crear y descargar el archivo
      const blob = new Blob([csvContent], { type: "text/csv;charset=utf-8;" });
      const link = document.createElement("a");
      const url = URL.createObjectURL(blob);
      link.href = url;
      link.download = `machines_${new Date().toISOString().split("T")[0]}.csv`;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      URL.revokeObjectURL(url);

      showToast(t("machines.exportSuccess"), "success");
    } catch (err: any) {
      const data = err?.response?.data;
      const backendMessage =
        (typeof data === "string" ? data : undefined) ??
        data?.message ??
        data?.detail ??
        data?.error;
      const errorMessage = backendMessage || err?.message || t("machines.exportError");
      showToast(errorMessage, "error");
      console.error("Error exporting CSV:", err);
    }
  };

  // Título del card con botón de exportación
  const renderCell = (machine: Machine, key: string): ReactNode => {
    if (key === "name") return <strong>{machine.name}</strong>;
    if (key === "state") {
      return (
        <select
          className="form-select form-select-sm"
          value={machine.state}
          onChange={(e) => handleStateChange(machine, e.target.value)}
          disabled={updatingMachine === machine.name || !machine.actions || machine.actions.length === 0}
          style={{ minWidth: "120px", padding: "0.25rem 0.5rem", fontSize: "0.8rem" }}
        >
          <option value={machine.state}>{machine.state}</option>
          {machine.actions && machine.actions.length > 0
            ? machine.actions
                .filter((action) => action !== machine.state)
                .map((action) => (
                  <option key={action} value={action}>
                    {action}
                  </option>
                ))
            : null}
        </select>
      );
    }
    if (key === "criticity") return <CriticityBadge value={machine.criticity} />;
    if (key === "leak_likelihood") return <LeakLikelihoodBar machine={machine} />;
    if (key === "classification") {
      return machine.classification ? translateMachineClassification(t, machine.classification) : "-";
    }
    const value = machine[key];
    if (value == null || value === "") return "-";
    if (typeof value === "object" && value && "value" in value) {
      const raw = (value as { value?: unknown; unit?: unknown }).value;
      const unit = (value as { unit?: unknown }).unit;
      if (raw == null || raw === "") return "-";
      return unit ? `${raw} ${unit}` : String(raw);
    }
    return String(value);
  };

  const cardTitle = (
    <div className="d-flex justify-content-between align-items-center w-100 gap-2">
      <h3 className="card-title m-0">{t("navigation.machines")}</h3>
      <div className="d-flex align-items-center gap-2 flex-shrink-0">
        {canConfigureColumns && (
          <div style={{ width: "16rem", maxWidth: "40vw" }}>
            <MultiSelectSearch
              options={columnOptions}
              selected={columns}
              onChange={persistColumns}
              placeholder={t("machines.columns")}
              searchPlaceholder={t("machines.columnsSearch")}
              emptyText={t("machines.columnsEmpty")}
              selectedCountLabel={selectedCountLabel}
              selectedGroupLabel={t("machines.columnsSelected")}
              otherGroupLabel={t("machines.columnsOther")}
            />
          </div>
        )}
      {canExportCsv() && (
        <Button
          variant="success"
          onClick={handleExportCSV}
          className="btn-sm"
          disabled={loading || visibleMachines.length === 0}
          title={t("machines.exportToCSV")}
        >
          <i className="bi bi-download me-1"></i>
          CSV
        </Button>
      )}
      </div>
    </div>
  );

  return (
    <div className="row g-0 page-fit-viewport">
      <div className="col-12 h-100">
        <Card
          className="page-fit-card"
          title={cardTitle}
          footer={
            <div className="d-flex justify-content-between align-items-center">
              <div>
                <span className="text-muted">
                  {t("pagination.showing", {
                    start: visibleMachines.length === 0 ? 0 : (currentPage - 1) * ITEMS_PER_PAGE + 1,
                    end: Math.min(currentPage * ITEMS_PER_PAGE, visibleMachines.length),
                    total: visibleMachines.length,
                    item: t("pagination.items.machines"),
                  })}
                </span>
              </div>
              <nav>
                <ul className="pagination mb-0">
                  <li className={`page-item ${currentPage === 1 ? "disabled" : ""}`}>
                    <button
                      className="page-link"
                      onClick={() => setCurrentPage((prev) => Math.max(1, prev - 1))}
                      disabled={currentPage === 1}
                    >
                      {t("pagination.previous")}
                    </button>
                  </li>
                  {Array.from({ length: Math.max(1, totalPages) }, (_, i) => i + 1).map((page) => (
                    <li key={page} className={`page-item ${currentPage === page ? "active" : ""}`}>
                      <button className="page-link" onClick={() => setCurrentPage(page)}>
                        {page}
                      </button>
                    </li>
                  ))}
                  <li className={`page-item ${currentPage === Math.max(1, totalPages) ? "disabled" : ""}`}>
                    <button
                      className="page-link"
                      onClick={() => setCurrentPage((prev) => Math.min(Math.max(1, totalPages), prev + 1))}
                      disabled={currentPage === Math.max(1, totalPages)}
                    >
                      {t("pagination.next")}
                    </button>
                  </li>
                </ul>
              </nav>
            </div>
          }
        >
          {error && (
            <div className="alert alert-danger" role="alert">
              {error}
            </div>
          )}

          {loading ? (
            <div className="text-center py-5">
              <div className="spinner-border" role="status">
                <span className="visually-hidden">{t("common.loading")}</span>
              </div>
            </div>
          ) : visibleMachines.length === 0 ? (
            <div className="text-center py-5">
              <i className="bi bi-cpu" style={{ fontSize: "4rem", color: "#6c757d" }}></i>
              <h4 className="mt-3 text-muted">{t("navigation.machines")}</h4>
              <p className="text-muted">{t("machines.noMachinesAvailable")}</p>
            </div>
          ) : (
            <div className="table-responsive machines-summary-table-wrap">
                <table className="table table-striped table-hover" style={{ fontSize: "0.875rem" }}>
                  <thead>
                    <tr>
                      {columns.map((key) => (
                        <th key={key} style={{ padding: "0.5rem 0.75rem" }}>{columnLabel(t, key)}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {paginatedMachines.map((machine) => (
                      <tr key={machine.name} style={{ height: "auto" }}>
                        {columns.map((key) => (
                          <td key={key} style={{ padding: "0.5rem 0.75rem", verticalAlign: "middle" }}>
                            {renderCell(machine, key)}
                          </td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
            </div>
          )}
        </Card>
      </div>

      {/* Modal de confirmación de transición */}
      {showTransitionModal && pendingTransition && (
        <div
          className="modal fade show"
          style={{ display: "block", backgroundColor: "rgba(0,0,0,0.5)" }}
          tabIndex={-1}
          role="dialog"
          aria-modal="true"
          onClick={(e) => {
            if (e.target === e.currentTarget && !updatingMachine) {
              handleCancelTransition();
            }
          }}
        >
          <div className="modal-dialog modal-dialog-centered" role="document">
            <div className="modal-content" onClick={(e) => e.stopPropagation()}>
              <div className="modal-header">
                <h5 className="modal-title">{t("machines.confirmStateTransition")}</h5>
                <button
                  type="button"
                  className="btn-close"
                  onClick={handleCancelTransition}
                  aria-label="Close"
                  disabled={!!updatingMachine}
                ></button>
              </div>
              <div className="modal-body">
                <p>
                  {t("machines.confirmStateTransitionMessage")}
                </p>
                <div className="mb-2">
                  <strong>{t("machines.machine")}:</strong> {pendingTransition.machineName}
                </div>
                <div className="mb-2">
                  <strong>{t("machines.currentState")}:</strong>{" "}
                  <span className="badge bg-secondary">{pendingTransition.oldState}</span>
                </div>
                <div>
                  <strong>{t("machines.newState")}:</strong>{" "}
                  <span className="badge bg-primary">{pendingTransition.newState}</span>
                </div>
              </div>
              <div className="modal-footer">
                <Button
                  variant="secondary"
                  onClick={handleCancelTransition}
                  disabled={!!updatingMachine}
                >
                  {t("common.cancel")}
                </Button>
                <Button
                  variant="primary"
                  onClick={handleConfirmTransition}
                  disabled={!!updatingMachine}
                >
                  {updatingMachine ? (
                    <>
                      <span className="spinner-border spinner-border-sm me-2" role="status" aria-hidden="true"></span>
                      {t("machines.executing")}
                    </>
                  ) : (
                    t("common.confirm")
                  )}
                </Button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
