import clsx from "clsx";
import { useDisplayTimezone } from "../hooks/useDisplayTimezone";
import { useTranslation } from "../hooks/useTranslation";

export function TimezoneBadge({
  className,
  compact = false,
}: {
  className?: string;
  compact?: boolean;
}) {
  const { t } = useTranslation();
  const { mode, timeZone } = useDisplayTimezone();
  const zone = timeZone || "UTC";
  const short = mode === "plant" ? t("timezone.plant") : t("timezone.local");
  const label =
    mode === "plant"
      ? t("timezone.plantBadge", { zone })
      : t("timezone.localBadge", { zone });

  return (
    <span
      className={clsx("timezone-badge", compact && "timezone-badge--compact", className)}
      title={label}
    >
      <i className="bi bi-clock" aria-hidden="true" />
      {compact ? short : label}
    </span>
  );
}
