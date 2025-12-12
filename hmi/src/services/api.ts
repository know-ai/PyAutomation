import axios, { AxiosError } from "axios";
import { API_BASE_URL } from "../config/constants";
import { store } from "../store/store";
import { AUTH_STORAGE_KEY, logout } from "../store/slices/authSlice";
import { showToast } from "../utils/toast";

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
      const message = 
        (error.response.data as any)?.message || 
        (typeof error.response.data === "string" ? error.response.data : "");

      // Detectar token inválido (401 con mensaje "Invalid token" o similar)
      if (
        status === 401 &&
        (message?.toLowerCase().includes("invalid token") ||
         message?.toLowerCase().includes("token inválido") ||
         message?.toLowerCase().includes("key is missing"))
      ) {
        // Hacer logout
        store.dispatch(logout());

        // Guardar el mensaje del toast en sessionStorage para mostrarlo después de la redirección
        const toastMessage = "Se ha iniciado sesión en otro dispositivo. Por favor, inicie sesión nuevamente.";
        try {
          sessionStorage.setItem("pendingToast", JSON.stringify({
            message: toastMessage,
            type: "warning",
            duration: 0 // 0 = no auto-cerrar, solo con el botón
          }));
        } catch (_e) {
          // ignore storage errors
        }

        // Redirigir a login
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


