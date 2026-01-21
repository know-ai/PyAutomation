import { useEffect, useState, useRef, useMemo } from "react";
import type { JSX, CSSProperties } from "react";
import { Card } from "../components/Card";
import { Button } from "../components/Button";
import { useTranslation } from "../hooks/useTranslation";
import {
  getMachines,
  getMachineByName,
  subscribeMachineTag,
  unsubscribeMachineTag,
  updateMachineAttributes,
  type Machine,
} from "../services/machines";
import { showToast } from "../utils/toast";
import { socketService } from "../services/socket";
import type { Tag } from "../services/tags";

const ITEMS_PER_PAGE = 10;
const ACTIVE_TAB_STORAGE_KEY = "machinesDetailed_activeTab";
const getPageStorageKey = (machineName: string) => `machinesDetailed_page_${machineName}`;

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
  
  // Estados para los inputs de atributos de máquina (por máquina)
  const [thresholdValue, setThresholdValue] = useState<Record<string, string>>({});
  const [bufferSizeValue, setBufferSizeValue] = useState<Record<string, string>>({});
  const [onDelayValue, setOnDelayValue] = useState<Record<string, string>>({});
  const [updatingAttribute, setUpdatingAttribute] = useState<Record<string, string | null>>({});
  // Valores originales para comparar si cambió
  const [originalThresholdValue, setOriginalThresholdValue] = useState<Record<string, number | null>>({});
  const [originalBufferSizeValue, setOriginalBufferSizeValue] = useState<Record<string, number | null>>({});
  const [originalOnDelayValue, setOriginalOnDelayValue] = useState<Record<string, number | null>>({});
  // Estado para el modal de confirmación
  const [showConfirmModal, setShowConfirmModal] = useState(false);
  const [pendingUpdate, setPendingUpdate] = useState<{
    machineName: string;
    attribute: "threshold" | "buffer_size" | "on_delay";
    newValue: number;
    oldValue: number | null;
    attributeLabel: string;
  } | null>(null);

  // Buffer para actualizaciones de propiedades de máquinas (patrón de 1 segundo)
  const pendingPropertyUpdatesRef = useRef<Map<string, Record<string, any>>>(new Map());
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
  
  // Buffer para actualizaciones completas de máquinas (patrón de 1 segundo)
  const pendingMachineUpdatesRef = useRef<Map<string, Machine>>(new Map());
  const machineUpdateIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
  
  // Buffer para actualizaciones de tags (patrón de 1 segundo)
  const pendingTagUpdatesRef = useRef<Map<string, any>>(new Map()); // Map<tagId, Tag>
  const tagUpdateIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // Cargar máquinas al montar el componente
  useEffect(() => {
    const loadMachines = async () => {
      setLoading(true);
      setError(null);
      try {
        const data = await getMachines();
        setMachines(data);
        
        // Intentar cargar el tab activo guardado en localStorage
        const savedActiveTab = localStorage.getItem(ACTIVE_TAB_STORAGE_KEY);
        
        // Verificar si el tab guardado existe en las máquinas disponibles
        let tabToActivate: string | null = null;
        if (savedActiveTab && data.some((m) => m.name === savedActiveTab)) {
          tabToActivate = savedActiveTab;
        } else if (data.length > 0 && data[0].name) {
          // Si no hay tab guardado válido, usar el primero
          tabToActivate = data[0].name;
        }
        
        if (tabToActivate) {
          setActiveTab(tabToActivate);
          // Cargar la página guardada para el tab activo
          const savedPage = localStorage.getItem(getPageStorageKey(tabToActivate));
          if (savedPage) {
            const page = parseInt(savedPage, 10);
            if (!isNaN(page) && page > 0) {
              setCurrentPage((prev) => ({ ...prev, [tabToActivate]: page }));
            }
          }
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

  // Guardar el tab activo en localStorage cuando cambie
  useEffect(() => {
    if (activeTab) {
      localStorage.setItem(ACTIVE_TAB_STORAGE_KEY, activeTab);
    }
  }, [activeTab]);

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
        // Cargar la página guardada o inicializar a 1 si no existe
        setCurrentPage((prev) => {
          if (!prev[activeTab]) {
            const savedPage = localStorage.getItem(getPageStorageKey(activeTab));
            const page = savedPage ? parseInt(savedPage, 10) : 1;
            return { ...prev, [activeTab]: page };
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

  // Resetear dropdowns cuando cambia el tab (pero mantener la página guardada)
  useEffect(() => {
    if (activeTab) {
      setSelectedSubscribedTag((prev) => ({ ...prev, [activeTab]: "" }));
      setSelectedReadOnlyVariable((prev) => ({ ...prev, [activeTab]: "" }));
      setSelectedInternalVariable((prev) => ({ ...prev, [activeTab]: "" }));
      // Cargar la página guardada para este tab, o inicializar a 1 si no existe
      setCurrentPage((prev) => {
        if (!prev[activeTab]) {
          const savedPage = localStorage.getItem(getPageStorageKey(activeTab));
          const page = savedPage ? parseInt(savedPage, 10) : 1;
          return { ...prev, [activeTab]: page };
        }
        return prev;
      });
      // Resetear valores de atributos cuando cambia el tab (se inicializarán cuando se carguen los detalles)
      setThresholdValue((prev) => ({ ...prev, [activeTab]: "" }));
      setBufferSizeValue((prev) => ({ ...prev, [activeTab]: "" }));
      setOnDelayValue((prev) => ({ ...prev, [activeTab]: "" }));
      setOriginalThresholdValue((prev) => ({ ...prev, [activeTab]: null }));
      setOriginalBufferSizeValue((prev) => ({ ...prev, [activeTab]: null }));
      setOriginalOnDelayValue((prev) => ({ ...prev, [activeTab]: null }));
    }
  }, [activeTab]);

  // Guardar la página actual en localStorage cuando cambie
  useEffect(() => {
    Object.entries(currentPage).forEach(([machineName, page]) => {
      if (machineName && page) {
        localStorage.setItem(getPageStorageKey(machineName), String(page));
      }
    });
  }, [currentPage]);

  // Función helper para mostrar modal de confirmación de threshold
  const handleUpdateThreshold = (machineName: string) => {
    const value = parseFloat(thresholdValue[machineName]);
    if (isNaN(value)) {
      showToast(t("machines.updateAttributeError"), "error");
      return;
    }

    // Solo mostrar modal si el valor cambió
    if (originalThresholdValue[machineName] !== null && value === originalThresholdValue[machineName]) {
      return;
    }

    setPendingUpdate({
      machineName,
      attribute: "threshold",
      newValue: value,
      oldValue: originalThresholdValue[machineName],
      attributeLabel: t("machines.threshold"),
    });
    setShowConfirmModal(true);
  };

  // Función para ejecutar la actualización de threshold después de confirmar
  const executeUpdateThreshold = async (machineName: string, value: number) => {
    setUpdatingAttribute((prev) => ({ ...prev, [machineName]: "threshold" }));
    try {
      const { message } = await updateMachineAttributes(machineName, {
        threshold: value,
      });
      showToast(message || t("machines.updateAttribute"), "success");
      // Refrescar detalles de la máquina
      const data = await getMachineByName(machineName);
      setMachineDetails((prev) => ({
        ...prev,
        [machineName]: data,
      }));
      // Actualizar el valor del input y el valor original
      const updatedThreshold = data.serialization?.threshold;
      const thresholdVal = typeof updatedThreshold === "object" && updatedThreshold !== null && "value" in updatedThreshold
        ? updatedThreshold.value
        : updatedThreshold;
      if (thresholdVal !== null && thresholdVal !== undefined) {
        const thresholdNum = typeof thresholdVal === "number" ? thresholdVal : parseFloat(String(thresholdVal));
        if (!isNaN(thresholdNum)) {
          setThresholdValue((prev) => ({ ...prev, [machineName]: String(thresholdNum) }));
          setOriginalThresholdValue((prev) => ({ ...prev, [machineName]: thresholdNum }));
        }
      }
    } catch (err: any) {
      const data = err?.response?.data;
      const backendMessage =
        (typeof data === "string" ? data : undefined) ??
        data?.message ??
        data?.detail ??
        data?.error;
      const errorMessage =
        backendMessage || err?.message || t("machines.updateAttributeError");
      showToast(errorMessage, "error");
      console.error("Error updating threshold:", err);
      // Restaurar valor original en caso de error
      if (originalThresholdValue[machineName] !== null) {
        setThresholdValue((prev) => ({ ...prev, [machineName]: String(originalThresholdValue[machineName]) }));
      }
    } finally {
      setUpdatingAttribute((prev) => ({ ...prev, [machineName]: null }));
    }
  };

  // Función helper para mostrar modal de confirmación de buffer_size
  const handleUpdateBufferSize = (machineName: string) => {
    // Para PFM/Observer el Buffer Size no debe ser editable
    const isBufferSizeLocked = ["pfm", "observer"].includes(String(machineName).toLowerCase());
    if (isBufferSizeLocked) return;

    const value = parseInt(bufferSizeValue[machineName], 10);
    if (isNaN(value)) {
      showToast(t("machines.updateAttributeError"), "error");
      return;
    }

    // Solo mostrar modal si el valor cambió
    if (originalBufferSizeValue[machineName] !== null && value === originalBufferSizeValue[machineName]) {
      return;
    }

    setPendingUpdate({
      machineName,
      attribute: "buffer_size",
      newValue: value,
      oldValue: originalBufferSizeValue[machineName],
      attributeLabel: t("machines.bufferSize"),
    });
    setShowConfirmModal(true);
  };

  // Función para ejecutar la actualización de buffer_size después de confirmar
  const executeUpdateBufferSize = async (machineName: string, value: number) => {
    setUpdatingAttribute((prev) => ({ ...prev, [machineName]: "buffer_size" }));
    try {
      const { message } = await updateMachineAttributes(machineName, {
        buffer_size: value,
      });
      showToast(message || t("machines.updateAttribute"), "success");
      // Refrescar detalles de la máquina
      const data = await getMachineByName(machineName);
      setMachineDetails((prev) => ({
        ...prev,
        [machineName]: data,
      }));
      // Actualizar el valor del input y el valor original
      if (data.serialization?.buffer_size !== null && data.serialization?.buffer_size !== undefined) {
        const bufferSizeNum = typeof data.serialization.buffer_size === "number" 
          ? data.serialization.buffer_size 
          : parseInt(String(data.serialization.buffer_size), 10);
        if (!isNaN(bufferSizeNum)) {
          setBufferSizeValue((prev) => ({ ...prev, [machineName]: String(bufferSizeNum) }));
          setOriginalBufferSizeValue((prev) => ({ ...prev, [machineName]: bufferSizeNum }));
        }
      }
    } catch (err: any) {
      const data = err?.response?.data;
      const backendMessage =
        (typeof data === "string" ? data : undefined) ??
        data?.message ??
        data?.detail ??
        data?.error;
      const errorMessage =
        backendMessage || err?.message || t("machines.updateAttributeError");
      showToast(errorMessage, "error");
      console.error("Error updating buffer_size:", err);
      // Restaurar valor original en caso de error
      if (originalBufferSizeValue[machineName] !== null) {
        setBufferSizeValue((prev) => ({ ...prev, [machineName]: String(originalBufferSizeValue[machineName]) }));
      }
    } finally {
      setUpdatingAttribute((prev) => ({ ...prev, [machineName]: null }));
    }
  };

  // Función helper para mostrar modal de confirmación de on_delay
  const handleUpdateOnDelay = (machineName: string) => {
    const value = parseInt(onDelayValue[machineName], 10);
    if (isNaN(value)) {
      showToast(t("machines.updateAttributeError"), "error");
      return;
    }

    // Solo mostrar modal si el valor cambió
    if (originalOnDelayValue[machineName] !== null && value === originalOnDelayValue[machineName]) {
      return;
    }

    setPendingUpdate({
      machineName,
      attribute: "on_delay",
      newValue: value,
      oldValue: originalOnDelayValue[machineName],
      attributeLabel: t("machines.onDelay"),
    });
    setShowConfirmModal(true);
  };

  // Función para ejecutar la actualización de on_delay después de confirmar
  const executeUpdateOnDelay = async (machineName: string, value: number) => {
    setUpdatingAttribute((prev) => ({ ...prev, [machineName]: "on_delay" }));
    try {
      const { message } = await updateMachineAttributes(machineName, {
        on_delay: value,
      });
      showToast(message || t("machines.updateAttribute"), "success");
      // Refrescar detalles de la máquina
      const data = await getMachineByName(machineName);
      setMachineDetails((prev) => ({
        ...prev,
        [machineName]: data,
      }));
      // Actualizar el valor del input y el valor original
      if (data.serialization?.on_delay !== null && data.serialization?.on_delay !== undefined) {
        const onDelayNum = typeof data.serialization.on_delay === "number" 
          ? data.serialization.on_delay 
          : parseInt(String(data.serialization.on_delay), 10);
        if (!isNaN(onDelayNum)) {
          setOnDelayValue((prev) => ({ ...prev, [machineName]: String(onDelayNum) }));
          setOriginalOnDelayValue((prev) => ({ ...prev, [machineName]: onDelayNum }));
        }
      }
    } catch (err: any) {
      const data = err?.response?.data;
      const backendMessage =
        (typeof data === "string" ? data : undefined) ??
        data?.message ??
        data?.detail ??
        data?.error;
      const errorMessage =
        backendMessage || err?.message || t("machines.updateAttributeError");
      showToast(errorMessage, "error");
      console.error("Error updating on_delay:", err);
      // Restaurar valor original en caso de error
      if (originalOnDelayValue[machineName] !== null) {
        setOnDelayValue((prev) => ({ ...prev, [machineName]: String(originalOnDelayValue[machineName]) }));
      }
    } finally {
      setUpdatingAttribute((prev) => ({ ...prev, [machineName]: null }));
    }
  };

  // Función para confirmar y ejecutar la actualización
  const handleConfirmUpdate = async () => {
    if (!pendingUpdate) return;

    const { machineName, attribute, newValue } = pendingUpdate;

    if (attribute === "threshold") {
      await executeUpdateThreshold(machineName, newValue);
    } else if (attribute === "buffer_size") {
      await executeUpdateBufferSize(machineName, newValue);
    } else if (attribute === "on_delay") {
      await executeUpdateOnDelay(machineName, newValue);
    }

    setShowConfirmModal(false);
    setPendingUpdate(null);
  };

  // Función para cancelar la actualización
  const handleCancelUpdate = () => {
    if (!pendingUpdate) return;

    const { machineName, attribute, oldValue } = pendingUpdate;

    // Restaurar el valor original en el input
    if (attribute === "threshold" && oldValue !== null) {
      setThresholdValue((prev) => ({ ...prev, [machineName]: String(oldValue) }));
    } else if (attribute === "buffer_size" && oldValue !== null) {
      setBufferSizeValue((prev) => ({ ...prev, [machineName]: String(oldValue) }));
    } else if (attribute === "on_delay" && oldValue !== null) {
      setOnDelayValue((prev) => ({ ...prev, [machineName]: String(oldValue) }));
    }

    setShowConfirmModal(false);
    setPendingUpdate(null);
  };

  // Inicializar valores de atributos cuando se cargan los detalles de la máquina
  useEffect(() => {
    Object.entries(machineDetails).forEach(([machineName, details]) => {
      if (details && details.serialization) {
        const serialization = details.serialization;
        
        // Inicializar threshold
        if (serialization.threshold) {
          const threshold = serialization.threshold;
          const thresholdVal = typeof threshold === "object" && threshold !== null && "value" in threshold
            ? threshold.value
            : threshold;
          if (thresholdVal !== null && thresholdVal !== undefined) {
            const thresholdNum = typeof thresholdVal === "number" ? thresholdVal : parseFloat(String(thresholdVal));
            if (!isNaN(thresholdNum)) {
              setThresholdValue((prev) => {
                if (prev[machineName] === undefined || prev[machineName] === "") {
                  return { ...prev, [machineName]: String(thresholdNum) };
                }
                return prev;
              });
              setOriginalThresholdValue((prev) => ({ ...prev, [machineName]: thresholdNum }));
            }
          }
        }
        
        // Inicializar buffer_size
        if (serialization.buffer_size !== null && serialization.buffer_size !== undefined) {
          const bufferSizeNum = typeof serialization.buffer_size === "number" 
            ? serialization.buffer_size 
            : parseInt(String(serialization.buffer_size), 10);
          if (!isNaN(bufferSizeNum)) {
            setBufferSizeValue((prev) => {
              if (prev[machineName] === undefined || prev[machineName] === "") {
                return { ...prev, [machineName]: String(bufferSizeNum) };
              }
              return prev;
            });
            setOriginalBufferSizeValue((prev) => ({ ...prev, [machineName]: bufferSizeNum }));
          }
        }
        
        // Inicializar on_delay
        if (serialization.on_delay !== null && serialization.on_delay !== undefined) {
          const onDelayNum = typeof serialization.on_delay === "number" 
            ? serialization.on_delay 
            : parseInt(String(serialization.on_delay), 10);
          if (!isNaN(onDelayNum)) {
            setOnDelayValue((prev) => {
              if (prev[machineName] === undefined || prev[machineName] === "") {
                return { ...prev, [machineName]: String(onDelayNum) };
              }
              return prev;
            });
            setOriginalOnDelayValue((prev) => ({ ...prev, [machineName]: onDelayNum }));
          }
        }
      }
    });
  }, [machineDetails]);

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

  // Suscripción a eventos completos de máquinas con buffering (para actualizar state y otros atributos)
  useEffect(() => {
    // Función para aplicar las actualizaciones pendientes de máquinas
    const flushMachineUpdates = () => {
      if (pendingMachineUpdatesRef.current.size === 0) {
        return;
      }

      console.log("Flushing machine updates:", Array.from(pendingMachineUpdatesRef.current.keys()));

      // Aplicar todas las actualizaciones acumuladas
      setMachineDetails((prev) => {
        const updated = { ...prev };
        let hasUpdates = false;

        // Iterar sobre todas las actualizaciones pendientes
        pendingMachineUpdatesRef.current.forEach((updatedMachine, machineName) => {
          // Solo actualizar si tenemos datos de esta máquina
          if (updated[machineName]) {
            hasUpdates = true;
            // Crear una copia profunda de los detalles actuales
            const currentDetails = { ...updated[machineName] };
            
            // Actualizar el estado en serialization
            if (currentDetails.serialization && typeof currentDetails.serialization === "object") {
              currentDetails.serialization = {
                ...currentDetails.serialization,
                state: updatedMachine.state,
                // Actualizar otros atributos que puedan cambiar
                criticity: updatedMachine.criticity,
                priority: updatedMachine.priority,
                actions: updatedMachine.actions,
                machine_interval: updatedMachine.machine_interval,
                buffer_size: updatedMachine.buffer_size,
                buffer_roll_type: updatedMachine.buffer_roll_type,
              };
              console.log(`Updated machine ${machineName} state to:`, updatedMachine.state);
            }
            
            updated[machineName] = currentDetails;
          }
        });

        // Limpiar el buffer después de aplicar
        pendingMachineUpdatesRef.current.clear();

        return hasUpdates ? updated : prev;
      });
    };

    // Iniciar intervalo para hacer flush cada 1 segundo
    machineUpdateIntervalRef.current = setInterval(() => {
      flushMachineUpdates();
    }, 1000);

    // Suscribirse a actualizaciones completas de máquinas
    const cleanup = socketService.onMachineUpdate((machine: Machine) => {
      // machine es un objeto Machine completo con toda la información
      console.log("On machine update received:", machine);
      
      if (machine.name) {
        // Usar una función de actualización para acceder al estado actual sin depender de él
        setMachineDetails((prev) => {
          // Solo procesar si esta máquina está en nuestros detalles cargados
          if (prev[machine.name]) {
            // Guardar en el buffer (sobrescribe si ya existe)
            pendingMachineUpdatesRef.current.set(machine.name, machine);
          }
          // No cambiar el estado aquí, solo actualizar el buffer
          return prev;
        });
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

  // Suscripción a eventos de tags con buffering (para actualizar process_variables asociados)
  useEffect(() => {
    // Función para aplicar las actualizaciones pendientes de tags
    const flushTagUpdates = () => {
      if (pendingTagUpdatesRef.current.size === 0) {
        return;
      }

      console.log("Flushing tag updates:", Array.from(pendingTagUpdatesRef.current.keys()));

      // Aplicar todas las actualizaciones acumuladas
      setMachineDetails((prev) => {
        const updated = { ...prev };
        let hasUpdates = false;

        // Iterar sobre todas las actualizaciones pendientes de tags
        pendingTagUpdatesRef.current.forEach((updatedTag, tagId) => {
          // Buscar en todas las máquinas si algún process_variable tiene este tag asociado
          Object.keys(updated).forEach((machineName) => {
            const machineDetails = updated[machineName];
            if (!machineDetails || !machineDetails.process_variables) {
              return;
            }

            // Buscar en process_variables
            Object.keys(machineDetails.process_variables).forEach((varKey) => {
              const processVar = machineDetails.process_variables[varKey];
              if (
                processVar &&
                typeof processVar === "object" &&
                processVar.tag &&
                typeof processVar.tag === "object"
              ) {
                // Verificar si el tag coincide por id o name
                const tagMatches =
                  (processVar.tag.id && String(processVar.tag.id) === String(tagId)) ||
                  (processVar.tag.name && processVar.tag.name === updatedTag.name) ||
                  (updatedTag.id && String(processVar.tag.id) === String(updatedTag.id));

                if (tagMatches) {
                  hasUpdates = true;
                  // Actualizar el tag dentro del process_variable
                  const updatedProcessVar = {
                    ...processVar,
                    tag: {
                      ...processVar.tag,
                      ...updatedTag,
                      // Preservar el value actualizado del tag
                      value: updatedTag.value !== undefined ? updatedTag.value : processVar.tag.value,
                    },
                  };

                  // También actualizar el value del process_variable si el tag tiene value
                  if (updatedTag.value !== undefined) {
                    updatedProcessVar.value = updatedTag.value;
                  }

                  // Actualizar en la copia de los detalles
                  updated[machineName] = {
                    ...machineDetails,
                    process_variables: {
                      ...machineDetails.process_variables,
                      [varKey]: updatedProcessVar,
                    },
                  };

                  console.log(
                    `Updated process_variable ${varKey} in machine ${machineName} with tag ${updatedTag.name || tagId}`
                  );
                }
              }
            });

            // También buscar en subscribed_tags, not_subscribed_tags, etc.
            const tagCollections = [
              "subscribed_tags",
              "not_subscribed_tags",
              "read_only_process_type_variables",
            ];

            tagCollections.forEach((collectionKey) => {
              const collection = machineDetails[collectionKey];
              if (collection && typeof collection === "object") {
                Object.keys(collection).forEach((varKey) => {
                  const processVar = collection[varKey];
                  if (
                    processVar &&
                    typeof processVar === "object" &&
                    processVar.tag &&
                    typeof processVar.tag === "object"
                  ) {
                    const tagMatches =
                      (processVar.tag.id && String(processVar.tag.id) === String(tagId)) ||
                      (processVar.tag.name && processVar.tag.name === updatedTag.name) ||
                      (updatedTag.id && String(processVar.tag.id) === String(updatedTag.id));

                    if (tagMatches) {
                      hasUpdates = true;
                      const updatedProcessVar = {
                        ...processVar,
                        tag: {
                          ...processVar.tag,
                          ...updatedTag,
                          value: updatedTag.value !== undefined ? updatedTag.value : processVar.tag.value,
                        },
                      };

                      if (updatedTag.value !== undefined) {
                        updatedProcessVar.value = updatedTag.value;
                      }

                      updated[machineName] = {
                        ...updated[machineName],
                        [collectionKey]: {
                          ...collection,
                          [varKey]: updatedProcessVar,
                        },
                      };
                    }
                  }
                });
              }
            });
          });
        });

        // Limpiar el buffer después de aplicar
        pendingTagUpdatesRef.current.clear();

        return hasUpdates ? updated : prev;
      });
    };

    // Iniciar intervalo para hacer flush cada 1 segundo
    tagUpdateIntervalRef.current = setInterval(() => {
      flushTagUpdates();
    }, 1000);

    // Suscribirse a actualizaciones de tags
    const cleanup = socketService.onTagUpdate((tag: Tag) => {
      // tag es un objeto Tag completo con toda la información
      console.log("On tag update received:", tag);

      if (tag.id || tag.name) {
        // Usar id como clave principal, o name como fallback
        const tagKey = tag.id ? String(tag.id) : (tag.name || "");
        
        if (tagKey) {
          // Guardar en el buffer (sobrescribe si ya existe)
          pendingTagUpdatesRef.current.set(tagKey, tag);
        }
      }
    });

    // Cleanup al desmontar
    return () => {
      cleanup();
      if (tagUpdateIntervalRef.current) {
        clearInterval(tagUpdateIntervalRef.current);
        tagUpdateIntervalRef.current = null;
      }
      // Aplicar cualquier actualización pendiente antes de limpiar
      flushTagUpdates();
      pendingTagUpdatesRef.current.clear();
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
      "name",
      "auto_restart",
      "identifier",
      "threshold",
      "on_wait_time"
    ];

    const attributes: Array<[string, any]> = [];
    const processedKeys = new Set<string>(); // Para evitar duplicados
    const firstLevelAttributes = new Map<string, any>(); // Para almacenar atributos de primer nivel
    const processVariables = new Map<string, any>(); // Para almacenar process_variables
    
    // Orden de prioridad para atributos de primer nivel
    const priorityOrder = ["state", "description", "classification", "priority", "criticity"];
    
    // 1. Recopilar TODAS las process_variables primero (estas tienen prioridad porque se actualizan en tiempo real)
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
          processVariables.set(varKey, formattedValue);
        } else {
          processVariables.set(varKey, varValue);
        }
      });
    }
    
    // 2. Recopilar atributos de primer nivel de serialization (solo los que NO están en process_variables)
    if (data.serialization && typeof data.serialization === "object" && data.serialization !== null) {
      Object.entries(data.serialization).forEach(([subKey, subValue]) => {
        // Omitir si está en excludedKeys, es "actions", o si ya está en process_variables
        if (!excludedKeys.includes(subKey) && subKey !== "actions" && !processVariables.has(subKey)) {
          // Formatear si es un objeto con value y unit
          if (typeof subValue === "object" && subValue !== null && "value" in subValue && "unit" in subValue) {
            const formattedValue = `${subValue.value ?? "-"} ${subValue.unit ?? ""}`.trim();
            firstLevelAttributes.set(subKey, formattedValue);
          } else {
            firstLevelAttributes.set(subKey, subValue);
          }
        }
      });
    }
    
    // 3. Recopilar otros atributos del nivel raíz (solo los que NO están en process_variables)
    Object.entries(data).forEach(([key, value]) => {
      if (!excludedKeys.includes(key) && !processVariables.has(key) && key !== "process_variables" && key !== "serialization") {
        firstLevelAttributes.set(key, value);
      }
    });
    
    // 4. Agregar atributos en el orden correcto:
    // Primero los de prioridad que NO están en process_variables
    priorityOrder.forEach((key) => {
      if (firstLevelAttributes.has(key)) {
        attributes.push([key, firstLevelAttributes.get(key)]);
        firstLevelAttributes.delete(key);
        processedKeys.add(key);
      }
    });
    
    // Luego TODAS las process_variables (estas se actualizan en tiempo real)
    processVariables.forEach((value, key) => {
      attributes.push([key, value]);
      processedKeys.add(key);
    });
    
    // Finalmente, el resto de atributos de primer nivel (ordenados alfabéticamente)
    const remainingFirstLevel = Array.from(firstLevelAttributes.entries()).sort((a, b) => a[0].localeCompare(b[0]));
    remainingFirstLevel.forEach(([key, value]) => {
      attributes.push([key, value]);
      processedKeys.add(key);
    });

    return attributes;
  };

  // Función para obtener la clase del badge según el estado
  const getStateBadgeClass = (state: string): string => {
    const stateLower = String(state).toLowerCase().trim();
    
    if (stateLower === "starting" || stateLower === "restarting" || stateLower === "resetting") {
      return "badge bg-secondary"; // gray
    } else if (stateLower === "waiting" || stateLower === "test") {
      return "badge bg-info"; // azul claro
    } else if (stateLower === "running") {
      return "badge bg-success"; // verde
    } else if (stateLower === "pre_alarming") {
      return "badge bg-warning"; // amarillo
    } else if (stateLower === "leaking" || stateLower === "sleep") {
      return "badge bg-danger"; // rojo
    } else if (
      stateLower === "con_restart" ||
      stateLower === "confirm_restart" ||
      stateLower === "confirm_restarting" ||
      stateLower === "con_reset" ||
      stateLower === "confirm_reset" ||
      stateLower === "confirm_resetting"
    ) {
      return "badge bg-warning"; // amarillo
    }
    
    // Default
    return "badge bg-secondary";
  };

  // Función para verificar si un estado debe tener efecto blinking
  const shouldBlink = (state: string): boolean => {
    const stateLower = String(state).toLowerCase().trim();
    return (
      stateLower === "leaking" ||
      stateLower === "con_restart" ||
      stateLower === "confirm_restart" ||
      stateLower === "confirm_restarting" ||
      stateLower === "con_reset" ||
      stateLower === "confirm_reset" ||
      stateLower === "confirm_resetting"
    );
  };

  // Función para obtener el estilo del badge según el valor numérico (1-5)
  const getNumericBadgeStyle = (value: number): { className: string; style?: CSSProperties } => {
    if (value === 1) {
      return { className: "badge bg-success" }; // verde
    } else if (value === 2) {
      // Intermedio entre verde y amarillo
      return { 
        className: "badge",
        style: { backgroundColor: "#7cb342", color: "#fff" } // verde-amarillo
      };
    } else if (value === 3) {
      return { className: "badge bg-warning" }; // amarillo
    } else if (value === 4) {
      // Intermedio entre amarillo y rojo
      return { 
        className: "badge",
        style: { backgroundColor: "#ff9800", color: "#fff" } // amarillo-rojo (naranja)
      };
    } else if (value === 5) {
      return { className: "badge bg-danger" }; // rojo
    }
    // Default
    return { className: "badge bg-secondary" };
  };

  // Función para formatear el valor de un atributo
  const formatAttributeValue = (value: any, attributeName?: string): string | JSX.Element => {
    if (value === null || value === undefined) return "-";
    
    // Si es el atributo "state", mostrar como badge
    if (attributeName === "state") {
      const stateValue = typeof value === "object" && value !== null && "value" in value 
        ? value.value 
        : value;
      const stateStr = String(stateValue);
      const badgeClass = getStateBadgeClass(stateStr);
      const needsBlink = shouldBlink(stateStr);
      
      return (
        <span 
          className={badgeClass}
          style={needsBlink ? { animation: "blink-alarm 1s infinite" } : undefined}
        >
          {stateStr}
        </span>
      );
    }
    
    // Si es el atributo "priority" o "criticity", mostrar como badge numérico
    if (attributeName === "priority" || attributeName === "criticity") {
      const numericValue = typeof value === "object" && value !== null && "value" in value 
        ? value.value 
        : value;
      const numValue = typeof numericValue === "number" ? numericValue : parseInt(String(numericValue), 10);
      
      if (!isNaN(numValue) && numValue >= 1 && numValue <= 5) {
        const badgeStyle = getNumericBadgeStyle(numValue);
        return (
          <span 
            className={badgeStyle.className}
            style={badgeStyle.style}
          >
            {numValue}
          </span>
        );
      }
      // Si no es un número válido, mostrar como texto normal
      return String(numericValue);
    }
    
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
                const isBufferSizeLocked = ["pfm", "observer"].includes(
                  String(machineName).toLowerCase()
                );
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
                                <table className="table table-striped table-hover" style={{ tableLayout: "fixed", width: "100%" }}>
                                  <thead>
                                    <tr>
                                      <th style={{ width: "40%" }}>{t("machines.attribute")}</th>
                                      <th style={{ width: "60%" }}>{t("machines.value")}</th>
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
                                          <td style={{ width: "40%", wordBreak: "break-word" }}><strong>{key}</strong></td>
                                          <td style={{ width: "60%", wordBreak: "break-word" }}>{formatAttributeValue(value, key)}</td>
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
                                  <select
                                    className="form-select"
                                    value={selectedSubscribedTag[machineName] || ""}
                                    onChange={(e) => setSelectedSubscribedTag((prev) => ({ ...prev, [machineName]: e.target.value }))}
                                  >
                                    <option value="">{t("machines.selectSubscribedTag")}</option>
                                    {Object.entries(machineDetails[machineName].subscribed_tags || {}).map(([fieldTag, processVar]) => {
                                      // Buscar el nombre de la variable interna asociada a este field tag
                                      // En subscribed_tags, la clave es el field tag (ej: "PI_02")
                                      // Necesitamos encontrar qué variable interna tiene ese tag asociado
                                      // En read_only_process_type_variables, la clave es el nombre de la variable interna
                                      // y varData.tag.name es el field tag
                                      let internalTagName = "";
                                      
                                      // Normalizar el fieldTag para comparación (sin espacios, en minúsculas)
                                      const normalizedFieldTag = String(fieldTag).trim();
                                      
                                      // Buscar en read_only_process_type_variables (donde están las variables internas suscritas)
                                      const readOnlyVars = machineDetails[machineName].read_only_process_type_variables || {};
                                      for (const [varName, varData] of Object.entries(readOnlyVars)) {
                                        if (varData && typeof varData === "object" && varData.tag && typeof varData.tag === "object" && varData.tag.name) {
                                          // El tag.name puede ser "MACHINE.fieldTag" (ej: "PPA.PI_02") o solo "fieldTag" (ej: "PI_02")
                                          const tagName = String(varData.tag.name).trim();
                                          // Extraer solo la parte del field tag (después del punto si existe)
                                          const tagNameParts = tagName.split(".");
                                          const tagNameWithoutMachine = tagNameParts.length > 1 ? tagNameParts[tagNameParts.length - 1] : tagName;
                                          
                                          // Comparar: el fieldTag debe coincidir con el tagName (con o sin prefijo de máquina)
                                          // varName es el nombre de la variable interna (ej: "outlet_pressure")
                                          if (tagName === normalizedFieldTag || tagNameWithoutMachine === normalizedFieldTag) {
                                            internalTagName = varName; // Usar varName, no tagName
                                            break;
                                          }
                                        }
                                      }
                                      
                                      // Si no se encontró en read_only, buscar en process_variables
                                      if (!internalTagName) {
                                        const processVars = machineDetails[machineName].process_variables || {};
                                        for (const [varName, varData] of Object.entries(processVars)) {
                                          if (varData && typeof varData === "object" && varData.tag && typeof varData.tag === "object" && varData.tag.name) {
                                            const tagName = String(varData.tag.name).trim();
                                            const tagNameParts = tagName.split(".");
                                            const tagNameWithoutMachine = tagNameParts.length > 1 ? tagNameParts[tagNameParts.length - 1] : tagName;
                                            
                                            if (tagName === normalizedFieldTag || tagNameWithoutMachine === normalizedFieldTag) {
                                              internalTagName = varName; // Usar varName, no tagName
                                              break;
                                            }
                                          }
                                        }
                                      }
                                      
                                      // Mostrar "fieldTag -> internalTag" o solo "fieldTag" si no hay internalTag
                                      const displayText = internalTagName 
                                        ? `${fieldTag} → ${internalTagName}`
                                        : fieldTag;
                                      
                                      return (
                                        <option key={fieldTag} value={fieldTag}>
                                          {displayText}
                                        </option>
                                      );
                                    })}
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
                          
                          {/* Card de Atributos de Máquina (solo para máquinas de leak detection) */}
                          {machineDetails[machineName] && 
                           machineDetails[machineName].serialization &&
                           machineDetails[machineName].serialization.classification &&
                           machineDetails[machineName].serialization.classification.toLowerCase().includes("leak detection") && (
                            <Card title={t("machines.machineAttributes")} className="mt-3">
                              <div>
                                {/* Input de Threshold */}
                                <div className="mb-3 d-flex align-items-center gap-2">
                                  <label className="form-label mb-0" style={{ minWidth: "120px" }}>
                                    {t("machines.threshold")}:
                                  </label>
                                  <input
                                    type="number"
                                    className="form-control"
                                    style={{ maxWidth: "150px" }}
                                    placeholder={t("machines.thresholdPlaceholder")}
                                    value={thresholdValue[machineName] || ""}
                                    onChange={(e) => setThresholdValue((prev) => ({ ...prev, [machineName]: e.target.value }))}
                                    onKeyDown={(e) => {
                                      if (e.key === "Enter") {
                                        e.preventDefault();
                                        handleUpdateThreshold(machineName);
                                      }
                                    }}
                                    onBlur={() => {
                                      if (thresholdValue[machineName] && thresholdValue[machineName] !== "") {
                                        handleUpdateThreshold(machineName);
                                      }
                                    }}
                                    disabled={updatingAttribute[machineName] === "threshold"}
                                  />
                                  {updatingAttribute[machineName] === "threshold" && (
                                    <div className="spinner-border spinner-border-sm text-primary" role="status">
                                      <span className="visually-hidden">{t("common.loading")}</span>
                                    </div>
                                  )}
                                </div>

                                {/* Input de Buffer Size */}
                                <div className="mb-3 d-flex align-items-center gap-2">
                                  <label className="form-label mb-0" style={{ minWidth: "120px" }}>
                                    {t("machines.bufferSize")}:
                                  </label>
                                  <input
                                    type="number"
                                    className="form-control"
                                    style={{ maxWidth: "150px" }}
                                    placeholder={t("machines.bufferSizePlaceholder")}
                                    value={bufferSizeValue[machineName] || ""}
                                    onChange={(e) => setBufferSizeValue((prev) => ({ ...prev, [machineName]: e.target.value }))}
                                    onKeyDown={(e) => {
                                      if (isBufferSizeLocked) return;
                                      if (e.key === "Enter") {
                                        e.preventDefault();
                                        handleUpdateBufferSize(machineName);
                                      }
                                    }}
                                    onBlur={() => {
                                      if (isBufferSizeLocked) return;
                                      if (bufferSizeValue[machineName] && bufferSizeValue[machineName] !== "") {
                                        handleUpdateBufferSize(machineName);
                                      }
                                    }}
                                    disabled={updatingAttribute[machineName] === "buffer_size" || isBufferSizeLocked}
                                  />
                                  {updatingAttribute[machineName] === "buffer_size" && (
                                    <div className="spinner-border spinner-border-sm text-primary" role="status">
                                      <span className="visually-hidden">{t("common.loading")}</span>
                                    </div>
                                  )}
                                </div>

                                {/* Input de On Delay */}
                                <div className="mb-3 d-flex align-items-center gap-2">
                                  <label className="form-label mb-0" style={{ minWidth: "120px" }}>
                                    {t("machines.onDelay")}:
                                  </label>
                                  <input
                                    type="number"
                                    className="form-control"
                                    style={{ maxWidth: "150px" }}
                                    placeholder={t("machines.onDelayPlaceholder")}
                                    value={onDelayValue[machineName] || ""}
                                    onChange={(e) => setOnDelayValue((prev) => ({ ...prev, [machineName]: e.target.value }))}
                                    onKeyDown={(e) => {
                                      if (e.key === "Enter") {
                                        e.preventDefault();
                                        handleUpdateOnDelay(machineName);
                                      }
                                    }}
                                    onBlur={() => {
                                      if (onDelayValue[machineName] && onDelayValue[machineName] !== "") {
                                        handleUpdateOnDelay(machineName);
                                      }
                                    }}
                                    disabled={updatingAttribute[machineName] === "on_delay"}
                                  />
                                  {updatingAttribute[machineName] === "on_delay" && (
                                    <div className="spinner-border spinner-border-sm text-primary" role="status">
                                      <span className="visually-hidden">{t("common.loading")}</span>
                                    </div>
                                  )}
                                </div>
                              </div>
                            </Card>
                          )}
                        </div>
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          </>
        )}

        {/* Modal de confirmación de actualización de atributo */}
        {showConfirmModal && pendingUpdate && (
          <div
            className="modal fade show"
            style={{ display: "block", backgroundColor: "rgba(0,0,0,0.5)" }}
            tabIndex={-1}
            role="dialog"
            aria-modal="true"
            onClick={(e) => {
              if (e.target === e.currentTarget && !updatingAttribute[pendingUpdate.machineName]) {
                handleCancelUpdate();
              }
            }}
          >
            <div className="modal-dialog modal-dialog-centered" role="document">
              <div className="modal-content" onClick={(e) => e.stopPropagation()}>
                <div className="modal-header">
                  <h5 className="modal-title">{t("machines.confirmAttributeUpdate")}</h5>
                  <button
                    type="button"
                    className="btn-close"
                    onClick={handleCancelUpdate}
                    aria-label="Close"
                    disabled={!!updatingAttribute[pendingUpdate.machineName]}
                  ></button>
                </div>
                <div className="modal-body">
                  <p>{t("machines.confirmAttributeUpdateMessage")}</p>
                  <div className="mb-2">
                    <strong>{t("machines.machine")}:</strong> {pendingUpdate.machineName}
                  </div>
                  <div className="mb-2">
                    <strong>{t("machines.attribute")}:</strong> {pendingUpdate.attributeLabel}
                  </div>
                  <div className="mb-2">
                    <strong>{t("machines.currentValue")}:</strong>{" "}
                    <span className="badge bg-secondary">
                      {pendingUpdate.oldValue !== null ? pendingUpdate.oldValue : "-"}
                    </span>
                  </div>
                  <div>
                    <strong>{t("machines.newValue")}:</strong>{" "}
                    <span className="badge bg-primary">{pendingUpdate.newValue}</span>
                  </div>
                </div>
                <div className="modal-footer">
                  <Button
                    variant="secondary"
                    onClick={handleCancelUpdate}
                    disabled={!!updatingAttribute[pendingUpdate.machineName]}
                  >
                    {t("common.cancel")}
                  </Button>
                  <Button
                    variant="primary"
                    onClick={handleConfirmUpdate}
                    disabled={!!updatingAttribute[pendingUpdate.machineName]}
                    loading={!!updatingAttribute[pendingUpdate.machineName]}
                  >
                    {t("common.confirm")}
                  </Button>
                </div>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

