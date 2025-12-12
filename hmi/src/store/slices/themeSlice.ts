import { createSlice, PayloadAction } from "@reduxjs/toolkit";

const THEME_STORAGE_KEY = "pyautomation.theme";

export const loadThemeFromStorage = (): "light" | "dark" => {
  try {
    const saved = localStorage.getItem(THEME_STORAGE_KEY);
    if (saved === "light" || saved === "dark") {
      return saved;
    }
    // Detectar preferencia del sistema
    if (window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches) {
      return "dark";
    }
  } catch (_e) {
    // ignore
  }
  return "light";
};

const persistTheme = (mode: "light" | "dark") => {
  try {
    localStorage.setItem(THEME_STORAGE_KEY, mode);
  } catch (_e) {
    // ignore persistence errors
  }
};

export type ThemeState = {
  mode: "light" | "dark";
};

const initialState: ThemeState = {
  mode: loadThemeFromStorage(),
};

const themeSlice = createSlice({
  name: "theme",
  initialState,
  reducers: {
    toggleTheme(state) {
      state.mode = state.mode === "light" ? "dark" : "light";
      persistTheme(state.mode);
    },
    setTheme(state, action: PayloadAction<"light" | "dark">) {
      state.mode = action.payload;
      persistTheme(state.mode);
    },
  },
});

export const { toggleTheme, setTheme } = themeSlice.actions;

export default themeSlice.reducer;

