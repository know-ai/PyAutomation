import api from "./api";
import type { LdsDynamicMetrics } from "./ldsAnalytics";
import type { TrendPoint } from "./performanceTrends";

export type LdsEngineRow = {
  name: string;
  state: string;
  likelihood: number | null;
  threshold: number | null;
  leak_flow: number | null;
  leak_location: number | null;
  leak_size: number | null;
  flow?: number | null;
  location?: number | null;
  size?: number | null;
  pressure_inputs?: string | null;
  is_degraded: boolean;
  bayes?: Record<string, unknown>;
};

export type LdsCoverageMap = Record<string, { SS?: boolean; SI?: boolean; TS?: boolean }>;

export type LdsDashboardSnapshot = {
  timestamp?: number;
  phase?: string;
  lds_state?: string;
  lds_likelihood?: number | null;
  lds_threshold?: number | null;
  lds_operation?: string;
  lds_operation_key?: string;
  engines_coverage?: LdsCoverageMap;
  total_events?: number;
  bayesian?: {
    enabled?: boolean;
    posterior?: number | null;
    used_motor_count?: number;
    negative_motor_count?: number;
    motors?: Record<string, { probability?: number; triggered?: boolean; evidence?: string }>;
  };
  engines?: Record<string, LdsEngineRow>;
  api_sensitivity?: Record<string, unknown>;
  api_accuracy?: Record<string, unknown>;
  api_reliability?: Record<string, unknown>;
  api_robustness?: Record<string, unknown> & {
    score?: number | null;
    states_covered?: string[];
    diagnostics_covered?: string[];
    idle_engines?: string[];
  };
  motor_capabilities?: Record<string, { detection?: boolean; location?: boolean; size?: boolean; flow?: boolean }>;
  motor_operational?: Record<string, string>;
  bayesian_coverage?: Record<string, boolean>;
  trfl_compliance?: Record<string, unknown>;
  trend?: Array<TrendPoint & { threshold?: number }>;
  recent_events?: Array<{
    timestamp?: number;
    engine?: string;
    event?: string;
    likelihood?: number | null;
  }>;
  alarms?: Array<{ name?: string; state?: string; priority?: number }>;
  dynamic?: LdsDynamicMetrics | null;
};

export async function getLdsDashboardSnapshot(): Promise<LdsDashboardSnapshot> {
  const { data } = await api.get("/LDS/dashboard", { timeout: 4000 });
  return data as LdsDashboardSnapshot;
}
