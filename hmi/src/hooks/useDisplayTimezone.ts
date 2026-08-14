import { useEffect } from "react";
import { useAppDispatch } from "./useAppDispatch";
import { useAppSelector } from "./useAppSelector";
import { setDisplayTimezoneMode, setPlantTimezone } from "../store/slices/displayTimezoneSlice";
import { getPlantTimezone } from "../services/health";
import { getBrowserTimeZone, type DisplayTimezoneMode } from "../utils/timezone";

export function useDisplayTimezone() {
  const mode = useAppSelector((state) => state.displayTimezone.mode);
  const plantTimezone = useAppSelector((state) => state.displayTimezone.plantTimezone);
  const dispatch = useAppDispatch();

  useEffect(() => {
    let cancelled = false;
    getPlantTimezone()
      .then((timezone) => {
        if (!cancelled && timezone) {
          dispatch(setPlantTimezone(timezone));
        }
      })
      .catch(() => {
        // Endpoint unavailable: keep browser fallback.
      });
    return () => {
      cancelled = true;
    };
  }, [dispatch]);

  const browserTimezone = getBrowserTimeZone();
  const timeZone =
    mode === "plant" ? plantTimezone || browserTimezone : browserTimezone || plantTimezone;

  return {
    mode,
    timeZone,
    plantTimezone,
    browserTimezone,
    setMode: (next: DisplayTimezoneMode) => dispatch(setDisplayTimezoneMode(next)),
  };
}
