import type { Alarm } from "../services/alarms";

export type AlarmFormData = {
  name: string;
  tag: string;
  alarm_type: string;
  trigger_value: string;
  description: string;
  display_name: string;
  on_delay: string;
  off_delay: string;
};

const TYPE_ALIASES: Record<string, string> = {
  BOOL: "BOOL",
  B: "BOOL",
  HIGH: "HIGH",
  H: "HIGH",
  HI: "HIGH",
  "HIGH-HIGH": "HIGH-HIGH",
  HH: "HIGH-HIGH",
  LOW: "LOW",
  L: "LOW",
  LO: "LOW",
  "LOW-LOW": "LOW-LOW",
  LL: "LOW-LOW",
};

export function normalizeAlarmType(raw: unknown): string {
  const token = String(raw || "").trim().toUpperCase();
  return TYPE_ALIASES[token] || token || "BOOL";
}

export function pickTriggerValue(alarm: Alarm): unknown {
  if (alarm.trigger_value !== undefined && alarm.trigger_value !== null) {
    return alarm.trigger_value;
  }
  if (alarm.alarm_setpoint?.value !== undefined && alarm.alarm_setpoint.value !== null) {
    return alarm.alarm_setpoint.value;
  }
  return undefined;
}

export function formatTriggerForForm(alarmType: string, value: unknown): string {
  if (value === undefined || value === null || value === "") {
    return "";
  }
  if (alarmType === "BOOL") {
    if (value === true || value === 1 || value === "1" || value === "true" || value === "True") {
      return "true";
    }
    if (value === false || value === 0 || value === "0" || value === "false" || value === "False") {
      return "false";
    }
    return "";
  }
  return String(value);
}

export function tagNameOf(alarm: Alarm): string {
  const tag = alarm.tag as unknown;
  if (typeof tag === "string") return tag;
  if (tag && typeof tag === "object" && "name" in (tag as object)) {
    return String((tag as { name?: string }).name || "");
  }
  return "";
}

export function alarmToFormData(alarm: Alarm): AlarmFormData {
  const alarmType = normalizeAlarmType(alarm.alarm_type || alarm.alarm_setpoint?.type || "BOOL");
  const delay = (raw: unknown, fallback = "0") =>
    raw !== undefined && raw !== null && raw !== "" ? String(raw) : fallback;
  return {
    name: alarm.name || "",
    tag: tagNameOf(alarm),
    alarm_type: alarmType,
    trigger_value: formatTriggerForForm(alarmType, pickTriggerValue(alarm)),
    description: alarm.description || "",
    display_name: alarm.display_name || "",
    on_delay: delay(alarm.on_delay),
    off_delay: delay(alarm.off_delay),
  };
}
