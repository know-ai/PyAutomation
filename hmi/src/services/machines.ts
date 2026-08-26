import api from "./api";

export type Machine = {
  state: string;
  actions: string[];
  manufacturer: string | null;
  segment: string | null;
  identifier: string;
  criticity: number;
  priority: number;
  description: string;
  classification: string;
  name: string;
  machine_interval: number;
  execution_interval?: number;
  sample_interval?: number | null;
  sample_overrides?: Record<string, number>;
  signal_modes?: Record<string, "raw" | "filtered">;
  buffer_size: number;
  buffer_roll_type: string;
  has_domain_config?: boolean;
  [key: string]: any;
};

export type MachinesResponse = {
  data: Machine[];
};

/**
 * Obtiene todas las máquinas de estado
 */
export const getMachines = async (): Promise<Machine[]> => {
  const { data } = await api.get("/machines/");
  return data?.data ?? [];
};

/**
 * Obtiene información detallada de una máquina por nombre
 */
export const getMachineByName = async (machineName: string): Promise<any> => {
  const { data } = await api.get(`/machines/${encodeURIComponent(machineName)}`);
  return data?.data;
};

/**
 * Actualiza el intervalo de ejecución de una máquina
 */
export const updateMachineInterval = async (
  machineName: string,
  interval: number
): Promise<{ message: string; data: Machine }> => {
  const { data } = await api.put(`/machines/${encodeURIComponent(machineName)}`, {
    interval,
  });
  return data;
};

/**
 * Ejecuta una transición de estado en una máquina
 */
export const transitionMachine = async (
  machineName: string,
  to: string
): Promise<{ message: string; data: Machine }> => {
  const { data } = await api.put(`/machines/${encodeURIComponent(machineName)}/transition`, {
    to,
  });
  return data;
};

/**
 * Suscribe un tag de campo a una variable interna de la máquina
 */
export const subscribeMachineTag = async (
  machineName: string,
  fieldTag: string,
  internalTag: string
): Promise<{ message: string; data: Machine }> => {
  const { data } = await api.post(
    `/machines/${encodeURIComponent(machineName)}/subscribe`,
    {
      field_tag: fieldTag,
      internal_tag: internalTag,
    }
  );
  return data;
};

/**
 * Desuscribe un tag previamente suscrito de la máquina
 */
export const unsubscribeMachineTag = async (
  machineName: string,
  tagName: string
): Promise<{ message: string; data: Machine }> => {
  const { data } = await api.post(
    `/machines/${encodeURIComponent(machineName)}/unsubscribe`,
    {
      tag_name: tagName,
    }
  );
  return data;
};

/**
 * Actualiza atributos genéricos de una máquina (threshold, buffer_size, on_delay, timings)
 */
export const updateMachineAttributes = async (
  machineName: string,
  attributes: {
    threshold?: number;
    interval?: number;
    execution_interval?: number;
    sample_interval?: number | null;
    sample_overrides?: Record<string, number | null>;
    signal_modes?: Record<string, "raw" | "filtered">;
    buffer_size?: number;
    on_delay?: number;
  }
): Promise<{ message: string; data: Machine }> => {
  const { data } = await api.put(
    `/machines/${encodeURIComponent(machineName)}/attributes`,
    attributes
  );
  return data;
};

export type DomainLabelDisplay = "visible" | "hidden";
export type DomainHelpDisplay = "tooltip" | "text" | "both" | "none";

export type DomainConfigField = {
  key: string;
  type: "number" | "select" | "boolean" | "string" | "object" | "array" | string;
  label?: string;
  unit?: string;
  min?: number;
  max?: number;
  step?: number;
  options?: Array<{ value: string; label: string }>;
  depends_on?: { field: string; equals?: unknown };
  help?: string;
  read_only?: boolean;
  read_only_when?: { field: string; equals?: unknown };
  short_label?: string;
  false_label?: string;
  true_label?: string;
  show_label?: boolean;
  label_display?: DomainLabelDisplay;
  help_display?: DomainHelpDisplay;
  fields?: DomainConfigField[];
  columns?: number;
  dwt_bounds?: {
    role?: "level" | "length";
    family_key?: string;
    length_key?: string;
    level_key?: string;
    filter_len?: Record<string, number>;
    cap?: number;
    min_length?: number;
    apply_min_when?: { field: string; equals?: unknown };
    apply_max_when?: { field: string; equals?: unknown };
  };
};

export type DomainConfigSection = {
  id?: string;
  label?: string;
  hint?: string;
  fields?: DomainConfigField[];
  depends_on?: { field: string; equals?: unknown };
  label_display?: DomainLabelDisplay;
  help_display?: DomainHelpDisplay;
};

export type DomainUiHints = {
  exclusive_subscribe_pairs?: string[][];
  lock_generic_attributes?: string[];
  threshold_unit?: string;
  show_generic_attributes_card?: boolean;
  factory_defaults?: Record<string, unknown>;
  label_display?: DomainLabelDisplay;
  help_display?: DomainHelpDisplay;
  show_labels?: boolean;
  show_set_factory?: boolean;
};

export type DomainUiSchema = {
  version?: number;
  title?: string;
  sections?: DomainConfigSection[];
  ui_hints?: DomainUiHints;
};

export type MachineDomainConfigResponse = {
  schema: DomainUiSchema;
  config: Record<string, unknown>;
};

export const getMachineDomainConfig = async (
  machineName: string
): Promise<MachineDomainConfigResponse | null> => {
  try {
    const { data } = await api.get(
      `/machines/${encodeURIComponent(machineName)}/domain-config`
    );
    return data;
  } catch (err: any) {
    if (err?.response?.status === 404) return null;
    throw err;
  }
};

export const putMachineDomainConfig = async (
  machineName: string,
  payload: Record<string, unknown>
): Promise<{ status: string; config: Record<string, unknown> }> => {
  const { data } = await api.put(
    `/machines/${encodeURIComponent(machineName)}/domain-config`,
    payload
  );
  return data;
};

