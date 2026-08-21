import { configureStore } from "@reduxjs/toolkit";
import authReducer, { AUTH_STORAGE_KEY } from "./slices/authSlice";
import themeReducer, { loadThemeFromStorage } from "./slices/themeSlice";
import localeReducer, { loadLocaleFromStorage } from "./slices/localeSlice";
import tagsReducer, { persistTagHistory } from "./slices/tagsSlice";
import alarmsReducer from "./slices/alarmsSlice";
import machinesReducer from "./slices/machinesSlice";
import displayTimezoneReducer from "./slices/displayTimezoneSlice";
import displayDensityReducer from "./slices/displayDensitySlice";

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
    displayDensity: displayDensityReducer,
  },
  preloadedState: {
    ...loadAuthState(),
    ...loadThemeState(),
    ...loadLocaleState(),
  },
});

export type RootState = ReturnType<typeof store.getState>;
export type AppDispatch = typeof store.dispatch;

/** Never run localStorage stringify on every Redux tick — it freezes RT trends 1–3 s. */
const HISTORY_PERSIST_INTERVAL_MS = 30_000;

const persistHistoryNow = () => {
  const { tagHistory, historySubscribers } = store.getState().tags;
  persistTagHistory(tagHistory, historySubscribers);
};

const scheduleIdlePersist = () => {
  const run = () => persistHistoryNow();
  if (typeof window !== "undefined" && "requestIdleCallback" in window) {
    (
      window as Window & {
        requestIdleCallback: (cb: () => void, opts?: { timeout: number }) => number;
      }
    ).requestIdleCallback(run, { timeout: 5000 });
    return;
  }
  setTimeout(run, 0);
};

if (typeof window !== "undefined") {
  window.setInterval(scheduleIdlePersist, HISTORY_PERSIST_INTERVAL_MS);
  window.addEventListener("beforeunload", persistHistoryNow);
  document.addEventListener("visibilitychange", () => {
    if (document.hidden) persistHistoryNow();
  });
}
