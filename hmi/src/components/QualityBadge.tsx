import { memo, useMemo } from "react";
import { useTranslation } from "../hooks/useTranslation";
import {
  qualityBadgeLetter,
  qualityBadgeTone,
  resolveQualityLabel,
  formatStaleAge,
} from "../utils/qualityBadge";

type QualityBadgeProps = {
  quality?: number | string | null;
  qualityLabel?: string | null;
  substatus?: string | null;
  stale?: boolean;
  staleAgeMs?: number | null;
  className?: string;
};

export const QualityBadge = memo(function QualityBadge({
  quality,
  qualityLabel,
  substatus,
  stale,
  staleAgeMs,
  className = "",
}: QualityBadgeProps) {
  const { t } = useTranslation();
  const label = resolveQualityLabel(quality, qualityLabel);
  const letter = qualityBadgeLetter(label);
  const tone = qualityBadgeTone(label);
  const title = useMemo(() => {
    const parts = [t(`quality.${label.toLowerCase()}`)];
    if (substatus) {
      parts.push(substatus);
    }
    if (stale) {
      const age = formatStaleAge(staleAgeMs);
      parts.push(age ? t("quality.staleAge", { age }) : t("quality.stale"));
    }
    return parts.join(" · ");
  }, [label, substatus, stale, staleAgeMs, t]);

  return (
    <span
      className={`badge text-bg-${tone} ${className}`.trim()}
      title={title}
      aria-label={title}
    >
      {letter}
      {stale ? "*" : ""}
    </span>
  );
});
