import { useEffect, useState, useMemo } from "react";
import { Card } from "../components/Card";
import { Button } from "../components/Button";
import { getMachines, updateMachineInterval, transitionMachine, type Machine } from "../services/machines";
import { useTranslation } from "../hooks/useTranslation";
import { showToast } from "../utils/toast";
import { useAppSelector } from "../hooks/useAppSelector";
import { useAppDispatch } from "../hooks/useAppDispatch";
import { loadAllMachines } from "../store/slices/machinesSlice";

const ITEMS_PER_PAGE = 10;

export function Machines() {
  const { t } = useTranslation();
  const dispatch = useAppDispatch();
  const realTimeMachines = useAppSelector((state) => state.machines.machines);
  const [machines, setMachines] = useState<Machine[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [currentPage, setCurrentPage] = useState(1);
  const [updatingMachine, setUpdatingMachine] = useState<string | null>(null);
  
  // Estado para el modal de confirmación de intervalo
  const [showIntervalModal, setShowIntervalModal] = useState(false);
  const [pendingIntervalUpdate, setPendingIntervalUpdate] = useState<{
    machineName: string;
    oldInterval: number;
    newInterval: number;
  } | null>(null);
  
  // Estado para el modal de confirmación de transición
  const [showTransitionModal, setShowTransitionModal] = useState(false);
  const [pendingTransition, setPendingTransition] = useState<{
    machineName: string;
    oldState: string;
    newState: string;
  } | null>(null);

  // Cargar máquinas
  const loadMachines = async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await getMachines();
      setMachines(data);
      // Cargar máquinas iniciales en el store para sincronizar con tiempo real
      dispatch(loadAllMachines(data));
    } catch (err: any) {
      const errorMessage = err?.response?.data?.message || err?.message || "Error al cargar las máquinas de estado";
      setError(errorMessage);
      console.error("Error loading machines:", err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadMachines();
  }, [dispatch]);

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

  // Paginación
  const totalPages = Math.ceil(machinesWithRealTime.length / ITEMS_PER_PAGE);
  const paginatedMachines = useMemo(() => {
    const startIndex = (currentPage - 1) * ITEMS_PER_PAGE;
    const endIndex = startIndex + ITEMS_PER_PAGE;
    return machinesWithRealTime.slice(startIndex, endIndex);
  }, [machinesWithRealTime, currentPage]);

  // Manejar cambio de intervalo
  const handleIntervalChange = (machine: Machine, newInterval: number) => {
    const intervalValue = parseFloat(String(newInterval));
    
    if (isNaN(intervalValue) || intervalValue < 0.1) {
      showToast("error", "El intervalo debe ser un número mayor o igual a 0.1 segundos");
      return;
    }

    if (intervalValue === machine.machine_interval) {
      return; // No hay cambio
    }

    // Mostrar modal de confirmación
    setPendingIntervalUpdate({
      machineName: machine.name,
      oldInterval: machine.machine_interval,
      newInterval: intervalValue,
    });
    setShowIntervalModal(true);
  };

  // Confirmar actualización de intervalo
  const handleConfirmIntervalUpdate = async () => {
    if (!pendingIntervalUpdate) return;

    setUpdatingMachine(pendingIntervalUpdate.machineName);
    try {
      const response = await updateMachineInterval(
        pendingIntervalUpdate.machineName,
        pendingIntervalUpdate.newInterval
      );

      // Actualizar la máquina en el estado local
      setMachines((prev) =>
        prev.map((m) =>
          m.name === pendingIntervalUpdate.machineName
            ? { ...m, machine_interval: pendingIntervalUpdate.newInterval }
            : m
        )
      );
      // Recargar máquinas para sincronizar con el store
      loadMachines();

      showToast("success", response.message || "Intervalo actualizado correctamente");
      setShowIntervalModal(false);
      setPendingIntervalUpdate(null);
    } catch (err: any) {
      const errorMessage = err?.response?.data?.message || err?.message || "Error al actualizar el intervalo";
      showToast("error", errorMessage);
      console.error("Error updating interval:", err);
    } finally {
      setUpdatingMachine(null);
    }
  };

  // Cancelar actualización de intervalo
  const handleCancelIntervalUpdate = () => {
    setShowIntervalModal(false);
    setPendingIntervalUpdate(null);
  };

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

    setUpdatingMachine(pendingTransition.machineName);
    try {
      const response = await transitionMachine(
        pendingTransition.machineName,
        pendingTransition.newState
      );

      // Actualizar la máquina en el estado local
      setMachines((prev) =>
        prev.map((m) =>
          m.name === pendingTransition.machineName
            ? { ...m, state: pendingTransition.newState, ...response.data }
            : m
        )
      );
      // Recargar máquinas para sincronizar con el store
      loadMachines();

      showToast("success", response.message || "Transición ejecutada correctamente");
      setShowTransitionModal(false);
      setPendingTransition(null);
    } catch (err: any) {
      const errorMessage = err?.response?.data?.message || err?.message || "Error al ejecutar la transición";
      showToast("error", errorMessage);
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
    if (!machines || machines.length === 0) {
      showToast("error", "No hay datos para exportar");
      return;
    }

    try {
      // Preparar los datos para CSV
      const headers = [
        "Nombre",
        "Intervalo (s)",
        "Estado",
        "Prioridad",
        "Criticidad",
        "Descripción",
        "Clasificación",
      ];

      // Convertir máquinas a filas CSV (usar máquinas con tiempo real)
      const rows = machinesWithRealTime.map((machine) => {
        return [
          machine.name || "",
          machine.machine_interval || "",
          machine.state || "",
          machine.priority !== undefined ? String(machine.priority) : "",
          machine.criticity !== undefined ? String(machine.criticity) : "",
          machine.description || "",
          machine.classification || "",
        ];
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

      showToast("success", "Datos exportados correctamente");
    } catch (err: any) {
      const errorMessage = err?.message || "Error al exportar los datos";
      showToast("error", errorMessage);
      console.error("Error exporting CSV:", err);
    }
  };

  // Título del card con botón de exportación
  const cardTitle = (
    <div className="d-flex justify-content-between align-items-center w-100">
      <h3 className="card-title m-0">{t("navigation.machines")}</h3>
      <Button
        variant="success"
        onClick={handleExportCSV}
        className="btn-sm"
        disabled={loading || machinesWithRealTime.length === 0}
        title="Exportar a CSV"
      >
        <i className="bi bi-download me-1"></i>
        CSV
      </Button>
    </div>
  );

  return (
    <div className="row">
      <div className="col-12">
        <Card title={cardTitle}>
          {error && (
            <div className="alert alert-danger" role="alert">
              {error}
            </div>
          )}

          {loading ? (
            <div className="text-center py-5">
              <div className="spinner-border" role="status">
                <span className="visually-hidden">Cargando...</span>
              </div>
            </div>
          ) : machinesWithRealTime.length === 0 ? (
            <div className="text-center py-5">
              <i className="bi bi-cpu" style={{ fontSize: "4rem", color: "#6c757d" }}></i>
              <h4 className="mt-3 text-muted">{t("navigation.machines")}</h4>
              <p className="text-muted">No hay máquinas disponibles</p>
            </div>
          ) : (
            <>
              <div className="table-responsive">
                <table className="table table-striped table-hover" style={{ fontSize: "0.875rem" }}>
                  <thead>
                    <tr>
                      <th style={{ padding: "0.5rem 0.75rem" }}>{t("tables.name")}</th>
                      <th style={{ padding: "0.5rem 0.75rem" }}>Intervalo (s)</th>
                      <th style={{ padding: "0.5rem 0.75rem" }}>{t("tables.state")}</th>
                      <th style={{ padding: "0.5rem 0.75rem" }}>{t("tables.priority")}</th>
                      <th style={{ padding: "0.5rem 0.75rem" }}>{t("tables.criticity")}</th>
                      <th style={{ padding: "0.5rem 0.75rem" }}>{t("tables.description")}</th>
                      <th style={{ padding: "0.5rem 0.75rem" }}>Clasificación</th>
                      <th style={{ padding: "0.5rem 0.75rem" }}>{t("tables.actions")}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {paginatedMachines.map((machine) => (
                      <tr key={machine.name} style={{ height: "auto" }}>
                        <td style={{ padding: "0.5rem 0.75rem", verticalAlign: "middle" }}>
                          <strong>{machine.name}</strong>
                        </td>
                        <td style={{ padding: "0.5rem 0.75rem", verticalAlign: "middle" }}>
                          <input
                            type="number"
                            className="form-control form-control-sm"
                            key={`interval-${machine.name}-${machine.machine_interval}`}
                            defaultValue={machine.machine_interval}
                            onBlur={(e) => {
                              const value = parseFloat(e.target.value);
                              if (!isNaN(value) && value >= 0.1 && value !== machine.machine_interval) {
                                handleIntervalChange(machine, value);
                              } else if (isNaN(value) || value < 0.1) {
                                e.target.value = String(machine.machine_interval);
                                showToast("error", "El intervalo debe ser un número mayor o igual a 0.1 segundos");
                              }
                            }}
                            onKeyDown={(e) => {
                              if (e.key === "Enter") {
                                e.currentTarget.blur();
                              }
                            }}
                            disabled={updatingMachine === machine.name}
                            min="0.1"
                            step="0.1"
                            style={{ width: "100px", padding: "0.25rem 0.5rem", fontSize: "0.8rem" }}
                          />
                        </td>
                        <td style={{ padding: "0.5rem 0.75rem", verticalAlign: "middle" }}>
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
                        </td>
                        <td style={{ padding: "0.5rem 0.75rem", verticalAlign: "middle" }}>
                          {machine.priority !== undefined ? machine.priority : "-"}
                        </td>
                        <td style={{ padding: "0.5rem 0.75rem", verticalAlign: "middle" }}>
                          {machine.criticity !== undefined ? machine.criticity : "-"}
                        </td>
                        <td style={{ padding: "0.5rem 0.75rem", verticalAlign: "middle" }}>
                          {machine.description || "-"}
                        </td>
                        <td style={{ padding: "0.5rem 0.75rem", verticalAlign: "middle" }}>
                          {machine.classification || "-"}
                        </td>
                        <td style={{ padding: "0.5rem 0.75rem", verticalAlign: "middle" }}>
                          <Button
                            variant="secondary"
                            className="btn-sm"
                            onClick={() => {
                              // Por ahora no hace nada, se implementará más adelante
                              showToast("info", "Funcionalidad de edición de configuración próximamente");
                            }}
                            title="Editar configuración"
                          >
                            <i className="bi bi-gear"></i>
                          </Button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              {/* Paginación */}
              {totalPages > 1 && (
                <div className="d-flex justify-content-between align-items-center mt-3">
                  <div>
                    <span className="text-muted">
                      Mostrando {(currentPage - 1) * ITEMS_PER_PAGE + 1} -{" "}
                      {Math.min(currentPage * ITEMS_PER_PAGE, machines.length)} de {machines.length} máquinas
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
                          Anterior
                        </button>
                      </li>
                      {Array.from({ length: totalPages }, (_, i) => i + 1).map((page) => (
                        <li key={page} className={`page-item ${currentPage === page ? "active" : ""}`}>
                          <button className="page-link" onClick={() => setCurrentPage(page)}>
                            {page}
                          </button>
                        </li>
                      ))}
                      <li className={`page-item ${currentPage === totalPages ? "disabled" : ""}`}>
                        <button
                          className="page-link"
                          onClick={() => setCurrentPage((prev) => Math.min(totalPages, prev + 1))}
                          disabled={currentPage === totalPages}
                        >
                          Siguiente
                        </button>
                      </li>
                    </ul>
                  </nav>
                </div>
              )}
            </>
          )}
        </Card>
      </div>

      {/* Modal de confirmación de intervalo */}
      {showIntervalModal && pendingIntervalUpdate && (
        <div
          className="modal fade show"
          style={{ display: "block", backgroundColor: "rgba(0,0,0,0.5)" }}
          tabIndex={-1}
          role="dialog"
          aria-modal="true"
          onClick={(e) => {
            if (e.target === e.currentTarget && !updatingMachine) {
              handleCancelIntervalUpdate();
            }
          }}
        >
          <div className="modal-dialog modal-dialog-centered" role="document">
            <div className="modal-content" onClick={(e) => e.stopPropagation()}>
              <div className="modal-header">
                <h5 className="modal-title">Confirmar cambio de intervalo</h5>
                <button
                  type="button"
                  className="btn-close"
                  onClick={handleCancelIntervalUpdate}
                  aria-label="Close"
                  disabled={!!updatingMachine}
                ></button>
              </div>
              <div className="modal-body">
                <p>
                  ¿Está seguro de que desea cambiar el intervalo de ejecución de la máquina?
                </p>
                <div className="mb-2">
                  <strong>Máquina:</strong> {pendingIntervalUpdate.machineName}
                </div>
                <div className="mb-2">
                  <strong>Intervalo actual:</strong> {pendingIntervalUpdate.oldInterval} segundos
                </div>
                <div>
                  <strong>Intervalo nuevo:</strong> {pendingIntervalUpdate.newInterval} segundos
                </div>
              </div>
              <div className="modal-footer">
                <Button
                  variant="secondary"
                  onClick={handleCancelIntervalUpdate}
                  disabled={!!updatingMachine}
                >
                  Cancelar
                </Button>
                <Button
                  variant="primary"
                  onClick={handleConfirmIntervalUpdate}
                  disabled={!!updatingMachine}
                >
                  {updatingMachine ? (
                    <>
                      <span className="spinner-border spinner-border-sm me-2" role="status" aria-hidden="true"></span>
                      Actualizando...
                    </>
                  ) : (
                    "Confirmar"
                  )}
                </Button>
              </div>
            </div>
          </div>
        </div>
      )}

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
                <h5 className="modal-title">Confirmar transición de estado</h5>
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
                  ¿Está seguro de que desea cambiar el estado de la máquina?
                </p>
                <div className="mb-2">
                  <strong>Máquina:</strong> {pendingTransition.machineName}
                </div>
                <div className="mb-2">
                  <strong>Estado actual:</strong>{" "}
                  <span className="badge bg-secondary">{pendingTransition.oldState}</span>
                </div>
                <div>
                  <strong>Estado nuevo:</strong>{" "}
                  <span className="badge bg-primary">{pendingTransition.newState}</span>
                </div>
              </div>
              <div className="modal-footer">
                <Button
                  variant="secondary"
                  onClick={handleCancelTransition}
                  disabled={!!updatingMachine}
                >
                  Cancelar
                </Button>
                <Button
                  variant="primary"
                  onClick={handleConfirmTransition}
                  disabled={!!updatingMachine}
                >
                  {updatingMachine ? (
                    <>
                      <span className="spinner-border spinner-border-sm me-2" role="status" aria-hidden="true"></span>
                      Ejecutando...
                    </>
                  ) : (
                    "Confirmar"
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
