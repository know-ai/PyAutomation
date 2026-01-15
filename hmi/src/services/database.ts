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
  try {
    const response = await api.get("/database/connected");
    const data = response?.data;
    // Si data es null, undefined, o no tiene la propiedad connected, retornar un objeto por defecto
    if (data == null || typeof data !== "object" || typeof data.connected !== "boolean") {
      return { connected: false };
    }
  return data;
  } catch (error: any) {
    // En caso de error, retornar desconectado
    console.error("Error in isDatabaseConnected:", error);
    return { connected: false };
  }
};

/**
 * Conecta a la base de datos con la configuración proporcionada
 */
export const connectDatabase = async (payload: DatabaseConnectPayload): Promise<DatabaseConnectResponse> => {
  try {
    const response = await api.post("/database/connect", payload);
    const data = response?.data;
    // Si data es null o undefined, retornar un objeto por defecto
    if (data == null || typeof data !== "object") {
      return { connected: false, message: "Error: respuesta inválida del servidor" };
    }
    // Asegurar que siempre tenga las propiedades esperadas
    return {
      connected: data.connected === true,
      message: data.message || (data.connected ? "Conectado exitosamente" : "Error al conectar")
    };
  } catch (error: any) {
    const errorMessage = error?.response?.data?.message || error?.message || "Error al conectar a la base de datos";
    return { connected: false, message: errorMessage };
  }
};

/**
 * Desconecta de la base de datos
 */
export const disconnectDatabase = async (): Promise<DatabaseConnectResponse> => {
  try {
    const response = await api.post("/database/disconnect");
    const data = response?.data;
    // Si data es null o undefined, retornar un objeto por defecto
    if (data == null || typeof data !== "object") {
      return { connected: false, message: "Desconectado" };
    }
    // Asegurar que siempre tenga las propiedades esperadas
    return {
      connected: false,
      message: data.message || "Desconectado exitosamente"
    };
  } catch (error: any) {
    const errorMessage = error?.response?.data?.message || error?.message || "Desconectado";
    return { connected: false, message: errorMessage };
  }
};

