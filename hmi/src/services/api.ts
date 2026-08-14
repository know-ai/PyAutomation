import axios, { AxiosError, AxiosRequestConfig } from "axios";
import { API_BASE_URL, DETECTED_PROTOCOL } from "../config/constants";
import { store } from "../store/store";
import { AUTH_STORAGE_KEY, logout } from "../store/slices/authSlice";
import { DB_UNAVAILABLE_CODE, emitDatabaseHealth } from "./health";

// Configuración de axios
// Nota: Para certificados autofirmados en el navegador, el usuario debe
// aceptar el certificado manualmente la primera vez. El navegador manejará
// esto automáticamente después de la aceptación inicial.
const api = axios.create({
  baseURL: API_BASE_URL,
  timeout: 15000,
});

api.interceptors.request.use((config) => {
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

      // Explicit single-session takeover only.
      if (status === 401 && code === "SESSION_SUPERSEDED") {
        store.dispatch(logout());
        try {
          sessionStorage.setItem(
            "pendingToast",
            JSON.stringify({
              messageKey: "auth.sessionTakenOver",
              type: "warning",
              duration: 0,
            })
          );
        } catch (_e) {
          // ignore storage errors
        }
        const basePath = import.meta.env.VITE_BASE_PATH || "/hmi/";
        const loginPath = basePath.endsWith("/")
          ? `${basePath}login`
          : `${basePath}/login`;
        window.location.href = loginPath;
        return Promise.reject(error);
      }

      // Generic invalid/expired session — do not claim "another device".
      if (
        status === 401 &&
        (code === "SESSION_INVALID" ||
          message?.toLowerCase().includes("invalid token") ||
          message?.toLowerCase().includes("token inválido"))
      ) {
        store.dispatch(logout());
        try {
          sessionStorage.setItem(
            "pendingToast",
            JSON.stringify({
              messageKey: "auth.sessionExpired",
              type: "warning",
              duration: 0,
            })
          );
        } catch (_e) {
          // ignore storage errors
        }
        const basePath = import.meta.env.VITE_BASE_PATH || "/hmi/";
        const loginPath = basePath.endsWith("/")
          ? `${basePath}login`
          : `${basePath}/login`;
        window.location.href = loginPath;
      }
    }

    return Promise.reject(error);
  }
);

export default api;


