import axios from "axios";
import { API_BASE_URL } from "../config/constants";
import { store } from "../store/store";
import { AUTH_STORAGE_KEY } from "../store/slices/authSlice";

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

export default api;


