import { FloatingStatusBanner } from "./FloatingStatusBanner";
import { useSystemHealth } from "../hooks/useSystemHealth";
import { useTranslation } from "../hooks/useTranslation";

const POSITION_KEY = "pya.degradedBanner.pos";

/**
 * Floating degraded-mode notice (remote DB down, socket still usable).
 * Overlay — no layout shift. Draggable. Hides when DB recovers.
 */
export function DegradedModeBanner() {
  const { t } = useTranslation();
  const { dbStatus, transportHealth } = useSystemHealth();
  const visible = dbStatus === "disconnected" && transportHealth !== "disconnected";
  const text = t("dbHealth.degradedModeBanner");

  return (
    <FloatingStatusBanner
      id="db"
      storageKey={POSITION_KEY}
      visible={visible}
      text={text}
      ariaLabel={text}
      moveLabel={t("dbHealth.degradedModeMove")}
      tone="warning"
      iconClassName="bi bi-exclamation-triangle-fill"
    />
  );
}
