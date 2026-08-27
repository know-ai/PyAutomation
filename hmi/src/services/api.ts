import axios, { AxiosError, AxiosRequestConfig } from "axios";
import { API_BASE_URL, DETECTED_PROTOCOL } from "../config/constants";
import { store } from "../store/store";
import { AUTH_STORAGE_KEY, logout } from "../store/slices/authSlice";
import { DB_UNAVAILABLE_CODE, emitDatabaseHealth } from "./health";
import { isProcessRestartActive } from "./processRestart";

// Configuración de axios
// Nota: Para certificados autofirmados en el navegador, el usuario debe
// aceptar el certificado manualmente la primera vez. El navegador manejará
// esto automáticamente después de la aceptación inicial.
const api = axios.create({
  baseURL: API_BASE_URL,
  timeout: 15000,
});

function isPublicAuthRequest(config?: AxiosRequestConfig | null): boolean {
  const url = `${config?.baseURL || ""}${config?.url || ""}`.toLowerCase();
  return url.includes("/users/login") || url.includes("/users/signup");
}

function requestApiKey(error: AxiosError): string | null {
  const headers = error.config?.headers;
  if (!headers) return null;
  const fromGetter = (headers as { get?: (key: string) => unknown }).get?.("X-API-KEY");
  const raw =
    fromGetter ??
    (headers as Record<string, unknown>)["X-API-KEY"] ??
    (headers as Record<string, unknown>)["x-api-key"];
  return typeof raw === "string" && raw ? raw : null;
}

function isStaleAuthFailure(error: AxiosError): boolean {
  const used = requestApiKey(error);
  const current = store.getState().auth.token;
  return Boolean(current && used && used !== current);
}

function redirectToLogin(messageKey: string): void {
  store.dispatch(logout());
  try {
    sessionStorage.setItem(
      "pendingToast",
      JSON.stringify({
        messageKey,
        type: "warning",
        duration: 0,
      })
    );
  } catch (_e) {
    // ignore storage errors
  }
  const basePath = import.meta.env.VITE_BASE_PATH || "/hmi/";
  const loginPath = basePath.endsWith("/") ? `${basePath}login` : `${basePath}/login`;
  window.location.href = loginPath;
}

api.interceptors.request.use((config) => {
  if (isPublicAuthRequest(config)) {
    if (config.headers) {
      delete (config.headers as Record<string, unknown>)["X-API-KEY"];
      delete (config.headers as Record<string, unknown>)["x-api-key"];
    }
    return config;
  }

  const state = store.getState();
  let token = state.auth.token;

  // Fallback al storage por si el estado aún no está hidratado
  if (!token) {
    try {
      const raw = localStorage.getItem(AUTH_STORAGE_KEY);
      if (raw) {
        const parsed = JSON.parse(raw);
        token = parsed?.token ?? null;
      }
    } catch (_e) {
      // ignore
    }
  }

  if (token) {
    config.headers = config.headers || {};
    config.headers["X-API-KEY"] = token;
  }
  return config;
});

api.interceptors.response.use(
  (response) => response,
  (error: AxiosError) => {
    // Verificar si el error es por token inválido
    if (error.response) {
      const status = error.response.status;
      const payload = error.response.data as
        | { code?: string; message?: string }
        | string
        | undefined;
      const code = typeof payload === "object" ? payload?.code : undefined;
      const message =
        (typeof payload === "object" && payload?.message) ||
        (typeof payload === "string" ? payload : "");

      if (
        status === 503 &&
        typeof payload === "object" &&
        (payload?.code === DB_UNAVAILABLE_CODE ||
          payload?.code === "AUTH_BACKEND_UNAVAILABLE")
      ) {
        (error as AxiosError & { isDbUnavailable?: boolean }).isDbUnavailable = true;
        if (payload?.code === DB_UNAVAILABLE_CODE) {
          emitDatabaseHealth(false);
        }
        // Never force-logout when the historian/auth backend is temporarily down.
        return Promise.reject(error);
      }

      if (status === 401 && isProcessRestartActive()) {
        return Promise.reject(error);
      }

      // Explicit single-session takeover only.
      // Ignore 401s from an older token after a successful re-login in this tab.
      if (status === 401 && code === "SESSION_SUPERSEDED") {
        if (!isStaleAuthFailure(error)) {
          redirectToLogin("auth.sessionTakenOver");
        }
        return Promise.reject(error);
      }

      // Generic invalid/expired session — do not claim "another device".
      if (
        status === 401 &&
        (code === "SESSION_INVALID" ||
          message?.toLowerCase().includes("invalid token") ||
          message?.toLowerCase().includes("token inválido"))
      ) {
        if (!isStaleAuthFailure(error)) {
          redirectToLogin("auth.sessionExpired");
        }
      }
    }

    return Promise.reject(error);
  }
);

export default api;


