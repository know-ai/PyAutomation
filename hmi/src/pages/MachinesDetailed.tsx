import { useEffect, useState, useRef, useMemo } from "react";
import type { JSX, CSSProperties } from "react";
import { Card } from "../components/Card";
import { Button } from "../components/Button";
import { useTranslation } from "../hooks/useTranslation";
import {
  getMachines,
  getMachineByName,
  getMachineDomainConfig,
  subscribeMachineTag,
  unsubscribeMachineTag,
  updateMachineAttributes,
  type DomainUiHints,
  type DomainUiSchema,
  type Machine,
} from "../services/machines";
import { DomainConfigSlot } from "../components/DomainConfigSlot";
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

/** Nombres de tags de campo ya suscritos (clave API + source + par .f). */
function collectSubscribedFieldTagNames(details: MachineDetailedData): Set<string> {
  const names = new Set<string>();
  const addPair = (name: string | undefined | null) => {
    if (!name) return;
    names.add(name);
    if (name.endsWith(".f")) {
      names.add(name.slice(0, -2));
    } else {
      names.add(`${name}.f`);
    }
  };
  for (const [key, val] of Object.entries(details.subscribed_tags || {})) {
    addPair(key);
    const nested = val && typeof val === "object" ? (val as { tag?: { name?: string }; source_name?: string }).tag?.name : undefined;
    addPair(typeof nested === "string" ? nested : undefined);
    const source =
      val && typeof val === "object"
        ? (val as { source_name?: string }).source_name
        : undefined;
    addPair(typeof source === "string" ? source : undefined);
  }
  for (const val of Object.values(details.read_only_process_type_variables || {})) {
    const nested =
      val && typeof val === "object"
        ? (val as { tag?: { name?: string } }).tag?.name
        : undefined;
    addPair(typeof nested === "string" ? nested : undefined);
  }
  return names;
}

/** Tags de campo aún libres para suscribir (solo raw; nunca .f). */
function getAvailableFieldTags(details: MachineDetailedData): string[] {
  const subscribed = collectSubscribedFieldTagNames(details);
  return (details.field_tags || []).filter(
    (name) => !name.endsWith(".f") && !subscribed.has(name)
  );
}

function subscribedInternalVariableNames(details: MachineDetailedData): Set<string> {
  return new Set(Object.keys(details.read_only_process_type_variables || {}));
}

function hideExclusivePairSiblings(
  keys: string[],
  subscribed: Set<string>,
  pairs: ReadonlyArray<readonly string[]>
): string[] {
  const hidden = new Set<string>();
  for (const pair of pairs) {
    const taken = pair.some((name) => subscribed.has(name));
    if (!taken) continue;
    for (const name of pair) {
      if (!subscribed.has(name)) hidden.add(name);
    }
  }
  return keys.filter((key) => !hidden.has(key));
}

type MachineUiHints = DomainUiHints;

/** Variables internas sin tag asignado (Tags No Suscritos), con pares exclusivos desde ui_hints. */
function getNotSubscribedTagKeys(details: MachineDetailedData, pairs: ReadonlyArray<readonly string[]>): string[] {
  const keys = Object.keys(details.not_subscribed_tags || {});
  const subscribed = subscribedInternalVariableNames(details);
  if (!pairs.length) return keys;
  return hideExclusivePairSiblings(keys, subscribed, pairs);
}

function extractProcessUnit(value: unknown): string {
  if (!value || typeof value !== "object") return "";
  const record = value as { unit?: unknown; value?: unknown; tag?: { unit?: unknown } };
  if (typeof record.unit === "string" && record.unit.trim()) return record.unit.trim();
  if (record.value && typeof record.value === "object") {
    const nestedUnit = (record.value as { unit?: unknown }).unit;
    if (typeof nestedUnit === "string" && nestedUnit.trim()) return nestedUnit.trim();
  }
  if (typeof record.tag?.unit === "string" && record.tag.unit.trim()) return record.tag.unit.trim();
  return "";
}

function getThresholdUnitLabel(
  details: MachineDetailedData | undefined,
  hints: MachineUiHints | undefined,
  t: (key: string) => string
): { label: string; hint: string } {
  const pv = details?.process_variables || {};
  const ser = details?.serialization;
  const empty = { label: "", hint: "" };
  const hinted = hints?.threshold_unit?.trim();
  if (hinted) {
    return {
      label: hinted,
      hint: hinted === "%" || hinted.toLowerCase().includes("percent") ? t("machines.thresholdUnitPercentHint") : "",
    };
  }
  const unit = extractProcessUnit(pv.threshold) || extractProcessUnit(ser?.threshold);
  if (!unit) return empty;
  const looksPercent = unit === "%" || unit.toLowerCase().includes("percent");
  return {
    label: unit,
    hint: looksPercent ? t("machines.thresholdUnitPercentHint") : "",
  };
}

function hasGenericAttributes(details: MachineDetailedData | undefined): boolean {
  const ser = details?.serialization;
  if (!ser) return false;
  return (
    ser.threshold !== undefined ||
    ser.on_delay !== undefined ||
    ser.buffer_size !== undefined
  );
}

export function MachinesDetailed() {
  const { t } = useTranslation();
  const [machines, setMachines] = useState<Machine[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<string | null>(null);
  const [machineDetails, setMachineDetails] = useState<Record<string, MachineDetailedData>>({});
  const [loadingDetails, setLoadingDetails] = useState<Record<string, boolean>>({});
  const [currentPage, setCurrentPage] = useState<Record<string, number>>({});
  
  // Estados para los dropdowns del card de Tags Subscriptions (por m?quina)
  const [selectedSubscribedTag, setSelectedSubscribedTag] = useState<Record<string, string>>({});
  const [selectedReadOnlyVariable, setSelectedReadOnlyVariable] = useState<Record<string, string>>({});
  const [selectedInternalVariable, setSelectedInternalVariable] = useState<Record<string, string>>({});
  
  // Estados para los inputs de atributos de m?quina (por m?quina)
  const [thresholdValue, setThresholdValue] = useState<Record<string, string>>({});
  const [bufferSizeValue, setBufferSizeValue] = useState<Record<string, string>>({});
  const [onDelayValue, setOnDelayValue] = useState<Record<string, string>>({});
  const [updatingAttribute, setUpdatingAttribute] = useState<Record<string, string | null>>({});
  // Valores originales para comparar si cambi?
  const [originalThresholdValue, setOriginalThresholdValue] = useState<Record<string, number | null>>({});
  const [originalBufferSizeValue, setOriginalBufferSizeValue] = useState<Record<string, number | null>>({});
  const [originalOnDelayValue, setOriginalOnDelayValue] = useState<Record<string, number | null>>({});
  const [customizeSampling, setCustomizeSampling] = useState<Record<string, boolean>>({});
  const [sampleIntervalValue, setSampleIntervalValue] = useState<Record<string, string>>({});
  const [executionIntervalValue, setExecutionIntervalValue] = useState<Record<string, string>>({});
  const [sampleOverrideValue, setSampleOverrideValue] = useState<Record<string, Record<string, string>>>({});
  const [savingTemporal, setSavingTemporal] = useState<Record<string, boolean>>({});
  // Estado para el modal de confirmaci?n
  const [showConfirmModal, setShowConfirmModal] = useState(false);
  const [pendingUpdate, setPendingUpdate] = useState<{
    machineName: string;
    attribute: "threshold" | "buffer_size" | "on_delay";
    newValue: number | string;
    oldValue: number | string | null;
    attributeLabel: string;
  } | null>(null);
  const [domainSchemas, setDomainSchemas] = useState<Record<string, DomainUiSchema>>({});
  const [domainConfigs, setDomainConfigs] = useState<Record<string, Record<string, unknown>>>({});

  const uiHintsFor = (machineName: string): MachineUiHints =>
    domainSchemas[machineName]?.ui_hints || {};

  const refreshDomainConfig = async (machineName: string, details?: MachineDetailedData | null) => {
    const hasDomain =
      details?.serialization?.has_domain_config ??
      machineDetails[machineName]?.serialization?.has_domain_config;
    if (!hasDomain) return;
    try {
      const domain = await getMachineDomainConfig(machineName);
      if (!domain) return;
      setDomainSchemas((prev) => ({ ...prev, [machineName]: domain.schema || {} }));
      setDomainConfigs((prev) => ({ ...prev, [machineName]: domain.config || {} }));
    } catch (domainErr: any) {
      const payload = domainErr?.response?.data;
      const message =
        (typeof payload === "string" ? payload : undefined) ??
        payload?.message ??
        t("machines.domainConfigLoadError");
      showToast(message, "error");
    }
  };

  const isAttributeLocked = (machineName: string, attribute: string): boolean =>
    (uiHintsFor(machineName).lock_generic_attributes || []).includes(attribute);

  const extractActiveThreshold = (serialization: any): number | null => {
    if (!serialization) return null;
    const active = serialization.active_detection_threshold;
    if (active !== null && active !== undefined) {
      const n = typeof active === "number" ? active : parseFloat(String(active));
      if (!isNaN(n)) return n;
    }
    const threshold = serialization.threshold;
    const thresholdVal =
      typeof threshold === "object" && threshold !== null && "value" in threshold
        ? threshold.value
        : threshold;
    if (thresholdVal !== null && thresholdVal !== undefined) {
      const n = typeof thresholdVal === "number" ? thresholdVal : parseFloat(String(thresholdVal));
      if (!isNaN(n)) return n;
    }
    return null;
  };

  // Buffer para actualizaciones de propiedades de m?quinas (patr?n de 1 segundo)
  const pendingPropertyUpdatesRef = useRef<Map<string, Record<string, any>>>(new Map());
  const pendingMachineUpdatesRef = useRef<Map<string, Machine>>(new Map());
  const pendingTagUpdatesRef = useRef<Map<string, any>>(new Map());
  const flushPropertiesRef = useRef<() => void>(() => {});
  const flushMachinesRef = useRef<() => void>(() => {});
  const flushTagsRef = useRef<() => void>(() => {});
  const temporalHydratedRef = useRef<Set<string>>(new Set());

  useEffect(() => {
    const id = window.setInterval(() => {
      if (typeof document !== "undefined" && document.hidden) {
        return;
      }
      flushPropertiesRef.current();
      flushMachinesRef.current();
      flushTagsRef.current();
    }, 1000);
    return () => window.clearInterval(id);
  }, []);

  // Cargar m?quinas al montar el componente
  useEffect(() => {
    const loadMachines = async () => {
      setLoading(true);
      setError(null);
      try {
        const data = await getMachines();
        setMachines(data);
        
        // Intentar cargar el tab activo guardado en localStorage
        const savedActiveTab = localStorage.getItem(ACTIVE_TAB_STORAGE_KEY);
        
        // Verificar si el tab guardado existe en las m?quinas disponibles
        let tabToActivate: string | null = null;
        if (savedActiveTab && data.some((m) => m.name === savedActiveTab)) {
          tabToActivate = savedActiveTab;
        } else if (data.length > 0 && data[0].name) {
          // Si no hay tab guardado v?lido, usar el primero
          tabToActivate = data[0].name;
        }
        
        if (tabToActivate) {
          setActiveTab(tabToActivate);
          // Cargar la p?gina guardada para el tab activo
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

  // Cargar detalles de la m?quina cuando cambia el tab activo
  useEffect(() => {
    if (!activeTab) return;

    const loadMachineDetails = async () => {
      setLoadingDetails((prev) => ({ ...prev, [activeTab]: true }));
      try {
        const data = await getMachineByName(activeTab);
        setMachineDetails((prev) => ({ ...prev, [activeTab]: data }));
        if (data?.serialization?.has_domain_config) {
          try {
            const domain = await getMachineDomainConfig(activeTab);
            if (domain) {
              setDomainSchemas((prev) => ({ ...prev, [activeTab]: domain.schema || {} }));
              setDomainConfigs((prev) => ({ ...prev, [activeTab]: domain.config || {} }));
            }
          } catch (domainErr: any) {
            const payload = domainErr?.response?.data;
            const message =
              (typeof payload === "string" ? payload : undefined) ??
              payload?.message ??
              t("machines.domainConfigLoadError");
            showToast(message, "error");
          }
        }
        // Cargar la p?gina guardada o inicializar a 1 si no existe
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

  // Resetear dropdowns cuando cambia el tab (pero mantener la p?gina guardada)
  useEffect(() => {
    if (activeTab) {
      setSelectedSubscribedTag((prev) => ({ ...prev, [activeTab]: "" }));
      setSelectedReadOnlyVariable((prev) => ({ ...prev, [activeTab]: "" }));
      setSelectedInternalVariable((prev) => ({ ...prev, [activeTab]: "" }));
      // Cargar la p?gina guardada para este tab, o inicializar a 1 si no existe
      setCurrentPage((prev) => {
        if (!prev[activeTab]) {
          const savedPage = localStorage.getItem(getPageStorageKey(activeTab));
          const page = savedPage ? parseInt(savedPage, 10) : 1;
          return { ...prev, [activeTab]: page };
        }
        return prev;
      });
      // Nota: NO reseteamos valores de atributos aqu?.
      // Mantener los valores por m?quina evita el "flash" de placeholders al cambiar de tab.
    }
  }, [activeTab]);

  // Guardar la p?gina actual en localStorage cuando cambie
  useEffect(() => {
    Object.entries(currentPage).forEach(([machineName, page]) => {
      if (machineName && page) {
        localStorage.setItem(getPageStorageKey(machineName), String(page));
      }
    });
  }, [currentPage]);

  // Funci?n helper para mostrar modal de confirmaci?n de threshold
  const handleUpdateThreshold = (machineName: string) => {
    if (isAttributeLocked(machineName, "threshold")) return;

    const value = parseFloat(thresholdValue[machineName]);
    if (isNaN(value)) {
      showToast(t("machines.updateAttributeError"), "error");
      return;
    }

    // Solo mostrar modal si el valor cambi?
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

  // Funci?n para ejecutar la actualizaci?n de threshold despu?s de confirmar
  const executeUpdateThreshold = async (machineName: string, value: number) => {
    setUpdatingAttribute((prev) => ({ ...prev, [machineName]: "threshold" }));
    try {
      const { message } = await updateMachineAttributes(machineName, {
        threshold: value,
      });
      showToast(message || t("machines.updateAttribute"), "success");
      // Refrescar detalles de la m?quina
      const data = await getMachineByName(machineName);
      setMachineDetails((prev) => ({
        ...prev,
        [machineName]: data,
      }));
      // Actualizar el valor del input y el valor original
      const thresholdNum = extractActiveThreshold(data.serialization);
      if (thresholdNum !== null) {
        setThresholdValue((prev) => ({ ...prev, [machineName]: String(thresholdNum) }));
        setOriginalThresholdValue((prev) => ({ ...prev, [machineName]: thresholdNum }));
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

  const scanTimeSeconds = (scanTime: unknown): number => {
    const n = typeof scanTime === "number" ? scanTime : parseFloat(String(scanTime ?? ""));
    if (isNaN(n) || n <= 0) return 1;
    return n / 1000;
  };

  const handleSaveTemporalConfig = async (machineName: string) => {
    const details = machineDetails[machineName];
    const execution = parseFloat(executionIntervalValue[machineName] || "");
    if (isNaN(execution) || execution < 0.01) {
      showToast(t("machines.invalidInterval"), "error");
      return;
    }
    const customized = Boolean(customizeSampling[machineName]);
    let sample: number | null = null;
    if (customized) {
      sample = parseFloat(sampleIntervalValue[machineName] || "");
      if (isNaN(sample) || sample <= 0) {
        showToast(t("machines.invalidInterval"), "error");
        return;
      }
      if (execution < sample) {
        showToast(t("machines.invalidInterval"), "error");
        return;
      }
    }
    const overrides: Record<string, number | null> = {};
    let blocked = false;
    if (!customized) {
      Object.keys(details?.subscribed_tags || {}).forEach((tagName) => {
        overrides[tagName] = null;
      });
    } else {
      Object.entries(details?.subscribed_tags || {}).forEach(([tagName, payload]) => {
        const raw = sampleOverrideValue[machineName]?.[tagName];
        if (!raw) {
          overrides[tagName] = null;
          return;
        }
        const value = parseFloat(raw);
        const minScan = scanTimeSeconds(payload?.scan_time);
        if (isNaN(value) || value < minScan) {
          blocked = true;
          return;
        }
        overrides[tagName] = value;
      });
    }
    if (blocked) {
      showToast(t("machines.sampleFasterThanScan"), "error");
      return;
    }
    setSavingTemporal((prev) => ({ ...prev, [machineName]: true }));
    try {
      const { message } = await updateMachineAttributes(machineName, {
        execution_interval: execution,
        sample_interval: customized ? sample : null,
        sample_overrides: overrides,
      });
      showToast(message || t("machines.temporalUpdated"), "success");
      const data = await getMachineByName(machineName);
      temporalHydratedRef.current.delete(machineName);
      setMachineDetails((prev) => ({ ...prev, [machineName]: data }));
    } catch (err: any) {
      const data = err?.response?.data;
      const backendMessage =
        (typeof data === "string" ? data : undefined) ??
        data?.message ??
        data?.detail ??
        data?.error;
      showToast(backendMessage || err?.message || t("machines.updateAttributeError"), "error");
    } finally {
      setSavingTemporal((prev) => ({ ...prev, [machineName]: false }));
    }
  };

  const handleSignalModeChange = async (
    machineName: string,
    sourceName: string,
    mode: "raw" | "filtered"
  ) => {
    setSavingTemporal((prev) => ({ ...prev, [machineName]: true }));
    try {
      const { message } = await updateMachineAttributes(machineName, {
        signal_modes: { [sourceName]: mode },
      });
      showToast(message || t("machines.signalModeUpdated"), "success");
      const data = await getMachineByName(machineName);
      temporalHydratedRef.current.delete(machineName);
      setMachineDetails((prev) => ({ ...prev, [machineName]: data }));
    } catch (err: any) {
      const data = err?.response?.data;
      const backendMessage =
        (typeof data === "string" ? data : undefined) ??
        data?.message ??
        data?.detail ??
        data?.error;
      showToast(backendMessage || err?.message || t("machines.updateAttributeError"), "error");
    } finally {
      setSavingTemporal((prev) => ({ ...prev, [machineName]: false }));
    }
  };

  const handleResetTemporalConfig = async (machineName: string) => {
    const details = machineDetails[machineName];
    const execution = parseFloat(executionIntervalValue[machineName] || "");
    if (isNaN(execution) || execution < 0.01) {
      showToast(t("machines.invalidInterval"), "error");
      return;
    }
    const overrides: Record<string, number | null> = {};
    Object.keys(details?.subscribed_tags || {}).forEach((tagName) => {
      overrides[tagName] = null;
    });
    setCustomizeSampling((prev) => ({ ...prev, [machineName]: false }));
    setSampleIntervalValue((prev) => ({ ...prev, [machineName]: "" }));
    setSampleOverrideValue((prev) => ({ ...prev, [machineName]: {} }));
    setSavingTemporal((prev) => ({ ...prev, [machineName]: true }));
    try {
      const { message } = await updateMachineAttributes(machineName, {
        execution_interval: execution,
        sample_interval: null,
        sample_overrides: overrides,
      });
      showToast(message || t("machines.temporalReset"), "success");
      const data = await getMachineByName(machineName);
      temporalHydratedRef.current.delete(machineName);
      setMachineDetails((prev) => ({ ...prev, [machineName]: data }));
    } catch (err: any) {
      const data = err?.response?.data;
      const backendMessage =
        (typeof data === "string" ? data : undefined) ??
        data?.message ??
        data?.detail ??
        data?.error;
      showToast(backendMessage || err?.message || t("machines.updateAttributeError"), "error");
    } finally {
      setSavingTemporal((prev) => ({ ...prev, [machineName]: false }));
    }
  };

  // Funci?n helper para mostrar modal de confirmaci?n de buffer_size
  const handleUpdateBufferSize = (machineName: string) => {
    if (isAttributeLocked(machineName, "buffer_size")) return;

    const value = parseInt(bufferSizeValue[machineName], 10);
    if (isNaN(value)) {
      showToast(t("machines.updateAttributeError"), "error");
      return;
    }

    // Solo mostrar modal si el valor cambi?
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

  // Funci?n para ejecutar la actualizaci?n de buffer_size despu?s de confirmar
  const executeUpdateBufferSize = async (machineName: string, value: number) => {
    setUpdatingAttribute((prev) => ({ ...prev, [machineName]: "buffer_size" }));
    try {
      const { message } = await updateMachineAttributes(machineName, {
        buffer_size: value,
      });
      showToast(message || t("machines.updateAttribute"), "success");
      // Refrescar detalles de la m?quina
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

  // Funci?n helper para mostrar modal de confirmaci?n de on_delay
  const handleUpdateOnDelay = (machineName: string) => {
    if (isAttributeLocked(machineName, "on_delay")) return;

    const value = parseInt(onDelayValue[machineName], 10);
    if (isNaN(value)) {
      showToast(t("machines.updateAttributeError"), "error");
      return;
    }

    // Solo mostrar modal si el valor cambi?
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

  // Funci?n para ejecutar la actualizaci?n de on_delay despu?s de confirmar
  const executeUpdateOnDelay = async (machineName: string, value: number) => {
    setUpdatingAttribute((prev) => ({ ...prev, [machineName]: "on_delay" }));
    try {
      const { message } = await updateMachineAttributes(machineName, {
        on_delay: value,
      });
      showToast(message || t("machines.updateAttribute"), "success");
      // Refrescar detalles de la m?quina
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

  // Funci?n para confirmar y ejecutar la actualizaci?n
  const handleConfirmUpdate = async () => {
    if (!pendingUpdate) return;

    const { machineName, attribute, newValue } = pendingUpdate;

    if (attribute === "threshold") {
      await executeUpdateThreshold(machineName, Number(newValue));
    } else if (attribute === "buffer_size") {
      await executeUpdateBufferSize(machineName, Number(newValue));
    } else if (attribute === "on_delay") {
      await executeUpdateOnDelay(machineName, Number(newValue));
    }

    setShowConfirmModal(false);
    setPendingUpdate(null);
  };

  // Funci?n para cancelar la actualizaci?n
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

  // Inicializar valores de atributos cuando se cargan los detalles de la m?quina
  useEffect(() => {
    Object.entries(machineDetails).forEach(([machineName, details]) => {
      if (details && details.serialization) {
        const serialization = details.serialization;
        
        // Inicializar threshold
        const thresholdNum = extractActiveThreshold(serialization);
        if (thresholdNum !== null) {
          setThresholdValue((prev) => {
            if (prev[machineName] === undefined || prev[machineName] === "") {
              return { ...prev, [machineName]: String(thresholdNum) };
            }
            return prev;
          });
          setOriginalThresholdValue((prev) => ({ ...prev, [machineName]: thresholdNum }));
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

        const execution = serialization.execution_interval ?? serialization.machine_interval;
        if (execution !== null && execution !== undefined) {
          setExecutionIntervalValue((prev) => {
            if (prev[machineName] !== undefined && prev[machineName] !== "") {
              return prev;
            }
            return { ...prev, [machineName]: String(execution) };
          });
        }
        if (!temporalHydratedRef.current.has(machineName)) {
          const sample = serialization.sample_interval;
          const customized = sample !== null && sample !== undefined;
          setCustomizeSampling((prev) => ({
            ...prev,
            [machineName]: customized,
          }));
          if (customized) {
            setSampleIntervalValue((prev) => ({ ...prev, [machineName]: String(sample) }));
          }
          const overrides = serialization.sample_overrides || {};
          setSampleOverrideValue((prev) => ({
            ...prev,
            [machineName]: Object.fromEntries(
              Object.entries(overrides).map(([k, v]) => [k, String(v)])
            ),
          }));
          temporalHydratedRef.current.add(machineName);
        }
      }
    });
  }, [machineDetails]);

  // Suscripci?n a eventos de propiedades de m?quinas con buffering
  useEffect(() => {
    // Funci?n para aplicar las actualizaciones pendientes
    const flushUpdates = () => {
      if (pendingPropertyUpdatesRef.current.size === 0) {
        return;
      }

      // Aplicar todas las actualizaciones acumuladas
      setMachineDetails((prev) => {
        const updated = { ...prev };
        let hasUpdates = false;

        // Iterar sobre todas las actualizaciones pendientes
        pendingPropertyUpdatesRef.current.forEach((propertyUpdates, machineName) => {
          // Solo actualizar si tenemos datos de esta m?quina
          if (updated[machineName]) {
            hasUpdates = true;
            // Crear una copia profunda de los detalles actuales
            const currentDetails = { ...updated[machineName] };
            
            // Aplicar cada actualizaci?n de propiedad
            Object.entries(propertyUpdates).forEach(([propertyName, propertyValue]) => {
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
                } else {
                  // Es un valor simple, actualizar directamente
                  currentDetails.serialization = {
                    ...currentDetails.serialization,
                    [propertyName]: propertyValue,
                  };
                }
              }
              
              // 3. Actualizar en el nivel ra?z si existe
              if (propertyName in currentDetails) {
                currentDetails[propertyName] = propertyValue;
              }
            });

            updated[machineName] = currentDetails;
          }
        });

        // Limpiar el buffer despu?s de aplicar
        pendingPropertyUpdatesRef.current.clear();

        return hasUpdates ? updated : prev;
      });
    };

    flushPropertiesRef.current = flushUpdates;

    const cleanup = socketService.onMachinePropertyUpdate((data) => {
      // data format: { machineName: { propertyName: propertyValue } }
      
      Object.entries(data).forEach(([machineName, propertyUpdates]) => {
        // Usar una funci?n de actualizaci?n para acceder al estado actual sin depender de ?l
        setMachineDetails((prev) => {
          // Solo procesar si esta m?quina est? en nuestros detalles cargados
          if (prev[machineName]) {
            // Obtener o crear el buffer para esta m?quina
            const existingUpdates = pendingPropertyUpdatesRef.current.get(machineName) || {};
            
            // Fusionar las nuevas actualizaciones con las existentes
            const mergedUpdates = {
              ...existingUpdates,
              ...propertyUpdates,
            };
            
            // Guardar en el buffer (sobrescribe si ya existe)
            pendingPropertyUpdatesRef.current.set(machineName, mergedUpdates);
          }
          // No cambiar el estado aqu?, solo actualizar el buffer
          return prev;
        });
      });
    });

    // Cleanup al desmontar
    return () => {
      cleanup();
      flushUpdates();
      pendingPropertyUpdatesRef.current.clear();
    };
  }, []); // Sin dependencias - se suscribe una sola vez

  // Suscripci?n a eventos completos de m?quinas con buffering (para actualizar state y otros atributos)
  useEffect(() => {
    // Funci?n para aplicar las actualizaciones pendientes de m?quinas
    const flushMachineUpdates = () => {
      if (pendingMachineUpdatesRef.current.size === 0) {
        return;
      }

      // Aplicar todas las actualizaciones acumuladas
      setMachineDetails((prev) => {
        const updated = { ...prev };
        let hasUpdates = false;

        // Iterar sobre todas las actualizaciones pendientes
        pendingMachineUpdatesRef.current.forEach((updatedMachine, machineName) => {
          // Solo actualizar si tenemos datos de esta m?quina
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
            }
            
            updated[machineName] = currentDetails;
          }
        });

        // Limpiar el buffer despu?s de aplicar
        pendingMachineUpdatesRef.current.clear();

        return hasUpdates ? updated : prev;
      });
    };

    flushMachinesRef.current = flushMachineUpdates;

    const cleanup = socketService.onMachineUpdate((machine: Machine) => {
      // machine es un objeto Machine completo con toda la informaci?n
      
      if (machine.name) {
        // Usar una funci?n de actualizaci?n para acceder al estado actual sin depender de ?l
        setMachineDetails((prev) => {
          // Solo procesar si esta m?quina est? en nuestros detalles cargados
          if (prev[machine.name]) {
            // Guardar en el buffer (sobrescribe si ya existe)
            pendingMachineUpdatesRef.current.set(machine.name, machine);
          }
          // No cambiar el estado aqu?, solo actualizar el buffer
          return prev;
        });
      }
    });

    // Cleanup al desmontar
    return () => {
      cleanup();
      flushMachineUpdates();
      pendingMachineUpdatesRef.current.clear();
    };
  }, []); // Sin dependencias - se suscribe una sola vez

  // Suscripci?n a eventos de tags con buffering (para actualizar process_variables asociados)
  useEffect(() => {
    // Funci?n para aplicar las actualizaciones pendientes de tags
    const flushTagUpdates = () => {
      if (pendingTagUpdatesRef.current.size === 0) {
        return;
      }

      // Aplicar todas las actualizaciones acumuladas
      setMachineDetails((prev) => {
        const updated = { ...prev };
        let hasUpdates = false;

        // Iterar sobre todas las actualizaciones pendientes de tags
        pendingTagUpdatesRef.current.forEach((updatedTag, tagId) => {
          // Buscar en todas las m?quinas si alg?n process_variable tiene este tag asociado
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

                  // Tambi?n actualizar el value del process_variable si el tag tiene value
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
                }
              }
            });

            // Tambi?n buscar en subscribed_tags, not_subscribed_tags, etc.
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

        // Limpiar el buffer despu?s de aplicar
        pendingTagUpdatesRef.current.clear();

        return hasUpdates ? updated : prev;
      });
    };

    flushTagsRef.current = flushTagUpdates;

    const cleanup = socketService.onTagUpdate((tag: Tag) => {
      // tag es un objeto Tag completo con toda la informaci?n

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
      flushTagUpdates();
      pendingTagUpdatesRef.current.clear();
    };
  }, []); // Sin dependencias - se suscribe una sola vez

  // Obtener los nombres ?nicos de las m?quinas
  const machineNames = machines
    .map((machine) => machine.name)
    .filter((name): name is string => !!name);

  // Funci?n para obtener atributos a mostrar en la tabla (excluyendo los especificados)
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
    
    // 2. Recopilar atributos de primer nivel de serialization (solo los que NO est?n en process_variables)
    if (data.serialization && typeof data.serialization === "object" && data.serialization !== null) {
      Object.entries(data.serialization).forEach(([subKey, subValue]) => {
        // Omitir si est? en excludedKeys, es "actions", o si ya est? en process_variables
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
    
    // 3. Recopilar otros atributos del nivel ra?z (solo los que NO est?n en process_variables)
    Object.entries(data).forEach(([key, value]) => {
      if (!excludedKeys.includes(key) && !processVariables.has(key) && key !== "process_variables" && key !== "serialization") {
        firstLevelAttributes.set(key, value);
      }
    });
    
    // 4. Agregar atributos en el orden correcto:
    // Primero los de prioridad que NO est?n en process_variables
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
    
    // Finalmente, el resto de atributos de primer nivel (ordenados alfab?ticamente)
    const remainingFirstLevel = Array.from(firstLevelAttributes.entries()).sort((a, b) => a[0].localeCompare(b[0]));
    remainingFirstLevel.forEach(([key, value]) => {
      attributes.push([key, value]);
      processedKeys.add(key);
    });

    return attributes;
  };

  // Funci?n para obtener la clase del badge seg?n el estado
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

  // Funci?n para verificar si un estado debe tener efecto blinking
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

  // Funci?n para obtener el estilo del badge seg?n el valor num?rico (1-5)
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

  // Funci?n para formatear el valor de un atributo
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
    
    // Si es el atributo "priority" o "criticity", mostrar como badge num?rico
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
      // Si no es un n?mero v?lido, mostrar como texto normal
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

  // Funci?n para obtener atributos paginados por m?quina
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
                const details = machineDetails[machineName];
                const hints = uiHintsFor(machineName);
                const notSubscribedKeys = details
                  ? getNotSubscribedTagKeys(details, hints.exclusive_subscribe_pairs || [])
                  : [];
                const thresholdUnit = getThresholdUnitLabel(details, hints, t);
                const isBufferSizeLocked = isAttributeLocked(machineName, "buffer_size");
                const isThresholdLocked = isAttributeLocked(machineName, "threshold");
                const isOnDelayLocked = isAttributeLocked(machineName, "on_delay");
                const showGenericCard =
                  hints.show_generic_attributes_card !== false &&
                  hasGenericAttributes(details);
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
                      <>
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
                                      // Necesitamos encontrar qu? variable interna tiene ese tag asociado
                                      // En read_only_process_type_variables, la clave es el nombre de la variable interna
                                      // y varData.tag.name es el field tag
                                      let internalTagName = "";
                                      
                                      // Normalizar el fieldTag para comparaci?n (sin espacios, en min?sculas)
                                      const normalizedFieldTag = String(fieldTag).trim();
                                      
                                      // Buscar en read_only_process_type_variables (donde est?n las variables internas suscritas)
                                      const readOnlyVars = machineDetails[machineName].read_only_process_type_variables || {};
                                      for (const [varName, varData] of Object.entries(readOnlyVars)) {
                                        if (varData && typeof varData === "object" && varData.tag && typeof varData.tag === "object" && varData.tag.name) {
                                          // tag.name may be "MACHINE.fieldTag" or just "fieldTag"
                                          const tagName = String(varData.tag.name).trim();
                                          // Extraer solo la parte del field tag (despu?s del punto si existe)
                                          const tagNameParts = tagName.split(".");
                                          const tagNameWithoutMachine = tagNameParts.length > 1 ? tagNameParts[tagNameParts.length - 1] : tagName;
                                          
                                          // Comparar: el fieldTag debe coincidir con el tagName (con o sin prefijo de m?quina)
                                          // varName es el nombre de la variable interna (ej: "outlet_pressure")
                                          if (tagName === normalizedFieldTag || tagNameWithoutMachine === normalizedFieldTag) {
                                            internalTagName = varName; // Usar varName, no tagName
                                            break;
                                          }
                                        }
                                      }
                                      
                                      // Si no se encontr? en read_only, buscar en process_variables
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
                                        ? `${fieldTag} ??? ${internalTagName}`
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
                                      {getAvailableFieldTags(machineDetails[machineName]).map((tagName) => (
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
                                      value={
                                        notSubscribedKeys.includes(selectedInternalVariable[machineName] || "")
                                          ? selectedInternalVariable[machineName]
                                          : ""
                                      }
                                      onChange={(e) => setSelectedInternalVariable((prev) => ({ ...prev, [machineName]: e.target.value }))}
                                    >
                                      <option value="">{t("machines.select")}</option>
                                      {notSubscribedKeys.map((key) => (
                                        <option key={key} value={key}>
                                          {key}
                                        </option>
                                      ))}
                                    </select>
                                  </div>
                                </div>

                                {hints.subscribe_hints?.[selectedInternalVariable[machineName] || ""] ? (
                                  <div className="alert alert-info py-2 small mb-3" role="status">
                                    {hints.subscribe_hints[selectedInternalVariable[machineName] || ""]}
                                  </div>
                                ) : null}

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
                                          const { message, hint, hint_level } = await subscribeMachineTag(
                                            machineName,
                                            fieldTag,
                                            internalTag
                                          );
                                          showToast(
                                            message || t("machines.subscribe"),
                                            "success"
                                          );
                                          if (hint) {
                                            const level =
                                              hint_level === "warning" || hint_level === "error"
                                                ? hint_level
                                                : "info";
                                            showToast(hint, level, 8000);
                                          }
                                          // Refrescar detalles de la m?quina
                                          const data = await getMachineByName(machineName);
                                          setMachineDetails((prev) => ({
                                            ...prev,
                                            [machineName]: data,
                                          }));
                                          await refreshDomainConfig(machineName, data);
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
                                          // Refrescar: el field tag vuelve a "Tags de Campo"
                                          // y la variable interna a "Tags No Suscritos".
                                          const data = await getMachineByName(
                                            machineName
                                          );
                                          setMachineDetails((prev) => ({
                                            ...prev,
                                            [machineName]: data,
                                          }));
                                          await refreshDomainConfig(machineName, data);
                                          setSelectedSubscribedTag((prev) => ({
                                            ...prev,
                                            [machineName]: "",
                                          }));
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
                          
                          {/* Generic machine attributes */}
                          {showGenericCard && (
                            <Card title={t("machines.machineAttributes")} className="mt-3">
                              <div>
                                <div className="mb-3 d-flex align-items-center gap-2 flex-wrap">
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
                                      if (isThresholdLocked) return;
                                      if (e.key === "Enter") {
                                        e.preventDefault();
                                        handleUpdateThreshold(machineName);
                                      }
                                    }}
                                    onBlur={() => {
                                      if (isThresholdLocked) return;
                                      if (thresholdValue[machineName] && thresholdValue[machineName] !== "") {
                                        handleUpdateThreshold(machineName);
                                      }
                                    }}
                                    disabled={updatingAttribute[machineName] === "threshold" || isThresholdLocked}
                                  />
                                  {thresholdUnit.label && (
                                    <span className="text-muted small" title={thresholdUnit.hint || undefined}>
                                      {thresholdUnit.label}
                                    </span>
                                  )}
                                  {updatingAttribute[machineName] === "threshold" && (
                                    <div className="spinner-border spinner-border-sm text-primary" role="status">
                                      <span className="visually-hidden">{t("common.loading")}</span>
                                    </div>
                                  )}
                                </div>

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
                                      if (isOnDelayLocked) return;
                                      if (e.key === "Enter") {
                                        e.preventDefault();
                                        handleUpdateOnDelay(machineName);
                                      }
                                    }}
                                    onBlur={() => {
                                      if (isOnDelayLocked) return;
                                      if (onDelayValue[machineName] && onDelayValue[machineName] !== "") {
                                        handleUpdateOnDelay(machineName);
                                      }
                                    }}
                                    disabled={updatingAttribute[machineName] === "on_delay" || isOnDelayLocked}
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
                      {machineDetails[machineName] && (
                        <div className="row mt-3">
                          <div className="col-12">
                            {(() => {
                              const customized = Boolean(customizeSampling[machineName]);
                              const execRaw = executionIntervalValue[machineName] || "";
                              const execNum = parseFloat(execRaw);
                              const globalSampleRaw = sampleIntervalValue[machineName] || "";
                              const globalSampleNum = parseFloat(globalSampleRaw);
                              const subscribed = Object.entries(
                                machineDetails[machineName].subscribed_tags || {}
                              );
                              const overrideInvalid = subscribed.some(([tagName, payload]) => {
                                const raw = sampleOverrideValue[machineName]?.[tagName] || "";
                                if (!raw) return false;
                                const value = parseFloat(raw);
                                return isNaN(value) || value < scanTimeSeconds(payload?.scan_time);
                              });
                              return (
                            <Card
                              className="timing-config-card"
                              title={
                                <div className="d-flex flex-wrap align-items-center justify-content-between gap-2 w-100">
                                  <h3 className="card-title mb-0">{t("machines.timingCardTitle")}</h3>
                                  <span
                                    className={`badge rounded-pill ${
                                      customized ? "text-bg-primary" : "text-bg-secondary"
                                    }`}
                                  >
                                    {customized
                                      ? t("machines.samplingCustomBadge")
                                      : t("machines.samplingDefaultBadge")}
                                  </span>
                                </div>
                              }
                            >
                              <div className="row g-3">
                                <div className="col-lg-4">
                                  <div className="timing-config-panel h-100">
                                    <label className="form-label" htmlFor={`execution-interval-${machineName}`}>
                                      {t("machines.executionInterval")}
                                    </label>
                                    <div className="input-group">
                                      <input
                                        id={`execution-interval-${machineName}`}
                                        type="number"
                                        min={0.01}
                                        step={0.01}
                                        className="form-control"
                                        value={execRaw}
                                        onChange={(e) =>
                                          setExecutionIntervalValue((prev) => ({
                                            ...prev,
                                            [machineName]: e.target.value,
                                          }))
                                        }
                                      />
                                      <span className="input-group-text">s</span>
                                    </div>
                                    <p className="text-muted small mb-0 mt-2">
                                      {t("machines.executionIntervalHelp")}
                                    </p>
                                  </div>
                                </div>
                                <div className="col-lg-8">
                                  <div className="timing-config-panel h-100">
                                    <label
                                      className="form-label"
                                      htmlFor={`sample-interval-${machineName}`}
                                    >
                                      {t("machines.samplingGlobalTitle")}
                                    </label>
                                    <div className="timing-sample-row">
                                      <div className="input-group timing-sample-input">
                                        <input
                                          id={`sample-interval-${machineName}`}
                                          type="number"
                                          min={0.01}
                                          step={0.01}
                                          className="form-control"
                                          value={customized ? globalSampleRaw : execRaw}
                                          disabled={!customized}
                                          onChange={(e) =>
                                            setSampleIntervalValue((prev) => ({
                                              ...prev,
                                              [machineName]: e.target.value,
                                            }))
                                          }
                                        />
                                        <span className="input-group-text">s</span>
                                      </div>
                                      <div className="form-check form-switch mb-0">
                                        <input
                                          className="form-check-input"
                                          type="checkbox"
                                          role="switch"
                                          id={`customize-sampling-${machineName}`}
                                          checked={customized}
                                          onChange={(e) => {
                                            const checked = e.target.checked;
                                            setCustomizeSampling((prev) => ({
                                              ...prev,
                                              [machineName]: checked,
                                            }));
                                            if (checked && !sampleIntervalValue[machineName]) {
                                              setSampleIntervalValue((prev) => ({
                                                ...prev,
                                                [machineName]: execRaw || "0.2",
                                              }));
                                            }
                                          }}
                                        />
                                        <label
                                          className="form-check-label"
                                          htmlFor={`customize-sampling-${machineName}`}
                                        >
                                          {t("machines.customizeSampling")}
                                        </label>
                                      </div>
                                    </div>
                                    <p className="text-muted small mb-0 mt-2">
                                      {customized
                                        ? t("machines.samplingGlobalHint")
                                        : t("machines.samplingDefaultHint")}
                                    </p>
                                  </div>
                                </div>
                              </div>

                              {subscribed.length > 0 && (
                                <div className="mt-4">
                                  <div className="d-flex flex-wrap align-items-baseline justify-content-between gap-2 mb-2">
                                    <h6 className="mb-0">{t("machines.samplingPerTagTitle")}</h6>
                                    <span className="text-muted small">
                                      {customized
                                        ? t("machines.samplingPerTagHint")
                                        : t("machines.samplingPerTagLegacyHint")}
                                    </span>
                                  </div>
                                  <div className="table-responsive">
                                    <table className="table table-sm align-middle timing-config-table mb-0">
                                      <thead>
                                        <tr>
                                          <th>{t("machines.subscribedTags")}</th>
                                          <th>{t("machines.signalMode")}</th>
                                          <th>{t("machines.scanTime")}</th>
                                          {customized && <th>{t("machines.sampleOverride")}</th>}
                                          <th>{t("machines.samplingEffective")}</th>
                                        </tr>
                                      </thead>
                                      <tbody>
                                        {subscribed.map(([tagName, payload]) => {
                                          const scanS = scanTimeSeconds(payload?.scan_time);
                                          const overrideRaw =
                                            sampleOverrideValue[machineName]?.[tagName] || "";
                                          const overrideNum = parseFloat(overrideRaw);
                                          const invalid =
                                            customized &&
                                            overrideRaw !== "" &&
                                            (isNaN(overrideNum) || overrideNum < scanS);
                                          let effectiveLabel = t("machines.samplingUsesExecution");
                                          let effectiveValue = !isNaN(execNum) ? `${execNum} s` : "?";
                                          if (customized) {
                                            if (overrideRaw && !isNaN(overrideNum)) {
                                              effectiveLabel = t("machines.samplingUsesOverride");
                                              effectiveValue = `${overrideNum} s`;
                                            } else if (!isNaN(globalSampleNum)) {
                                              effectiveLabel = t("machines.samplingUsesGlobal");
                                              effectiveValue = `${globalSampleNum} s`;
                                            } else {
                                              effectiveValue = "?";
                                              effectiveLabel = t("machines.samplingUsesGlobal");
                                            }
                                          }
                                          const sourceName =
                                            (typeof payload?.source_name === "string" &&
                                              payload.source_name) ||
                                            tagName.replace(/\.f$/, "");
                                          const filterEnabled = Boolean(payload?.filter_enabled);
                                          const signalMode =
                                            payload?.signal_mode === "raw" ? "raw" : "filtered";
                                          return (
                                            <tr key={tagName}>
                                              <td>
                                                <code className="timing-tag-name">{sourceName}</code>
                                              </td>
                                              <td style={{ minWidth: "8rem" }}>
                                                {filterEnabled ? (
                                                  <select
                                                    className="form-select form-select-sm"
                                                    value={signalMode}
                                                    disabled={Boolean(savingTemporal[machineName])}
                                                    onChange={(e) =>
                                                      handleSignalModeChange(
                                                        machineName,
                                                        sourceName,
                                                        e.target.value as "raw" | "filtered"
                                                      )
                                                    }
                                                    title={t("machines.signalModeHint")}
                                                  >
                                                    <option value="filtered">
                                                      {t("machines.signalModeFiltered")}
                                                    </option>
                                                    <option value="raw">
                                                      {t("machines.signalModeRaw")}
                                                    </option>
                                                  </select>
                                                ) : (
                                                  <span className="text-muted small">
                                                    {t("machines.signalModeRaw")}
                                                  </span>
                                                )}
                                              </td>
                                              <td className="text-nowrap">
                                                {payload?.scan_time ?? "?"} ms
                                                <span className="text-muted"> ({scanS} s)</span>
                                              </td>
                                              {customized && (
                                                <td style={{ minWidth: "9rem", maxWidth: "12rem" }}>
                                                  <input
                                                    type="number"
                                                    min={scanS}
                                                    step={0.01}
                                                    placeholder={
                                                      !isNaN(globalSampleNum)
                                                        ? String(globalSampleNum)
                                                        : t("machines.samplingOverridePlaceholder")
                                                    }
                                                    className={`form-control form-control-sm ${
                                                      invalid ? "is-invalid" : ""
                                                    }`}
                                                    value={overrideRaw}
                                                    title={
                                                      invalid
                                                        ? t("machines.sampleFasterThanScan")
                                                        : t("machines.samplingOverridePlaceholder")
                                                    }
                                                    onChange={(e) =>
                                                      setSampleOverrideValue((prev) => ({
                                                        ...prev,
                                                        [machineName]: {
                                                          ...(prev[machineName] || {}),
                                                          [tagName]: e.target.value,
                                                        },
                                                      }))
                                                    }
                                                  />
                                                </td>
                                              )}
                                              <td>
                                                <span className="fw-medium">{effectiveValue}</span>
                                                <span className="text-muted small ms-1">
                                                  ({effectiveLabel})
                                                </span>
                                              </td>
                                            </tr>
                                          );
                                        })}
                                      </tbody>
                                    </table>
                                  </div>
                                </div>
                              )}

                              <div className="d-flex flex-wrap justify-content-between gap-2 mt-3">
                                <Button
                                  variant="secondary"
                                  onClick={() => handleResetTemporalConfig(machineName)}
                                  disabled={Boolean(savingTemporal[machineName])}
                                >
                                  {t("machines.resetTemporalConfig")}
                                </Button>
                                <Button
                                  onClick={() => handleSaveTemporalConfig(machineName)}
                                  disabled={Boolean(savingTemporal[machineName]) || overrideInvalid}
                                >
                                  {savingTemporal[machineName]
                                    ? t("machines.updating")
                                    : t("machines.saveTemporalConfig")}
                                </Button>
                              </div>
                            </Card>
                              );
                            })()}
                          </div>
                        </div>
                      )}
                      {domainSchemas[machineName] && (
                        <div className="row mt-3">
                          <div className="col-12">
                            <DomainConfigSlot
                              machineName={machineName}
                              schema={domainSchemas[machineName]}
                              config={domainConfigs[machineName] || {}}
                              machineState={String(
                                machineDetails[machineName]?.serialization?.state || ""
                              )}
                              onConfigUpdated={(next) =>
                                setDomainConfigs((prev) => ({ ...prev, [machineName]: next }))
                              }
                              onSchemaUpdated={(next) =>
                                setDomainSchemas((prev) => ({ ...prev, [machineName]: next }))
                              }
                            />
                          </div>
                        </div>
                      )}
                      </>
                    )}
                  </div>
                );
              })}
            </div>
          </>
        )}

        {/* Modal de confirmaci?n de actualizaci?n de atributo */}
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

