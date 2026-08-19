import api from "./api";

export type ClockConfig = {
  ntp_servers?: string;
  ntp_servers_list?: string[];
  ntp_check_interval_s?: number;
  ntp_warn_offset_ms?: number;
  ntp_alarm_offset_ms?: number;
  ntp_fail_closed?: boolean;
  ntp_enabled?: boolean;
  ntp_step_threshold_ms?: number;
  ntp_auth_type?: "none" | "symmetric" | "nts";
  effective_enabled?: boolean;
};

export type ClockStatus = {
  enabled?: boolean;
  synced?: boolean;
  warn?: boolean;
  offset_ms?: number | null;
  delay_ms?: number | null;
  stratum?: number | null;
  server_used?: string | null;
  last_check_utc?: string | null;
  next_check_utc?: string | null;
  check_interval_s?: number;
  warn_offset_ms?: number;
  alarm_offset_ms?: number;
  step_threshold_ms?: number;
  fail_closed?: boolean;
  consecutive_failures?: number;
  last_error?: string | null;
  last_address_used?: string | null;
  auth_required_detected?: boolean;
  authentication_required?: boolean;
  jump_detected?: boolean;
  protocol_version?: string;
  host_time_utc?: string;
  node_id?: string | null;
  config?: ClockConfig;
};

export type ClockCheckResponse = {
  ok: boolean;
  message?: string;
  status?: ClockStatus;
};

export const getClockSettings = async (): Promise<ClockConfig> => {
  const { data } = await api.get("/settings/clock");
  return data;
};

export const updateClockSettings = async (payload: Partial<ClockConfig>): Promise<ClockConfig> => {
  const { data } = await api.put("/settings/clock", payload);
  return data;
};

export const getClockStatus = async (): Promise<ClockStatus> => {
  const { data } = await api.get("/system/clock");
  return data;
};

export const forceClockCheck = async (): Promise<ClockCheckResponse> => {
  const { data } = await api.post("/system/clock/check");
  return data;
};

export type ClockHealth = {
  enabled?: boolean;
  synced?: boolean;
  warn?: boolean;
  offset_ms?: number | null;
  last_error?: string | null;
  last_address_used?: string | null;
  auth_required_detected?: boolean;
  CLOCK_OFFSET_MS?: number | null;
  NTP_SYNCED?: boolean;
};

export const getClockHealth = async (): Promise<ClockHealth> => {
  const { data } = await api.get("/health/system", { timeout: 2500 });
  return data?.clock || {};
};
