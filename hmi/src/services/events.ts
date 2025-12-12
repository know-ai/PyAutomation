import api from "./api";

export type Event = {
  id?: number;
  timestamp?: string;
  message?: string;
  description?: string;
  classification?: string;
  priority?: number;
  criticity?: number;
  username?: string;
  user?: {
    username?: string;
    [key: string]: any;
  };
  [key: string]: any;
};

export type EventFilter = {
  usernames?: string[];
  priorities?: number[];
  criticities?: number[];
  message?: string;
  classification?: string;
  description?: string;
  greater_than_timestamp?: string;
  less_than_timestamp?: string;
  timezone?: string;
  page?: number;
  limit?: number;
};

export type EventResponse = {
  data: Event[];
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
 * Filtra eventos del sistema según los criterios proporcionados
 */
export const filterEvents = async (filters: EventFilter): Promise<EventResponse> => {
  const { data } = await api.post("/events/filter_by", filters);
  return data;
};

