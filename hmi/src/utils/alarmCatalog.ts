type TranslateFn = (key: string, params?: Record<string, string | number>) => string;

/** Map ALM.PERF.* suffixes to performance.alarmTitle keys. */
const PERF_ALARM_SUFFIX_TO_TITLE_KEY: Record<string, string> = {
  "ALM.PERF.CPU": "cpu",
  "ALM.PERF.DISK": "disk",
  "ALM.PERF.SAF_QUEUE": "saf_queue",
  "ALM.PERF.SAF_LAG": "saf_lag",
  "ALM.PERF.METRICS_AGE": "metrics_age",
  "ALM.PERF.DB_CONN": "db_conn",
  "ALM.PERF.HTTP_5XX": "http_5xx",
};

const OPCUA_CONNECTION_LOST =
  /^OPC UA client '(.+)' connection lost$/;
const PERF_THRESHOLD =
  /^System · (.+)\. Triggers when (.+) ≥ (.+)\.?$/;

function endsWithAlarmSuffix(name: string, suffix: string): boolean {
  return name === suffix || name.endsWith(`.${suffix}`);
}

/**
 * Translate known system alarm descriptions for HMI display.
 * Operator-authored descriptions pass through unchanged.
 */
export function translateAlarmDescription(
  description: string | null | undefined,
  alarmName: string | null | undefined,
  t: TranslateFn
): string {
  const desc = (description || "").trim();
  const name = (alarmName || "").trim();
  if (!desc && !name) return "-";

  if (endsWithAlarmSuffix(name, "ALM.DB.Connection") || desc === "Historian database connection lost") {
    return t("alarms.catalog.dbConnectionLost");
  }

  if (endsWithAlarmSuffix(name, "ALM.NTP.OutOfSync") || desc === "Edge clock out of sync with plant NTP") {
    return t("alarms.catalog.ntpOutOfSync");
  }

  for (const [suffix, titleKey] of Object.entries(PERF_ALARM_SUFFIX_TO_TITLE_KEY)) {
    if (!endsWithAlarmSuffix(name, suffix)) continue;
    const title = t(`performance.alarmTitle.${titleKey}`);
    const match = desc.match(PERF_THRESHOLD);
    if (match) {
      return t("alarms.catalog.performanceThreshold", {
        title,
        field: match[2],
        threshold: match[3],
      });
    }
    return t("alarms.catalog.performance", { title });
  }

  const opcuaFromDesc = desc.match(OPCUA_CONNECTION_LOST);
  if (opcuaFromDesc) {
    return t("alarms.catalog.opcuaConnectionLost", { client: opcuaFromDesc[1] });
  }
  const opcuaFromName = name.match(/(?:^|\.)ALM\.OPCUA\.(.+)$/);
  if (opcuaFromName) {
    return t("alarms.catalog.opcuaConnectionLost", { client: opcuaFromName[1] });
  }

  const exactKey = `alarms.catalog.exact.${desc}`;
  const exact = t(exactKey);
  if (exact !== exactKey) return exact;

  return desc || "-";
}
