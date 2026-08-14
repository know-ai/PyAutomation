import { configureStore } from "@reduxjs/toolkit";
import authReducer, { AUTH_STORAGE_KEY } from "./slices/authSlice";
import themeReducer, { loadThemeFromStorage } from "./slices/themeSlice";
import localeReducer, { loadLocaleFromStorage } from "./slices/localeSlice";
import tagsReducer, { persistTagHistory } from "./slices/tagsSlice";
import alarmsReducer from "./slices/alarmsSlice";
import machinesReducer from "./slices/machinesSlice";
import displayTimezoneReducer from "./slices/displayTimezoneSlice";

const loadAuthState = () => {
  try {
    const raw = localStorage.getItem(AUTH_STORAGE_KEY);
    if (!raw) return undefined;
    const parsed = JSON.parse(raw);
    return { auth: parsed };
  } catch (_e) {
    return undefined;
  }
};

const loadThemeState = () => {
  try {
    const theme = loadThemeFromStorage();
    return { theme: { mode: theme } };
  } catch (_e) {
    return undefined;
  }
};

const loadLocaleState = () => {
  try {
    const locale = loadLocaleFromStorage();
    return { locale: { locale } };
  } catch (_e) {
    return undefined;
  }
};

export const store = configureStore({
  reducer: {
    auth: authReducer,
    theme: themeReducer,
    locale: localeReducer,
    tags: tagsReducer,
    alarms: alarmsReducer,
    machines: machinesReducer,
    displayTimezone: displayTimezoneReducer,
  },
  preloadedState: {
    ...loadAuthState(),
    ...loadThemeState(),
    ...loadLocaleState(),
  },
});

export type RootState = ReturnType<typeof store.getState>;
export type AppDispatch = typeof store.dispatch;

const persistHistoryNow = () => {
  persistTagHistory(store.getState().tags.tagHistory);
};

let persistHistoryTimer: ReturnType<typeof setTimeout> | null = null;
store.subscribe(() => {
  if (persistHistoryTimer != null) return;
  persistHistoryTimer = setTimeout(() => {
    persistHistoryTimer = null;
    persistHistoryNow();
  }, 2000);
});

if (typeof window !== "undefined") {
  window.addEventListener("beforeunload", persistHistoryNow);
  document.addEventListener("visibilitychange", () => {
    if (document.hidden) persistHistoryNow();
  });
}

