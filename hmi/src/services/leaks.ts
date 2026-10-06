import api from "./api";
import { confirmationHeaders } from "./operatorConfirmation";

export type LeakUnit = string | { unit?: string | null } | null | undefined;

export type LeakRow = {
  id: number;
  timestamp?: string | null;
  user_report_timestamp?: string | null;
  is_leak?: boolean | null;
  flow?: number | null;
  flow_unit?: LeakUnit;
  location?: number | null;
  location_unit?: LeakUnit;
  volume?: number | null;
  volume_unit?: LeakUnit;
  size?: number | null;
  size_unit?: LeakUnit;
  state?: string | null;
  detection_source?: string | null;
  operation_mode?: string | null;
  user?: { username?: string | null } | null;
  classified_by?: string | null;
};

export type LeakPage = {
  data: LeakRow[];
  pagination: { total: number; page: number; limit: number; pages: number };
};

export type EngineFalseAlarm = {
  engine: string;
  total: number;
  false_alarms: number;
  rate: number;
};

export type FalseAlarmMetrics = {
  total_alarms: number;
  confirmed_real: number;
  false_alarms: number;
  false_alarm_rate: number;
  p50_response_time_seconds: number;
  p95_response_time_seconds: number;
  mean_response_time_seconds?: number | null;
  mean_location_error_m?: number | null;
  location_accuracy_samples?: number;
  breakdown: EngineFalseAlarm[];
};

export type LeakFilterQuery = {
  greater_than_timestamp: string;
  less_than_timestamp: string;
  timezone: string;
  page: number;
  limit: number;
  state?: string;
  detection_sources?: string[];
};

export type LeakReportBody = {
  is_leak: boolean;
  size?: number;
  volume?: number;
  location?: number;
};

export function filterLeaks(query: LeakFilterQuery, signal?: AbortSignal): Promise<LeakPage> {
  const body: Record<string, string | number | string[]> = {
    greater_than_timestamp: query.greater_than_timestamp,
    less_than_timestamp: query.less_than_timestamp,
    timezone: query.timezone,
    page: query.page,
    limit: query.limit,
    detection_sources: query.detection_sources ?? ["LDS"],
  };
  if (query.state) body.state = query.state;
  return api.post("/leaks/filter_by", body, { signal }).then(({ data }) => data);
}

export function getFalseAlarmMetrics(
  query: { from: string; to: string; timezone: string; engine?: string },
  signal?: AbortSignal
): Promise<FalseAlarmMetrics> {
  return api
    .get("/leaks/metrics/false-alarms", {
      params: { ...query, engine: query.engine ?? "LDS" },
      signal,
    })
    .then(({ data }) => data);
}

export function reportLeak(
  id: number,
  body: LeakReportBody,
  confirmation?: string | null
): Promise<unknown> {
  return api
    .put(`/leaks/report/${id}`, body, confirmationHeaders(confirmation))
    .then(({ data }) => data);
}
