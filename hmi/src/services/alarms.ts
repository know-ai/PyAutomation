import api from "./api";

export type Alarm = {
  identifier?: string;
  id?: string | number;
  name: string;
  tag: string;
  alarm_type?: string;
  trigger_value?: number | boolean;
  description?: string;
  state?: {
    mnemonic?: string;
    state?: string;
    process_condition?: string;
    alarm_status?: string;
    annunciate_status?: string;
    acknowledge_status?: string;
  } | string;
  timestamp?: string;
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

/**
 * Obtiene la lista de alarmas con paginación
 */
export const getAlarms = async (
  page: number = 1,
  limit: number = 20
): Promise<AlarmsResponse> => {
  const { data } = await api.get("/alarms/", {
    params: { page, limit },
  });
  return data;
};

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
  name: string;
  tag: string;
  description?: string;
  state: string;
  mnemonic?: string;
  status?: string;
  alarm_time: string;
  ack_time?: string | null;
  has_comments?: boolean;
};

export type AlarmSummaryFilter = {
  names?: string[];
  states?: string[];
  tags?: string[];
  greater_than_timestamp?: string;
  less_than_timestamp?: string;
  timezone?: string;
  page?: number;
  limit?: number;
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
  filters: AlarmSummaryFilter
): Promise<AlarmSummaryResponse> => {
  const { data } = await api.post("/alarms/summary/filter_by", filters);
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

