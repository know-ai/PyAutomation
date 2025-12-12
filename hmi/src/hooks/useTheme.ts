import { useEffect } from "react";
import { useAppSelector } from "./useAppSelector";
import { useAppDispatch } from "./useAppDispatch";
import { toggleTheme, setTheme } from "../store/slices/themeSlice";

export const useTheme = () => {
  const mode = useAppSelector((state) => state.theme.mode);
  const dispatch = useAppDispatch();

  // Aplicar el tema al DOM cuando cambie
  useEffect(() => {
    const html = document.documentElement;
    const body = document.body;

    // Remover clases anteriores
    html.classList.remove("light", "dark");
    body.classList.remove("light", "dark", "dark-mode");

    // Agregar clase según el tema
    if (mode === "dark") {
      html.classList.add("dark");
      body.classList.add("dark", "dark-mode");
      html.setAttribute("data-bs-theme", "dark");
    } else {
      html.classList.add("light");
      body.classList.add("light");
      html.setAttribute("data-bs-theme", "light");
    }
  }, [mode]);

  const toggle = () => {
    dispatch(toggleTheme());
  };

  const set = (theme: "light" | "dark") => {
    dispatch(setTheme(theme));
  };

  return {
    mode,
    toggle,
    set,
    isDark: mode === "dark",
    isLight: mode === "light",
  };
};

