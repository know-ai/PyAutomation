import api from "./api";

export type Tag = {
  id?: string | number;
  name: string;
  unit: string;
  variable: string;
  display_unit?: string;
  data_type?: string;
  description?: string;
  display_name?: string;
  opcua_address?: string;
  node_namespace?: string;
  scan_time?: number;
  dead_band?: number;
  process_filter?: boolean;
  gaussian_filter?: boolean;
  gaussian_filter_threshold?: number;
  gaussian_filter_r_value?: number;
  outlier_detection?: boolean;
  out_of_range_detection?: boolean;
  frozen_data_detection?: boolean;
  segment?: string;
  manufacturer?: string;
  [key: string]: any; // Para campos adicionales que puedan venir del backend
};

export type TagsResponse = {
  data: Tag[];
  pagination: {
    page: number;
    limit: number;
    total: number;
    pages: number;
  };
};

/**
 * Obtiene la lista de tags con paginación
 */
export const getTags = async (
  page: number = 1,
  limit: number = 20
): Promise<TagsResponse> => {
  const { data } = await api.get("/tags/", {
    params: { page, limit },
  });
  return data;
};

/**
 * Obtiene tags por nombres específicos
 */
export const getTagsByNames = async (names: string[]): Promise<Tag[]> => {
  const { data } = await api.get("/tags/names", {
    params: { names },
  });
  return data;
};

/**
 * Crea un nuevo tag
 */
export const createTag = async (tag: Partial<Tag>): Promise<any> => {
  const { data } = await api.post("/tags/add", tag);
  return data;
};

/**
 * Actualiza un tag existente
 */
export const updateTag = async (tag: Partial<Tag> & { id: string | number }): Promise<any> => {
  const { data } = await api.post("/tags/update", tag);
  return data;
};

/**
 * Elimina un tag por nombre
 */
export const deleteTag = async (tagName: string): Promise<any> => {
  const { data } = await api.delete(`/tags/delete/${encodeURIComponent(tagName)}`);
  return data;
};

/**
 * Escribe un valor a un tag
 */
export const writeTagValue = async (
  tagName: string,
  value: any
): Promise<any> => {
  const { data } = await api.post("/tags/write_value", {
    tag_name: tagName,
    value,
  });
  return data;
};

/**
 * Obtiene zonas horarias disponibles
 */
export const getTimezones = async (): Promise<string[]> => {
  const { data } = await api.get("/tags/timezones");
  return data;
};

/**
 * Obtiene todas las variables disponibles (Pressure, Temperature, etc.)
 */
export const getVariables = async (): Promise<string[]> => {
  const { data } = await api.get("/tags/variables");
  return data?.data || [];
};

/**
 * Obtiene las unidades disponibles para una variable específica
 */
export const getUnitsByVariable = async (variableName: string): Promise<string[]> => {
  const { data } = await api.get(`/tags/units/${encodeURIComponent(variableName)}`);
  return data?.data || [];
};

export type TabularDataFilter = {
  tags: string[];
  greater_than_timestamp: string;
  less_than_timestamp: string;
  sample_time: number;
  timezone?: string;
  page?: number;
  limit?: number;
};

export type TabularDataResponse = {
  tag_names: string[];
  display_names: string[];
  values: any[][];
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
 * Obtiene datos tabulares históricos de tags con resampling
 */
export const getTabularData = async (
  filters: TabularDataFilter
): Promise<TabularDataResponse> => {
  const { data } = await api.post("/tags/get_tabular_data", filters);
  return data;
};

