import api from "./api";

export type LdsVerdict = "TRUE_POSITIVE" | "FALSE_POSITIVE" | "FALSE_POSITIVE_AUTO" | "MISSED_LEAK";

export type LdsValidationRow = {
  id?: number;
  timestamp?: number | null;
  engine?: string;
  likelihood?: number | null;
  detection_source?: string;
  source_kind?: "automatic" | "manual";
  operator_verdict?: LdsVerdict | null;
  field_location?: number | null;
  field_flow?: number | null;
  field_size?: number | null;
  notes?: string | null;
  validated_at?: number | null;
  classified_by?: string | null;
  classified_by_kind?: "system" | "operator";
  automatic?: boolean;
};

export type LdsValidationPage = {
  events: LdsValidationRow[];
  total: number;
  limit?: number;
  offset?: number;
  range?: string;
};

export async function getLdsValidationPending(): Promise<LdsValidationPage> {
  const { data } = await api.get("/LDS/validation/pending", { timeout: 8000 });
  return data as LdsValidationPage;
}

export async function getLdsValidationHistory(params: {
  range?: string;
  limit?: number;
  offset?: number;
  engine?: string;
  verdict?: string;
}): Promise<LdsValidationPage> {
  const { data } = await api.get("/LDS/validation/history", { params, timeout: 8000 });
  return data as LdsValidationPage;
}

export async function classifyLdsEvent(body: {
  leak_id: number;
  verdict: "TRUE_POSITIVE" | "FALSE_POSITIVE";
  field_location?: number | null;
  field_flow?: number | null;
  field_size?: number | null;
  notes?: string;
}): Promise<LdsValidationRow> {
  const { data } = await api.post("/LDS/validation/classify", body, { timeout: 8000 });
  return data as LdsValidationRow;
}

export async function reportLdsMissedLeak(body: {
  timestamp?: string;
  engine?: string;
  location?: number | null;
  flow?: number | null;
  size?: number | null;
  notes?: string;
}): Promise<LdsValidationRow> {
  const { data } = await api.post("/LDS/validation/missed", body, { timeout: 8000 });
  return data as LdsValidationRow;
}
