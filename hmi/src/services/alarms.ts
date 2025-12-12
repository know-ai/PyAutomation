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

