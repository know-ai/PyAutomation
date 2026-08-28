type TranslateFn = (key: string, params?: Record<string, string | number>) => string;

/** Map ALM.PERF.* suffixes → performance.alarmTitle keys. */
const PERF_ALARM_SUFFIX_TO_TITLE_KEY: Record<string, string> = {
  "ALM.PERF.CPU": "cpu",
  "ALM.PERF.DISK": "disk",
  "ALM.PERF.SAF_QUEUE": "saf_queue",
  "ALM.PERF.SAF_LAG": "saf_lag",
  "ALM.PERF.METRICS_AGE": "metrics_age",
  "ALM.PERF.DB_CONN": "db_conn",
  "ALM.PERF.HTTP_5XX": "http_5xx",
  "ALM.PERF.FIELD_STALE": "field_stale",
  "ALM.PERF.SAF_DEADLETTER": "saf_deadletter",
  "ALM.PERF.HUB_LAG": "hub_lag",
  "ALM.PERF.SAF_SHED": "saf_shed",
  "ALM.PERF.SAF_INGEST": "saf_ingest",
  "ALM.PERF.SAF_RATE": "saf_rate",
  "ALM.PERF.SSD": "ssd",
  "ALM.PERF.NTP": "ntp",
  "ALM.PERF.NODE_DOWN": "node_down",
};

/** Snapshot metric codes → locale keys under alarms.catalog.fields.* */
const PERF_FIELD_TO_KEY: Record<string, string> = {
  HOST_CPU_PERCENT: "cpu",
  HOST_DISK_USED_PERCENT: "disk",
  SAF_QUEUE_DEPTH: "safQueue",
  SAF_REPLICATION_LAG_MS: "safLag",
  METRICS_AGE_MS: "metricsAge",
  DB_ACTIVE_CONNECTIONS: "dbConn",
  HTTP_5XX_1M: "http5xx",
  FIELD_STALE: "fieldStale",
  SAF_DEADLETTER_COUNT: "safDeadletter",
  HUB_LAG_MS: "hubLag",
  SAF_SHED: "safShed",
  SAF_INGEST_AGE_MS: "safIngest",
  SAF_RATE_MISMATCH: "safRate",
  HOST_SSD_ALARM: "ssd",
  HOST_NTP_ABS_OFFSET_MS: "ntp",
  HOST_PEER_DOWN: "peerDown",
};

const OPCUA_CONNECTION_LOST = /^OPC UA client '(.+)' connection lost$/i;
const PERF_THRESHOLD =
  /(?:Triggers when|Se dispara cuando)\s+(.+?)\s*[≥>=]\s*(.+?)\.?\s*$/i;
const QUALITY_DESC = /^Signal quality BAD\/stale on '(.+)'$/i;

function endsWithAlarmSuffix(name: string, suffix: string): boolean {
  return name === suffix || name.endsWith(`.${suffix}`);
}

function translatePerfField(field: string, t: TranslateFn): string {
  const key = PERF_FIELD_TO_KEY[field.trim()];
  if (!key) return field.trim();
  const label = t(`alarms.catalog.fields.${key}`);
  return label.startsWith("alarms.catalog.fields.") ? field.trim() : label;
}

/**
 * Human-readable, locale-aware description for PyAutomation system alarms.
 * Operator-authored descriptions pass through unchanged.
 *
 * Matching is **name-first** (stable across languages / description edits).
 */
export function translateAlarmDescription(
  description: string | null | undefined,
  alarmName: string | null | undefined,
  t: TranslateFn
): string {
  const desc = (description || "").trim();
  const name = (alarmName || "").trim();
  if (!desc && !name) return "-";

  if (endsWithAlarmSuffix(name, "ALM.DB.Connection")) {
    return t("alarms.catalog.dbConnectionLost");
  }

  if (endsWithAlarmSuffix(name, "ALM.NTP.OutOfSync")) {
    return t("alarms.catalog.ntpOutOfSync");
  }

  if (endsWithAlarmSuffix(name, "ALM.CATALOG.SyncFailed")) {
    return t("alarms.catalog.catalogSyncFailed");
  }
  if (endsWithAlarmSuffix(name, "ALM.CATALOG.OrphanRows")) {
    return t("alarms.catalog.catalogOrphanRows");
  }
  if (endsWithAlarmSuffix(name, "ALM.CATALOG.Conflict")) {
    return t("alarms.catalog.catalogConflict");
  }
  if (endsWithAlarmSuffix(name, "ALM.CATALOG.LocalOnly")) {
    return t("alarms.catalog.catalogLocalOnly");
  }

  for (const [suffix, titleKey] of Object.entries(PERF_ALARM_SUFFIX_TO_TITLE_KEY)) {
    if (!endsWithAlarmSuffix(name, suffix)) continue;
    const title = t(`performance.alarmTitle.${titleKey}`);
    const match = desc.match(PERF_THRESHOLD);
    if (match) {
      const threshold = match[2].trim();
      // Ignore poisoned placeholders until the backend refreshes the description.
      const numericPart = threshold.replace(/(?:%|ms|\/min)$/i, "");
      if (!/^(none|null|undefined|\?)$/i.test(numericPart)) {
        return t("alarms.catalog.performanceThreshold", {
          title,
          field: translatePerfField(match[1], t),
          threshold,
        });
      }
    }
    return t("alarms.catalog.performance", { title });
  }

  const qualityFromName = name.match(/(?:^|\.)ALM\.QUALITY\.(.+)$/);
  if (qualityFromName) {
    const tag = qualityFromName[1].replace(/_/g, ".");
    return t("alarms.catalog.qualityDegraded", { tag });
  }
  const qualityFromDesc = desc.match(QUALITY_DESC);
  if (qualityFromDesc) {
    return t("alarms.catalog.qualityDegraded", { tag: qualityFromDesc[1] });
  }

  const opcuaFromName = name.match(/(?:^|\.)ALM\.OPCUA\.(.+)$/);
  if (opcuaFromName) {
    return t("alarms.catalog.opcuaConnectionLost", {
      client: opcuaFromName[1].replace(/_/g, " "),
    });
  }
  const opcuaFromDesc = desc.match(OPCUA_CONNECTION_LOST);
  if (opcuaFromDesc) {
    return t("alarms.catalog.opcuaConnectionLost", { client: opcuaFromDesc[1] });
  }

  // Legacy exact English description keys (optional extras in locales).
  if (desc) {
    const exactKey = `alarms.catalog.exact.${desc}`;
    const exact = t(exactKey);
    if (exact !== exactKey) return exact;
  }

  // Fallback: known English system phrases when name was renamed/missing.
  if (desc === "Historian database connection lost") {
    return t("alarms.catalog.dbConnectionLost");
  }
  if (desc === "Edge clock out of sync with plant NTP") {
    return t("alarms.catalog.ntpOutOfSync");
  }
  if (desc === "Catalog sync failed") {
    return t("alarms.catalog.catalogSyncFailed");
  }
  if (desc === "Catalog orphan rows") {
    return t("alarms.catalog.catalogOrphanRows");
  }
  if (desc === "Catalog sync conflict") {
    return t("alarms.catalog.catalogConflict");
  }
  if (desc === "Catalog local-only too long") {
    return t("alarms.catalog.catalogLocalOnly");
  }

  return desc || "-";
}

/** True when the alarm is a PyAutomation-managed system alarm (by name). */
export function isSystemAlarmName(alarmName: string | null | undefined): boolean {
  const name = (alarmName || "").trim();
  if (!name) return false;
  return (
    endsWithAlarmSuffix(name, "ALM.DB.Connection") ||
    endsWithAlarmSuffix(name, "ALM.NTP.OutOfSync") ||
    /(?:^|\.)ALM\.(PERF|CATALOG|OPCUA|QUALITY)\./.test(name)
  );
}
