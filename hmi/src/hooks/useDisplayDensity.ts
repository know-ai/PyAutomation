import { useEffect } from "react";
import { useAppSelector } from "./useAppSelector";
import { useAppDispatch } from "./useAppDispatch";
import { setDisplayDensity } from "../store/slices/displayDensitySlice";
import {
  applyDisplayDensityToDom,
  type DisplayDensity,
} from "../utils/displayDensity";

export function useDisplayDensity() {
  const mode = useAppSelector((state) => state.displayDensity.mode);
  const dispatch = useAppDispatch();

  useEffect(() => {
    applyDisplayDensityToDom(mode);
    if (mode !== "auto") return undefined;

    let frame = 0;
    const onChange = () => {
      if (frame) return;
      frame = window.requestAnimationFrame(() => {
        frame = 0;
        applyDisplayDensityToDom("auto");
      });
    };

    window.addEventListener("resize", onChange);
    window.addEventListener("orientationchange", onChange);
    return () => {
      if (frame) window.cancelAnimationFrame(frame);
      window.removeEventListener("resize", onChange);
      window.removeEventListener("orientationchange", onChange);
    };
  }, [mode]);

  return {
    mode,
    setMode: (next: DisplayDensity) => dispatch(setDisplayDensity(next)),
  };
}
