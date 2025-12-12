import api from "./api";

export type Log = {
  id?: number;
  timestamp?: string;
  message?: string;
  description?: string;
  classification?: string;
  user?: {
    username?: string;
    [key: string]: any;
  };
  alarm?: {
    id?: number;
    name?: string;
    [key: string]: any;
  };
  event?: {
    id?: number;
    [key: string]: any;
  };
  [key: string]: any;
};

export type LogFilter = {
  usernames?: string[];
  alarm_names?: string[];
  event_ids?: number[];
  classification?: string;
  message?: string;
  description?: string;
  greater_than_timestamp?: string;
  less_than_timestamp?: string;
  timezone?: string;
  page?: number;
  limit?: number;
};

export type LogResponse = {
  data: Log[];
  pagination: {
    page: number;
    limit: number;
    total_records: number;
    total_pages: number;
    has_next: boolean;
    has_prev: boolean;
  };
};

export type CreateLogPayload = {
  message: string;
  description?: string;
  alarm_summary_id?: number;
  event_id?: number;
};

/**
 * Filtra logs operacionales según los criterios proporcionados
 */
export const filterLogs = async (filters: LogFilter): Promise<LogResponse> => {
  const { data } = await api.post("/logs/filter_by", filters);
  // El backend ahora siempre retorna un objeto con paginación
  if (Array.isArray(data)) {
    // Fallback por compatibilidad (no debería ocurrir)
    return {
      data: data,
      pagination: {
        page: 1,
        limit: data.length,
        total_records: data.length,
        total_pages: 1,
        has_next: false,
        has_prev: false,
      },
    };
  }
  return data as LogResponse;
};

/**
 * Crea un nuevo log operacional
 */
export const createLog = async (payload: CreateLogPayload): Promise<any> => {
  const { data } = await api.post("/logs/add", payload);
  return data;
};

