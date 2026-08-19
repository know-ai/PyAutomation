import clsx from "clsx";
import { useEffect, useState } from "react";
import { useTranslation } from "../hooks/useTranslation";
import { getClockHealth, type ClockHealth } from "../services/clock";

type ClockLevel = "unknown" | "ok" | "warn" | "alarm" | "disabled";

function resolveLevel(clock: ClockHealth): ClockLevel {
  if (!clock.enabled) return "disabled";
  if (clock.synced === false) return "alarm";
  if (clock.warn) return "warn";
  if (clock.synced === true) return "ok";
  return "unknown";
}

export function ClockBadge() {
  const { t } = useTranslation();
  const [clock, setClock] = useState<ClockHealth>({});

  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      try {
        const status = await getClockHealth();
        if (!cancelled) setClock(status);
      } catch {
        if (!cancelled) setClock({});
      }
    };
    void load();
    const id = window.setInterval(load, 60_000);
    return () => {
      cancelled = true;
      window.clearInterval(id);
    };
  }, []);

  const level = resolveLevel(clock);
  const offset =
    clock.offset_ms ?? clock.CLOCK_OFFSET_MS ?? null;
  const errorSuffix =
    clock.last_error && level === "alarm"
      ? ` — ${clock.last_error}`
      : clock.auth_required_detected
        ? ` — ${t("clock.authRequiredShort")}`
        : "";
  const addressSuffix = clock.last_address_used ? ` @ ${clock.last_address_used}` : "";
  const title =
    level === "disabled"
      ? t("clock.badgeDisabled")
      : level === "alarm"
        ? `${t("clock.badgeAlarm", { offset: offset ?? "?" })}${addressSuffix}${errorSuffix}`
        : level === "warn"
          ? t("clock.badgeWarn", { offset: offset ?? "?" })
          : level === "ok"
            ? t("clock.badgeOk", { offset: offset ?? 0 })
            : t("clock.badgeUnknown");

  return (
    <span
      className={clsx("clock-badge", `clock-badge--${level}`)}
      title={title}
      aria-label={title}
    >
      <i className="bi bi-clock-history" aria-hidden="true" />
    </span>
  );
}
