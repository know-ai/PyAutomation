import { createSlice, PayloadAction } from "@reduxjs/toolkit";

const LOCALE_STORAGE_KEY = "pyautomation.locale";

const loadLocaleFromStorage = (): "en" | "es" => {
  try {
    const saved = localStorage.getItem(LOCALE_STORAGE_KEY);
    if (saved === "en" || saved === "es") {
      return saved;
    }
    // Detectar idioma del navegador
    const browserLang = navigator.language.split("-")[0];
    if (browserLang === "es") {
      return "es";
    }
  } catch (_e) {
    // ignore
  }
  return "en"; // Por defecto inglés
};

const persistLocale = (locale: "en" | "es") => {
  try {
    localStorage.setItem(LOCALE_STORAGE_KEY, locale);
    // Actualizar el atributo lang del HTML
    document.documentElement.setAttribute("lang", locale);
  } catch (_e) {
    // ignore persistence errors
  }
};

export type LocaleState = {
  locale: "en" | "es";
};

const initialState: LocaleState = {
  locale: loadLocaleFromStorage(),
};

// Inicializar el atributo lang del HTML
if (typeof document !== "undefined") {
  document.documentElement.setAttribute("lang", initialState.locale);
}

const localeSlice = createSlice({
  name: "locale",
  initialState,
  reducers: {
    setLocale(state, action: PayloadAction<"en" | "es">) {
      state.locale = action.payload;
      persistLocale(state.locale);
    },
    toggleLocale(state) {
      state.locale = state.locale === "en" ? "es" : "en";
      persistLocale(state.locale);
    },
  },
});

export const { setLocale, toggleLocale } = localeSlice.actions;

export default localeSlice.reducer;

export { loadLocaleFromStorage };

