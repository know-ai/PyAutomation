import api from "./api";

export type LdsTimeRange = "1h" | "6h" | "12h" | "24h" | "7d" | "30d" | "90d";
export type LdsPageSize = 10 | 25 | 50 | 100;

export type LdsEventRow = {
  id?: number;
  timestamp?: number;
  engine_name?: string;
  event_type?: string;
  from_state?: string | null;
  to_state?: string | null;
  likelihood_value?: number | null;
  operator_verified?: boolean | null;
  current_state?: string | null;
};

export type LdsEventStats = {
  by_engine?: Record<string, number>;
  by_engine_type?: Record<string, { total?: number; pre_alarm?: number; leak?: number; other?: number }>;
  by_type?: Record<string, number>;
  by_state?: Record<string, number>;
  by_operation_state?: Record<string, number>;
  by_state_unknown?: number;
  by_state_note?: string | null;
  timeseries?: Array<Record<string, string | number>>;
  timeseries_unit?: string;
  stamped_state_total?: number;
};

export type LdsEventsPage = {
  events: LdsEventRow[];
  total: number;
  limit: number;
  offset: number;
  range: string;
  engine?: string | null;
  stats?: LdsEventStats;
};

export type LdsEngineAlarmCount = number | { total?: number; pre_alarm?: number; leak?: number };

export type LdsDynamicMetrics = {
  range?: string;
  precision?: number | null;
  false_alarm_rate?: number | null;
  sensitivity?: number | null;
  robustness?: number | null;
  robustness_detail?: {
    score?: number | null;
    states_covered?: string[];
    diagnostics_covered?: string[];
    diagnostics?: Record<string, boolean>;
    idle_engines?: string[];
    note?: string;
  } | null;
  true_positives?: number;
  false_positives?: number;
  false_negatives?: number;
  unclassified?: number;
  recent_validations?: Array<{
    id?: number;
    verdict?: string;
    classified_by?: string | null;
    validated_at?: number | null;
    engine?: string;
  }>;
  total_alarms?: number;
  total_alarms_24h?: number | null;
  alarms_by_engine?: Record<string, LdsEngineAlarmCount>;
  alarms_by_state?: Record<string, Record<string, number>>;
  false_alarm_rate_by_engine?: Record<string, number | null>;
  hourly?: Array<{ t?: string; v?: number }>;
  source?: string;
  note?: string;
};

export type LdsThresholdRow = {
  engine: string;
  SS?: number | null;
  SI?: number | null;
  TS?: number | null;
  unit?: string;
  state?: string;
};

export async function getLdsEvents(params: {
  range?: string;
  limit?: number;
  offset?: number;
  engine?: string;
  stats?: boolean;
}): Promise<LdsEventsPage> {
  const { data } = await api.get("/LDS/events", { params, timeout: 8000 });
  return data as LdsEventsPage;
}

export async function getLdsDynamicMetrics(range = "24h"): Promise<LdsDynamicMetrics> {
  const { data } = await api.get("/LDS/metrics/dynamic", { params: { range }, timeout: 8000 });
  return data as LdsDynamicMetrics;
}

export async function getLdsThresholds(): Promise<LdsThresholdRow[]> {
  const { data } = await api.get("/LDS/thresholds", { timeout: 8000 });
  const rows = (data as { thresholds?: LdsThresholdRow[] })?.thresholds;
  return Array.isArray(rows) ? rows : [];
}
