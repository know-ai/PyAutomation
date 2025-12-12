import api from "./api";

export type DatabaseConfig = {
  dbtype?: string;
  dbfile?: string;
  user?: string;
  password?: string;
  host?: string;
  port?: number | string;
  name?: string;
};

export type DatabaseConnectPayload = {
  dbtype: string;
  dbfile?: string;
  user?: string;
  password?: string;
  host?: string;
  port?: number | string;
  name?: string;
  reload?: boolean;
};

export type DatabaseConnectedResponse = {
  connected: boolean;
};

export type DatabaseConfigResponse = DatabaseConfig & {
  message?: string;
};

export type DatabaseConnectResponse = {
  message: string;
  connected: boolean;
};

/**
 * Obtiene la configuración actual de la base de datos
 */
export const getDatabaseConfig = async (): Promise<DatabaseConfigResponse> => {
  const { data } = await api.get("/database/config");
  return data;
};

/**
 * Verifica si la base de datos está conectada
 */
export const isDatabaseConnected = async (): Promise<DatabaseConnectedResponse> => {
  const { data } = await api.get("/database/connected");
  return data;
};

/**
 * Conecta a la base de datos con la configuración proporcionada
 */
export const connectDatabase = async (payload: DatabaseConnectPayload): Promise<DatabaseConnectResponse> => {
  const { data } = await api.post("/database/connect", payload);
  return data;
};

/**
 * Desconecta de la base de datos
 */
export const disconnectDatabase = async (): Promise<DatabaseConnectResponse> => {
  const { data } = await api.post("/database/disconnect");
  return data;
};

