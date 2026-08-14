import clsx from "clsx";
import { useDisplayTimezone } from "../hooks/useDisplayTimezone";
import { useTranslation } from "../hooks/useTranslation";

export function TimezoneBadge({ className }: { className?: string }) {
  const { t } = useTranslation();
  const { mode, timeZone } = useDisplayTimezone();
  const zone = timeZone || "UTC";
  const label =
    mode === "plant"
      ? t("timezone.plantBadge", { zone })
      : t("timezone.localBadge", { zone });

  return (
    <span className={clsx("timezone-badge", className)} title={label}>
      <i className="bi bi-clock" aria-hidden="true" />
      {label}
    </span>
  );
}
