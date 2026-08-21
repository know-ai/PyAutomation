import api from "./api";

export type AppConfig = {
  logger_period?: number;
  log_max_bytes?: number;
  log_backup_count?: number;
  log_level?: number;
  alarm_inhibit_uncertain_quality?: boolean;
};

export type UpdateSettingsPayload = {
  logger_period?: number;
  log_max_bytes?: number;
  log_backup_count?: number;
  log_level?: number;
  alarm_inhibit_uncertain_quality?: boolean;
};

export type ExportConfigResponse = {
  message?: string;
  error?: string;
};

export type ImportConfigResponse = {
  message: string;
  summary?: {
    imported: number;
    skipped: number;
    errors: number;
  };
  results?: {
    imported: Record<string, number>;
    skipped: Record<string, number>;
    errors: Record<string, string[]>;
  };
  error?: string;
  details?: any;
};

/**
 * Obtiene las configuraciones actuales de la aplicación
 */
export const getSettings = async (): Promise<AppConfig> => {
  const { data } = await api.get("/settings/");
  return data;
};

/**
 * Actualiza las configuraciones de la aplicación
 */
export const updateSettings = async (payload: UpdateSettingsPayload): Promise<string> => {
  const { data } = await api.put("/settings/update", payload);
  return data;
};

/**
 * Exporta la configuración completa a un archivo JSON
 */
export const exportConfig = async (): Promise<Blob> => {
  const response = await api.get("/settings/export_config", {
    responseType: "blob",
  });
  return response.data;
};

/**
 * Importa la configuración desde un archivo JSON
 */
export const importConfig = async (file: File): Promise<ImportConfigResponse> => {
  const formData = new FormData();
  formData.append("file", file);
  
  const { data } = await api.post("/settings/import_config", formData, {
    headers: {
      "Content-Type": "multipart/form-data",
    },
  });
  return data;
};

