import type { TranslateFn } from "./domainI18n";

export type OpcUaErrorView = {
  code: string;
  title: string;
  detail?: string;
};

const KNOWN_CODES = new Set([
  "connection_refused",
  "connection_timeout",
  "host_unresolved",
  "host_unreachable",
  "session_closed",
  "not_connected",
  "client_not_found",
  "browse_failed",
  "add_failed",
  "update_failed",
  "remove_failed",
  "duplicate_name",
  "not_owned",
  "identity_missing",
  "discovery_failed",
  "invalid_request",
  "unknown",
]);

const CLASSIFIERS: Array<[string, string[]]> = [
  ["connection_refused", ["connection refused", "errno 111", "errno 61", "actively refused"]],
  ["connection_timeout", ["timed out", "timeout", "errno 110", "etimedout"]],
  ["host_unresolved", ["name or service not known", "nodename nor servname", "getaddrinfo", "could not translate host"]],
  ["host_unreachable", ["network is unreachable", "no route to host", "errno 101", "errno 113"]],
  ["session_closed", ["badsessionid", "session closed", "connection closed", "broken pipe"]],
  ["not_connected", ["cannot unpack", "nonetype", "not connected", "is not connected"]],
  ["duplicate_name", ["duplicated", "already exists", "duplicate"]],
  ["not_owned", ["not owned", "another edge", "another node", "belongs to another"]],
  ["identity_missing", ["identity is not configured"]],
  ["browse_failed", ["failed to retrieve node tree", "failed to retrieve node children"]],
  ["discovery_failed", ["servers not found", "failed to discover"]],
];

type AnyRecord = Record<string, unknown>;

function asRecord(value: unknown): AnyRecord | null {
  return value && typeof value === "object" && !Array.isArray(value) ? (value as AnyRecord) : null;
}

function asText(value: unknown): string {
  return typeof value === "string" ? value.trim() : "";
}

function classifyText(text: string): string | null {
  const lower = text.toLowerCase();
  for (const [code, needles] of CLASSIFIERS) {
    if (needles.some((needle) => lower.includes(needle))) return code;
  }
  return null;
}

function isTechnicalDump(text: string): boolean {
  const lower = text.toLowerCase();
  return (
    lower.includes("failed to ") ||
    lower.includes("errno") ||
    lower.includes("traceback") ||
    lower.includes("nonetype") ||
    lower.includes("cannot unpack") ||
    text.includes("{'") ||
    text.includes('{"') ||
    /Error: \[/.test(text)
  );
}

function extractPayload(error: unknown): AnyRecord {
  const err = error as {
    code?: string;
    message?: string;
    response?: { data?: unknown };
    params?: AnyRecord;
  };
  const data = asRecord(err?.response?.data);
  if (data) return data;
  if (asRecord(error)) return error as AnyRecord;
  return { message: asText(err?.message) };
}

function extractParams(payload: AnyRecord): Record<string, string> {
  const raw = asRecord(payload.params) || {};
  const params: Record<string, string> = {};
  for (const key of ["client", "host", "port", "url"]) {
    const value = raw[key] ?? payload[key];
    if (value != null && String(value).trim()) params[key] = String(value);
  }
  if (!params.url) {
    const message = asText(payload.message) + " " + asText(payload.error);
    const match = message.match(/opc\.tcp:\/\/[^\s'"}]+/i);
    if (match) params.url = match[0];
  }
  return params;
}

function endpointDetail(t: TranslateFn, params: Record<string, string>): string | undefined {
  if (params.host && params.port) {
    return t("communications.errors.endpoint", params);
  }
  if (params.url) {
    return t("communications.errors.endpointUrl", params);
  }
  if (params.client) {
    return t("communications.errors.clientName", params);
  }
  return undefined;
}

export function isOpcUaConnectivityCode(code: string): boolean {
  return [
    "connection_refused",
    "connection_timeout",
    "host_unresolved",
    "host_unreachable",
    "session_closed",
    "not_connected",
    "client_not_found",
    "discovery_failed",
  ].includes(code);
}

export function translateOpcUaError(
  t: TranslateFn,
  error: unknown,
  fallbackKey = "communications.errors.unknown"
): OpcUaErrorView {
  if ((error as { code?: string })?.code === "ECONNABORTED") {
    return { code: "connection_timeout", title: t("communications.connectTimeout") };
  }

  const payload = extractPayload(error);
  const params = extractParams(payload);
  const rawMessage = asText(payload.message) || asText(payload.error) || asText((error as { message?: string })?.message);
  const codeFromPayload = asText(payload.code);
  const code =
    (KNOWN_CODES.has(codeFromPayload) ? codeFromPayload : null) ||
    classifyText(rawMessage) ||
    classifyText(JSON.stringify(payload)) ||
    "unknown";

  const key = `communications.errors.${code}`;
  let title = t(key, params);
  if (title === key) {
    title = t(fallbackKey, params);
  }
  if (title === fallbackKey && rawMessage && !isTechnicalDump(rawMessage)) {
    title = rawMessage;
  }

  return {
    code,
    title,
    detail: endpointDetail(t, params),
  };
}
