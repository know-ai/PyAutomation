import api from "./api";

export type DatabaseHealthResponse = {
  status: "ok" | "error";
  connected: boolean;
  latency_ms: number | null;
  message: string;
};

export const DB_UNAVAILABLE_CODE = "DB_UNAVAILABLE";
export const DB_HEALTH_EVENT = "pyautomation:db-health";

export function emitDatabaseHealth(connected: boolean): void {
  if (typeof window === "undefined") return;
  window.dispatchEvent(
    new CustomEvent(DB_HEALTH_EVENT, {
      detail: { connected },
    })
  );
}

export function isDbUnavailableError(error: unknown): boolean {
  const err = error as {
    isDbUnavailable?: boolean;
    response?: { status?: number; data?: { code?: string } };
  };
  if (err?.isDbUnavailable) return true;
  return err?.response?.status === 503 && err?.response?.data?.code === DB_UNAVAILABLE_CODE;
}

function asErrorText(value: unknown): string | null {
  if (typeof value === "string") {
    const trimmed = value.trim();
    if (!trimmed || trimmed.startsWith("<")) return null;
    return trimmed;
  }
  return null;
}

export function axiosErrorMessage(error: unknown, fallback: string): string {
  const err = error as { message?: string; response?: { data?: unknown } };
  const data = err?.response?.data;
  if (typeof data === "string") {
    return asErrorText(data) || fallback;
  }
  if (data && typeof data === "object") {
    const payload = data as { message?: unknown; detail?: unknown; error?: unknown };
    return (
      asErrorText(payload.message) ||
      asErrorText(payload.detail) ||
      asErrorText(payload.error) ||
      fallback
    );
  }
  return asErrorText(err?.message) || fallback;
}

export const getDatabaseHealth = async (): Promise<DatabaseHealthResponse> => {
  const { data } = await api.get("/health/db", { timeout: 2500 });
  return data;
};

export const getPlantTimezone = async (): Promise<string> => {
  const { data } = await api.get("/system/timezone", { timeout: 2500 });
  return typeof data?.timezone === "string" ? data.timezone : "";
};

export type PlantNode = {
  id: string;
  area: string;
  site?: string | null;
  hostname?: string | null;
  version?: string | null;
};

export const getPlantNodes = async (): Promise<PlantNode[]> => {
  const { data } = await api.get("/system/nodes");
  return data?.data || [];
};

export type NodeIdentity = {
  nodeId: string;
  area: string;
  site: string;
};

export const getNodeIdentity = async (): Promise<NodeIdentity> => {
  const { data } = await api.get("/health/system", { timeout: 2500 });
  return {
    nodeId: typeof data?.NODE_ID === "string" ? data.NODE_ID : "",
    area: typeof data?.NODE_AREA === "string" ? data.NODE_AREA : "",
    site: typeof data?.NODE_SITE === "string" ? data.NODE_SITE : "",
  };
};

export const reconnectRemoteDatabase = async (): Promise<DatabaseHealthResponse> => {
  try {
    const { data } = await api.post("/system/reconnect_db", {}, { timeout: 15000 });
    return data;
  } catch (error: unknown) {
    const data = (error as { response?: { data?: DatabaseHealthResponse } })?.response?.data;
    if (data && typeof data.connected === "boolean") {
      return data;
    }
    throw error;
  }
};
