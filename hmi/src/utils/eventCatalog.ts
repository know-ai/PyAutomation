type TranslateFn = (key: string, params?: Record<string, string | number>) => string;

const lookup = (t: TranslateFn, section: "message" | "classification", raw: string): string | null => {
  const key = `events.catalog.${section}.${raw}`;
  const translated = t(key);
  return translated === key ? null : translated;
};

/** Map ALM.PERF.* suffixes to performance.alarmTitle keys. */
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
};

const PERF_ALARM_MESSAGE =
  /^Performance alarm (.+) (activated|cleared)$/;

/** OPC UA audit stores ``"{canonical}: {client}"``. */
const MESSAGE_PREFIXES = [
  "OPC UA client connection failed",
  "OPC UA client reconnect failed",
  "OPC UA client disconnected",
  "OPC UA client reconnecting",
  "OPC UA client reconnected",
  "OPC UA client connected",
].sort((a, b) => b.length - a.length);

function translatePerformanceAlarmMessage(value: string, t: TranslateFn): string | null {
  const match = value.match(PERF_ALARM_MESSAGE);
  if (!match) return null;
  const [, suffix, state] = match;
  const titleKey = PERF_ALARM_SUFFIX_TO_TITLE_KEY[suffix];
  const title = titleKey ? t(`performance.alarmTitle.${titleKey}`) : suffix;
  const stateKey =
    state === "activated"
      ? "events.catalog.performanceAlarm.activated"
      : "events.catalog.performanceAlarm.cleared";
  return t(stateKey, { title });
}

export function translateEventClassification(
  value: string | null | undefined,
  t: TranslateFn
): string {
  if (value == null || value === "") return "-";
  return lookup(t, "classification", value) || value;
}

export function translateEventMessage(value: string | null | undefined, t: TranslateFn): string {
  if (value == null || value === "") return "-";
  const exact = lookup(t, "message", value);
  if (exact) return exact;

  const perfAlarm = translatePerformanceAlarmMessage(value, t);
  if (perfAlarm) return perfAlarm;

  for (const prefix of MESSAGE_PREFIXES) {
    if (value === prefix) {
      return lookup(t, "message", prefix) || value;
    }
    const withColon = `${prefix}: `;
    if (value.startsWith(withColon)) {
      const head = lookup(t, "message", prefix) || prefix;
      return `${head}: ${value.slice(withColon.length)}`;
    }
  }
  return value;
}
