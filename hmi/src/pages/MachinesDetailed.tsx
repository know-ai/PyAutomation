import { useEffect, useState, useRef, useMemo } from "react";
import { Card } from "../components/Card";
import { Button } from "../components/Button";
import { useTranslation } from "../hooks/useTranslation";
import {
  getMachines,
  getMachineByName,
  subscribeMachineTag,
  unsubscribeMachineTag,
  type Machine,
} from "../services/machines";
import { showToast } from "../utils/toast";
import { socketService } from "../services/socket";

const ITEMS_PER_PAGE = 10;

type MachineDetailedData = {
  process_variables: Record<string, any>;
  subscribed_tags: Record<string, any>;
  not_subscribed_tags: Record<string, any>;
  internal_process_variables: Record<string, any>;
  read_only_process_type_variables: Record<string, any>;
  serialization: any;
  field_tags?: string[];
  [key: string]: any;
};

export function MachinesDetailed() {
  const { t } = useTranslation();
  const [machines, setMachines] = useState<Machine[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<string | null>(null);
  const [machineDetails, setMachineDetails] = useState<Record<string, MachineDetailedData>>({});
  const [loadingDetails, setLoadingDetails] = useState<Record<string, boolean>>({});
  const [currentPage, setCurrentPage] = useState<Record<string, number>>({});
  
  // Estados para los dropdowns del card de Tags Subscriptions (por máquina)
  const [selectedSubscribedTag, setSelectedSubscribedTag] = useState<Record<string, string>>({});
  const [selectedReadOnlyVariable, setSelectedReadOnlyVariable] = useState<Record<string, string>>({});
  const [selectedInternalVariable, setSelectedInternalVariable] = useState<Record<string, string>>({});

  // Buffer para actualizaciones de propiedades de máquinas (patrón de 1 segundo)
  const pendingPropertyUpdatesRef = useRef<Map<string, Record<string, any>>>(new Map());
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // Cargar máquinas al montar el componente
  useEffect(() => {
    const loadMachines = async () => {
      setLoading(true);
      setError(null);
      try {
        const data = await getMachines();
        setMachines(data);
        // Establecer el primer tab como activo si hay máquinas
        if (data.length > 0 && data[0].name) {
          setActiveTab(data[0].name);
        }
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
        showToast(errorMessage, "error");
        console.error("Error loading machines:", err);
      } finally {
        setLoading(false);
      }
    };

    loadMachines();
  }, [t]);

  // Cargar detalles de la máquina cuando cambia el tab activo
  useEffect(() => {
    if (!activeTab) return;

    const loadMachineDetails = async () => {
      // Si ya tenemos los detalles, no recargar (evita loops infinitos)
      if (machineDetails[activeTab]) return;

      setLoadingDetails((prev) => ({ ...prev, [activeTab]: true }));
      try {
        const data = await getMachineByName(activeTab);
        setMachineDetails((prev) => ({ ...prev, [activeTab]: data }));
        // Inicializar página a 1 si no existe para esta máquina
        setCurrentPage((prev) => {
          if (!prev[activeTab]) {
            return { ...prev, [activeTab]: 1 };
          }
          return prev;
        });
      } catch (err: any) {
        const data = err?.response?.data;
        const backendMessage =
          (typeof data === "string" ? data : undefined) ??
          data?.message ??
          data?.detail ??
          data?.error;
        const errorMessage =
          backendMessage || err?.message || t("machines.loadError");
        showToast(errorMessage, "error");
        console.error("Error loading machine details:", err);
      } finally {
        setLoadingDetails((prev) => ({ ...prev, [activeTab]: false }));
      }
    };

    loadMachineDetails();
  }, [activeTab, t]); // Removido machineDetails de las dependencias para evitar loop infinito

  // Resetear dropdowns y página cuando cambia el tab
  useEffect(() => {
    if (activeTab) {
      setSelectedSubscribedTag((prev) => ({ ...prev, [activeTab]: "" }));
      setSelectedReadOnlyVariable((prev) => ({ ...prev, [activeTab]: "" }));
      setSelectedInternalVariable((prev) => ({ ...prev, [activeTab]: "" }));
      // Resetear página a 1 cuando cambia el tab
      setCurrentPage((prev) => ({ ...prev, [activeTab]: 1 }));
    }
  }, [activeTab]);

  // Suscripción a eventos de propiedades de máquinas con buffering
  useEffect(() => {
    // Función para aplicar las actualizaciones pendientes
    const flushUpdates = () => {
      if (pendingPropertyUpdatesRef.current.size === 0) {
        return;
      }

      console.log("Flushing property updates:", Array.from(pendingPropertyUpdatesRef.current.entries()));

      // Aplicar todas las actualizaciones acumuladas
      setMachineDetails((prev) => {
        const updated = { ...prev };
        let hasUpdates = false;

        // Iterar sobre todas las actualizaciones pendientes
        pendingPropertyUpdatesRef.current.forEach((propertyUpdates, machineName) => {
          // Solo actualizar si tenemos datos de esta máquina
          if (updated[machineName]) {
            hasUpdates = true;
            // Crear una copia profunda de los detalles actuales
            const currentDetails = { ...updated[machineName] };
            
            // Aplicar cada actualización de propiedad
            Object.entries(propertyUpdates).forEach(([propertyName, propertyValue]) => {
              console.log(`Updating property ${propertyName} with value:`, propertyValue);
              
              // 1. Actualizar en process_variables si existe (para variables de proceso como leak, leak_likelihood, etc.)
              // Actualizar tag.value dentro de process_variables ya que ese es el valor que se muestra
              if (currentDetails.process_variables && typeof currentDetails.process_variables === "object") {
                if (propertyName in currentDetails.process_variables) {
                  // Actualizar el valor dentro de la estructura de process_variables
                  const processVar = currentDetails.process_variables[propertyName];
                  if (typeof processVar === "object" && processVar !== null) {
                    // Actualizar tanto value directo como tag.value (prioridad a tag.value para mostrar)
                    const updatedProcessVar = { ...processVar };
                    
                    // Actualizar value directo
                    updatedProcessVar.value = propertyValue;
                    
                    // Actualizar tag.value si existe el tag
                    if (updatedProcessVar.tag && typeof updatedProcessVar.tag === "object") {
                      updatedProcessVar.tag = {
                        ...updatedProcessVar.tag,
                        value: propertyValue,
                      };
                    }
                    
                    currentDetails.process_variables = {
                      ...currentDetails.process_variables,
                      [propertyName]: updatedProcessVar,
                    };
                    console.log(`Updated process_variables[${propertyName}].value and tag.value to:`, propertyValue);
                  }
                }
              }

              // 2. Actualizar en serialization si existe
              // Si la propiedad en serialization es un objeto con value/unit, actualizar solo el value
              if (currentDetails.serialization && typeof currentDetails.serialization === "object") {
                const serializationProp = currentDetails.serialization[propertyName];
                if (serializationProp && typeof serializationProp === "object" && "value" in serializationProp) {
                  // Es un objeto con estructura {value, unit, ...}, actualizar solo el value
                  currentDetails.serialization = {
                    ...currentDetails.serialization,
                    [propertyName]: {
                      ...serializationProp,
                      value: propertyValue,
                    },
                  };
                  console.log(`Updated serialization[${propertyName}].value to:`, propertyValue);
                } else {
                  // Es un valor simple, actualizar directamente
                  currentDetails.serialization = {
                    ...currentDetails.serialization,
                    [propertyName]: propertyValue,
                  };
                  console.log(`Updated serialization[${propertyName}] to:`, propertyValue);
                }
              }
              
              // 3. Actualizar en el nivel raíz si existe
              if (propertyName in currentDetails) {
                currentDetails[propertyName] = propertyValue;
                console.log(`Updated root level[${propertyName}] to:`, propertyValue);
              }
            });

            updated[machineName] = currentDetails;
          }
        });

        // Limpiar el buffer después de aplicar
        pendingPropertyUpdatesRef.current.clear();

        return hasUpdates ? updated : prev;
      });
    };

    // Iniciar intervalo para hacer flush cada 1 segundo
    intervalRef.current = setInterval(() => {
      flushUpdates();
    }, 1000);

    // Suscribirse a actualizaciones de propiedades de máquinas
    const cleanup = socketService.onMachinePropertyUpdate((data) => {
      // data tiene el formato: { machineName: { propertyName: propertyValue } }
      // Por ejemplo: { "LDS": { "leak": 0.5 } } o { "NPW": { "state": "running" } }
      console.log("On machine property update received:", data);
      
      Object.entries(data).forEach(([machineName, propertyUpdates]) => {
        console.log(`Processing updates for machine ${machineName}:`, propertyUpdates);
        // Usar una función de actualización para acceder al estado actual sin depender de él
        setMachineDetails((prev) => {
          // Solo procesar si esta máquina está en nuestros detalles cargados
          if (prev[machineName]) {
            // Obtener o crear el buffer para esta máquina
            const existingUpdates = pendingPropertyUpdatesRef.current.get(machineName) || {};
            
            // Fusionar las nuevas actualizaciones con las existentes
            const mergedUpdates = {
              ...existingUpdates,
              ...propertyUpdates,
            };
            
            // Guardar en el buffer (sobrescribe si ya existe)
            pendingPropertyUpdatesRef.current.set(machineName, mergedUpdates);
          }
          // No cambiar el estado aquí, solo actualizar el buffer
          return prev;
        });
      });
    });

    // Cleanup al desmontar
    return () => {
      cleanup();
      if (intervalRef.current) {
        clearInterval(intervalRef.current);
        intervalRef.current = null;
      }
      // Aplicar cualquier actualización pendiente antes de limpiar
      flushUpdates();
      pendingPropertyUpdatesRef.current.clear();
    };
  }, []); // Sin dependencias - se suscribe una sola vez

  // Obtener los nombres únicos de las máquinas
  const machineNames = machines
    .map((machine) => machine.name)
    .filter((name): name is string => !!name);

  // Función para obtener atributos a mostrar en la tabla (excluyendo los especificados)
  const getTableAttributes = (data: MachineDetailedData | undefined) => {
    if (!data) return [];
    
    const excludedKeys = [
      "subscribed_tags",
      "not_subscribed_tags",
      "internal_process_variables",
      "read_only_process_type_variables",
      "field_tags",
      "name"
    ];

    const attributes: Array<[string, any]> = [];
    const processedKeys = new Set<string>(); // Para evitar duplicados entre process_variables y serialization
    
    // Primero procesar process_variables (tienen prioridad)
    // Para process_variables, usar tag.value y tag.unit si existen, sino usar value y unit directamente
    if (data.process_variables && typeof data.process_variables === "object" && Object.keys(data.process_variables).length > 0) {
      Object.entries(data.process_variables).forEach(([varKey, varValue]) => {
        if (typeof varValue === "object" && varValue !== null) {
          let displayValue: string;
          let displayUnit: string = "";
          
          // Prioridad: usar tag.value y tag.unit si existen (son los valores actualizados)
          if (varValue.tag && typeof varValue.tag === "object" && varValue.tag !== null) {
            displayValue = varValue.tag.value ?? varValue.value ?? "-";
            displayUnit = varValue.tag.unit ?? varValue.unit ?? "";
          } else if ("value" in varValue && "unit" in varValue) {
            // Fallback a value y unit directos si no hay tag
            displayValue = varValue.value ?? "-";
            displayUnit = varValue.unit ?? "";
          } else {
            // Si no tiene estructura esperada, mostrar el valor tal cual
            displayValue = String(varValue);
            displayUnit = "";
          }
          
          const formattedValue = `${displayValue} ${displayUnit}`.trim();
          attributes.push([varKey, formattedValue]);
          processedKeys.add(varKey); // Marcar como procesado
        } else {
          attributes.push([varKey, varValue]);
          processedKeys.add(varKey);
        }
      });
    }
    
    // Luego procesar serialization, omitiendo las claves ya procesadas en process_variables
    if (data.serialization && typeof data.serialization === "object" && data.serialization !== null) {
      Object.entries(data.serialization).forEach(([subKey, subValue]) => {
        // Omitir si ya fue procesado en process_variables, o si es "actions" o "name"
        if (subKey !== "actions" && subKey !== "name" && !processedKeys.has(subKey)) {
          // Formatear si es un objeto con value y unit
          if (typeof subValue === "object" && subValue !== null && "value" in subValue && "unit" in subValue) {
            const formattedValue = `${subValue.value ?? "-"} ${subValue.unit ?? ""}`.trim();
            attributes.push([subKey, formattedValue]);
          } else {
            attributes.push([subKey, subValue]);
          }
          processedKeys.add(subKey);
        }
      });
    }
    
    // Finalmente, agregar otros atributos del nivel raíz (que no estén excluidos ni ya procesados)
    Object.entries(data).forEach(([key, value]) => {
      if (!excludedKeys.includes(key) && !processedKeys.has(key) && key !== "process_variables" && key !== "serialization") {
        attributes.push([key, value]);
      }
    });

    return attributes;
  };

  // Función para formatear el valor de un atributo
  const formatAttributeValue = (value: any): string => {
    if (value === null || value === undefined) return "-";
    if (typeof value === "object" && value !== null) {
      if (value.value !== undefined && value.unit !== undefined) {
        return `${value.value} ${value.unit}`;
      }
      return JSON.stringify(value);
    }
    return String(value);
  };

  // Función para obtener atributos paginados por máquina
  const getPaginatedAttributes = (machineName: string) => {
    const allAttributes = getTableAttributes(machineDetails[machineName]);
    const page = currentPage[machineName] || 1;
    const startIndex = (page - 1) * ITEMS_PER_PAGE;
    const endIndex = startIndex + ITEMS_PER_PAGE;
    return {
      paginated: allAttributes.slice(startIndex, endIndex),
      total: allAttributes.length,
      totalPages: Math.ceil(allAttributes.length / ITEMS_PER_PAGE),
      currentPage: page,
    };
  };

  return (
    <div className="row">
      <div className="col-12">
        {loading ? (
          <div className="text-center py-5">
            <div className="spinner-border text-primary" role="status">
              <span className="visually-hidden">{t("common.loading")}</span>
            </div>
          </div>
        ) : error ? (
          <div className="alert alert-danger" role="alert">
            {error}
          </div>
        ) : machineNames.length === 0 ? (
          <div className="text-center py-5">
            <p className="text-muted">{t("machines.noMachinesAvailable")}</p>
          </div>
        ) : (
          <>
            {/* Nav tabs */}
            <ul className="nav nav-tabs" role="tablist">
              {machineNames.map((machineName, index) => (
                <li className="nav-item" role="presentation" key={machineName}>
                  <button
                    className={`nav-link ${activeTab === machineName ? "active" : ""}`}
                    type="button"
                    role="tab"
                    aria-controls={`tab-${machineName}`}
                    aria-selected={activeTab === machineName}
                    onClick={() => setActiveTab(machineName)}
                  >
                    {machineName}
                  </button>
                </li>
              ))}
            </ul>

            {/* Tab content */}
            <div className="tab-content">
              {machineNames.map((machineName) => {
                const machine = machines.find((m) => m.name === machineName);
                return (
                  <div
                    key={machineName}
                    className={`tab-pane fade ${activeTab === machineName ? "show active" : ""}`}
                    id={`tab-${machineName}`}
                    role="tabpanel"
                    aria-labelledby={`tab-${machineName}`}
                  >
                    {loadingDetails[machineName] ? (
                      <div className="text-center py-5">
                        <div className="spinner-border text-primary" role="status">
                          <span className="visually-hidden">{t("common.loading")}</span>
                        </div>
                      </div>
                    ) : (
                      <div className="row">
                        {/* Primera columna - Tabla de atributos (6 grid) */}
                        <div className="col-md-6">
                          {machineDetails[machineName] ? (
                            <>
                              <div className="table-responsive">
                                <table className="table table-striped table-hover">
                                  <thead>
                                    <tr>
                                      <th>{t("machines.attribute")}</th>
                                      <th>{t("machines.value")}</th>
                                    </tr>
                                  </thead>
                                  <tbody>
                                    {(() => {
                                      const { paginated, total } = getPaginatedAttributes(machineName);
                                      if (total === 0) {
                                        return (
                                          <tr>
                                            <td colSpan={2} className="text-center text-muted">
                                              {t("machines.noAttributesAvailable")}
                                            </td>
                                          </tr>
                                        );
                                      }
                                      return paginated.map(([key, value]) => (
                                        <tr key={key}>
                                          <td><strong>{key}</strong></td>
                                          <td>{formatAttributeValue(value)}</td>
                                        </tr>
                                      ));
                                    })()}
                                  </tbody>
                                </table>
                              </div>
                              {(() => {
                                const { total, totalPages, currentPage: page } = getPaginatedAttributes(machineName);
                                if (totalPages > 1) {
                                  return (
                                    <div className="d-flex justify-content-between align-items-center mt-3">
                                      <div>
                                        <span className="text-muted">
                                          {t("pagination.showing", {
                                            start: (page - 1) * ITEMS_PER_PAGE + 1,
                                            end: Math.min(page * ITEMS_PER_PAGE, total),
                                            total: total,
                                            item: t("pagination.items.attributes"),
                                          })}
                                        </span>
                                      </div>
                                      <nav>
                                        <ul className="pagination mb-0">
                                          <li className={`page-item ${page === 1 ? "disabled" : ""}`}>
                                            <button
                                              className="page-link"
                                              onClick={() => setCurrentPage((prev) => ({ ...prev, [machineName]: Math.max(1, page - 1) }))}
                                              disabled={page === 1}
                                            >
                                              {t("pagination.previous")}
                                            </button>
                                          </li>
                                          {Array.from({ length: totalPages }, (_, i) => i + 1).map((p) => (
                                            <li key={p} className={`page-item ${page === p ? "active" : ""}`}>
                                              <button
                                                className="page-link"
                                                onClick={() => setCurrentPage((prev) => ({ ...prev, [machineName]: p }))}
                                              >
                                                {p}
                                              </button>
                                            </li>
                                          ))}
                                          <li className={`page-item ${page === totalPages ? "disabled" : ""}`}>
                                            <button
                                              className="page-link"
                                              onClick={() => setCurrentPage((prev) => ({ ...prev, [machineName]: Math.min(totalPages, page + 1) }))}
                                              disabled={page === totalPages}
                                            >
                                              {t("pagination.next")}
                                            </button>
                                          </li>
                                        </ul>
                                      </nav>
                                    </div>
                                  );
                                }
                                return null;
                              })()}
                            </>
                          ) : (
                            <p className="text-muted">{t("machines.loadingDetails")}</p>
                          )}
                        </div>

                        {/* Segunda columna - Tags Subscriptions (6 grid) */}
                        <div className="col-md-6">
                          <Card title={t("machines.tagsSubscriptions")}>
                            {machineDetails[machineName] ? (
                              <div>
                                {/* Primera fila - Dropdown subscribed_tags */}
                                <div className="mb-3">
                                  <label className="form-label">{t("machines.subscribedTags")}</label>
                                  <select
                                    className="form-select"
                                    value={selectedSubscribedTag[machineName] || ""}
                                    onChange={(e) => setSelectedSubscribedTag((prev) => ({ ...prev, [machineName]: e.target.value }))}
                                  >
                                    <option value="">{t("machines.selectSubscribedTag")}</option>
                                    {Object.keys(machineDetails[machineName].subscribed_tags || {}).map((key) => (
                                      <option key={key} value={key}>
                                        {key}
                                      </option>
                                    ))}
                                  </select>
                                </div>

                                {/* Segunda fila - Dos columnas con dropdowns */}
                                <div className="row mb-3">
                                  <div className="col-6">
                                    <label className="form-label">{t("machines.fieldTags")}</label>
                                    <select
                                      className="form-select"
                                      value={selectedReadOnlyVariable[machineName] || ""}
                                      onChange={(e) => setSelectedReadOnlyVariable((prev) => ({ ...prev, [machineName]: e.target.value }))}
                                    >
                                      <option value="">{t("machines.select")}</option>
                                      {(machineDetails[machineName].field_tags || []).map((tagName) => (
                                        <option key={tagName} value={tagName}>
                                          {tagName}
                                        </option>
                                      ))}
                                    </select>
                                  </div>
                                  <div className="col-6">
                                    <label className="form-label">{t("machines.notSubscribedTags")}</label>
                                    <select
                                      className="form-select"
                                      value={selectedInternalVariable[machineName] || ""}
                                      onChange={(e) => setSelectedInternalVariable((prev) => ({ ...prev, [machineName]: e.target.value }))}
                                    >
                                      <option value="">{t("machines.select")}</option>
                                      {Object.keys(machineDetails[machineName].not_subscribed_tags || {}).map((key) => (
                                        <option key={key} value={key}>
                                          {key}
                                        </option>
                                      ))}
                                    </select>
                                  </div>
                                </div>

                                {/* Tercera fila - Botones */}
                                <div className="row">
                                  <div className="col-6">
                                    <Button
                                      className="w-100"
                                      disabled={
                                        !selectedReadOnlyVariable[machineName] ||
                                        !selectedInternalVariable[machineName] ||
                                        selectedReadOnlyVariable[machineName] === "" ||
                                        selectedInternalVariable[machineName] === ""
                                      }
                                      onClick={async () => {
                                        const fieldTag = selectedReadOnlyVariable[machineName];
                                        const internalTag = selectedInternalVariable[machineName];

                                        if (!fieldTag || !internalTag) {
                                          return;
                                        }

                                        try {
                                          const { message } = await subscribeMachineTag(
                                            machineName,
                                            fieldTag,
                                            internalTag
                                          );
                                          showToast(
                                            message || t("machines.subscribe"),
                                            "success"
                                          );
                                          // Refrescar detalles de la máquina
                                          const data = await getMachineByName(machineName);
                                          setMachineDetails((prev) => ({
                                            ...prev,
                                            [machineName]: data,
                                          }));
                                          // Resetear selecciones
                                          setSelectedReadOnlyVariable((prev) => ({
                                            ...prev,
                                            [machineName]: "",
                                          }));
                                          setSelectedInternalVariable((prev) => ({
                                            ...prev,
                                            [machineName]: "",
                                          }));
                                        } catch (err: any) {
                                          const data = err?.response?.data;
                                          const backendMessage =
                                            (typeof data === "string"
                                              ? data
                                              : undefined) ??
                                            data?.message ??
                                            data?.detail ??
                                            data?.error;
                                          const errorMessage =
                                            backendMessage ||
                                            err?.message ||
                                            t("machines.loadError");
                                          showToast(errorMessage, "error");
                                          console.error(
                                            "Error subscribing tag to machine:",
                                            err
                                          );
                                        }
                                      }}
                                    >
                                      {t("machines.subscribe")}
                                    </Button>
                                  </div>
                                  <div className="col-6">
                                    <Button
                                      className="w-100"
                                      variant="secondary"
                                      disabled={
                                        !selectedSubscribedTag[machineName] ||
                                        selectedSubscribedTag[machineName] === ""
                                      }
                                      onClick={async () => {
                                        const tagName = selectedSubscribedTag[machineName];
                                        if (!tagName) {
                                          return;
                                        }

                                        try {
                                          const { message } =
                                            await unsubscribeMachineTag(
                                              machineName,
                                              tagName
                                            );
                                          showToast(
                                            message || t("machines.unsubscribe"),
                                            "success"
                                          );
                                          // Refrescar detalles de la máquina
                                          const data = await getMachineByName(
                                            machineName
                                          );
                                          setMachineDetails((prev) => ({
                                            ...prev,
                                            [machineName]: data,
                                          }));
                                          // Resetear selección
                                          setSelectedSubscribedTag((prev) => ({
                                            ...prev,
                                            [machineName]: "",
                                          }));
                                        } catch (err: any) {
                                          const data = err?.response?.data;
                                          const backendMessage =
                                            (typeof data === "string"
                                              ? data
                                              : undefined) ??
                                            data?.message ??
                                            data?.detail ??
                                            data?.error;
                                          const errorMessage =
                                            backendMessage ||
                                            err?.message ||
                                            t("machines.loadError");
                                          showToast(errorMessage, "error");
                                          console.error(
                                            "Error unsubscribing tag from machine:",
                                            err
                                          );
                                        }
                                      }}
                                    >
                                      {t("machines.unsubscribe")}
                                    </Button>
                                  </div>
                                </div>
                              </div>
                            ) : (
                              <p className="text-muted">{t("machines.loadingDetails")}</p>
                            )}
                          </Card>
                        </div>
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          </>
        )}
      </div>
    </div>
  );
}

