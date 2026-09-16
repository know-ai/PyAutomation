import type { AxiosRequestConfig } from "axios";
import api from "./api";

export type Alarm = {
  identifier?: string;
  id?: string | number;
  name: string;
  tag: string;
  alarm_type?: string;
  trigger_value?: number | boolean;
  description?: string;
  display_name?: string;
  state?: {
    mnemonic?: string;
    state?: string;
    process_condition?: string;
    alarm_status?: string;
    annunciate_status?: string;
    acknowledge_status?: string;
  } | string;
  timestamp?: string;
  last_transition_ts?: string | null;
  last_transition_from?: string | null;
  last_transition_to?: string | null;
  ack_timestamp?: string;
  segment?: string;
  manufacturer?: string;
  alarm_setpoint?: {
    type?: string;
    value?: number | boolean;
  };
  actions?: {
    [key: string]: string;
  };
  on_delay?: number;
  off_delay?: number;
  on_delay_units?: string;
  off_delay_units?: string;
  condition_met?: boolean;
  on_timer_remaining?: number | null;
  off_timer_remaining?: number | null;
  delay_phase?: "pending" | "clearing" | null;
  priority?: number;
  latching?: boolean;
  ack_required?: boolean;
  chattering?: boolean;
  [key: string]: any;
};

export type AlarmsResponse = {
  data: Alarm[];
  pagination: {
    page: number;
    limit: number;
    total: number;
    pages: number;
  };
};

export type AlarmsListFilter = {
  q?: string;
  state?: string;
};

export const CATALOG_PAGE_SIZE_MAX = 50;
export const HISTORY_PAGE_SIZE_MAX = 100;

export type AlarmsFooterResponse = {
  top_3_active: Alarm[];
  count_by_state: Record<string, number>;
};

/**
 * Obtiene la lista de alarmas con paginación
 */
export const getAlarms = async (
  page: number = 1,
  limit: number = 20,
  filters: AlarmsListFilter = {}
): Promise<AlarmsResponse> => {
  const pageSize = Math.min(Math.max(1, limit), CATALOG_PAGE_SIZE_MAX);
  const params: Record<string, string | number> = { page, limit: pageSize, page_size: pageSize };
  const query = filters.q?.trim();
  const state = filters.state?.trim();
  if (query) params.q = query;
  if (state) params.state = state;
  const { data } = await api.get("/alarms/", { params });
  return data;
};

export const getAlarmsFooter = async (): Promise<AlarmsFooterResponse> => {
  const { data } = await api.get("/alarms/footer");
  return data;
};

export async function collectAlarmsPages(
  filters: AlarmsListFilter = {},
  pageSize: number = CATALOG_PAGE_SIZE_MAX
): Promise<Alarm[]> {
  const size = Math.min(pageSize, CATALOG_PAGE_SIZE_MAX);
  const all: Alarm[] = [];
  for (let page = 1; page <= 200; page += 1) {
    const response = await getAlarms(page, size, filters);
    const items = response.data || [];
    all.push(...items);
    if (items.length < size) break;
  }
  return all;
}

/**
 * Crea una nueva alarma
 */
export const createAlarm = async (alarm: Partial<Alarm>): Promise<any> => {
  const { data } = await api.post("/alarms/add", alarm);
  return data;
};

/**
 * Actualiza una alarma existente
 */
export const updateAlarm = async (alarm: Partial<Alarm> & { id: string | number }): Promise<any> => {
  const { data } = await api.post("/alarms/update", alarm);
  return data;
};

/**
 * Elimina una alarma por ID
 */
export const deleteAlarm = async (alarmId: string | number): Promise<any> => {
  const { data } = await api.delete(`/alarms/delete/${encodeURIComponent(alarmId)}`);
  return data;
};

/**
 * Obtiene una alarma por ID
 */
export const getAlarmById = async (alarmId: string | number): Promise<Alarm> => {
  const { data } = await api.get(`/alarms/${encodeURIComponent(alarmId)}`);
  return data;
};

/**
 * Obtiene una alarma por nombre
 */
export const getAlarmByName = async (alarmName: string): Promise<Alarm> => {
  const { data } = await api.get(`/alarms/name/${encodeURIComponent(alarmName)}`);
  return data;
};

export type AlarmSummary = {
  id?: string | number;
  identifier?: string;
  name: string;
  tag: string;
  description?: string;
  alarm_type?: string;
  trigger_value?: number | boolean | null;
  state: string;
  mnemonic?: string;
  status?: string;
  condition?: string;
  segment?: string | null;
  manufacturer?: string | null;
  area?: string | null;
  alarm_time: string;
  ack_time?: string | null;
  from_state?: string | null;
  to_state?: string | null;
  event_time?: string | null;
  operator_id?: number | null;
  schema_version?: number | null;
  has_comments?: boolean;
};

export type AlarmSummaryFilter = {
  names?: string[];
  states?: string[];
  tags?: string[];
  /** Case-insensitive partial match on alarm name or description */
  q?: string;
  greater_than_timestamp?: string;
  less_than_timestamp?: string;
  timezone?: string;
  page?: number;
  limit?: number;
  area?: string;
};

export type AlarmSummaryResponse = {
  data: AlarmSummary[];
  pagination: {
    page: number;
    limit: number;
    total_records: number;
    total_pages: number;
    has_next: boolean;
    has_prev: boolean;
  };
};

/**
 * Filtra el histórico de alarmas según los criterios proporcionados
 */
export const filterAlarmsSummary = async (
  filters: AlarmSummaryFilter,
  config?: AxiosRequestConfig
): Promise<AlarmSummaryResponse> => {
  const payload = {
    ...filters,
    limit: Math.min(Math.max(1, Number(filters.limit || 20)), HISTORY_PAGE_SIZE_MAX),
  };
  const { data } = await api.post("/alarms/summary/filter_by", payload, config);
  return data;
};

/**
 * Reconoce una alarma por su nombre
 */
export const acknowledgeAlarm = async (alarmName: string): Promise<any> => {
  const { data } = await api.post(`/alarms/acknowledge/${encodeURIComponent(alarmName)}`);
  return data;
};

/**
 * Reconoce todas las alarmas activas
 */
export const acknowledgeAllAlarms = async (): Promise<any> => {
  const { data } = await api.post("/alarms/acknowledge_all");
  return data;
};

/**
 * Ejecuta una acción en una alarma
 */
export const executeAlarmAction = async (
  actionValue: string,
  alarmName: string
): Promise<any> => {
  const { data } = await api.post(`/alarms/${encodeURIComponent(actionValue)}/${encodeURIComponent(alarmName)}`);
  return data;
};

/**
 * Obtiene los comentarios de un resumen de alarma
 */
export const getAlarmSummaryComments = async (id: number): Promise<any[]> => {
  const { data } = await api.get(`/alarms/summary/${id}/comments`);
  return data;
};

/**
 * Shelve una alarma con duración específica
 */
export const shelveAlarm = async (
  alarmName: string,
  duration: {
    seconds?: number;
    minutes?: number;
    hours?: number;
    days?: number;
    weeks?: number;
  }
): Promise<any> => {
  const { data } = await api.post(`/alarms/shelve/${encodeURIComponent(alarmName)}`, duration);
  return data;
};

