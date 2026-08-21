import { QualityBadge } from "./QualityBadge";
import { useAppSelector } from "../hooks/useAppSelector";
import { useTranslation } from "../hooks/useTranslation";
import type { Tag } from "../services/tags";

/** Live G/U/B badges for historical Trends / DataLogger (CA-OQ-12). */
export function HistoricalQualityLegend({ tagNames }: { tagNames: string[] }) {
  const { t } = useTranslation();
  const tagValues = useAppSelector((state) => state.tags.tagValues);

  if (!tagNames.length) {
    return null;
  }

  return (
    <div className="d-flex flex-wrap align-items-center gap-2 py-1" role="group" aria-label={t("quality.legend")}>
      {tagNames.map((name) => {
        const live = tagValues[name] as Tag | undefined;
        const hasLiveQuality =
          (live?.quality !== undefined && live?.quality !== null) || Boolean(live?.quality_label);
        return (
          <span key={name} className="d-inline-flex align-items-center gap-1">
            <span className="small text-muted">{name}</span>
            {hasLiveQuality ? (
              <QualityBadge
                quality={live?.quality}
                qualityLabel={live?.quality_label}
                substatus={live?.quality_substatus}
                stale={Boolean(live?.stale)}
                staleAgeMs={typeof live?.stale_age_ms === "number" ? live.stale_age_ms : null}
              />
            ) : (
              <span className="badge text-bg-secondary" title={t("quality.historicalNone")}>
                {t("quality.na")}
              </span>
            )}
          </span>
        );
      })}
    </div>
  );
}
