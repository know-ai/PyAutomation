import { configureStore } from "@reduxjs/toolkit";
import authReducer, { AUTH_STORAGE_KEY } from "./slices/authSlice";
import themeReducer, { loadThemeFromStorage } from "./slices/themeSlice";
import localeReducer, { loadLocaleFromStorage } from "./slices/localeSlice";

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
  },
  preloadedState: {
    ...loadAuthState(),
    ...loadThemeState(),
    ...loadLocaleState(),
  },
});

export type RootState = ReturnType<typeof store.getState>;
export type AppDispatch = typeof store.dispatch;

