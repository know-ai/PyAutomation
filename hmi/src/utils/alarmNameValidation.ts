/** Client-side mirror of automation.alarm_naming.qualify_user_alarm_name (HMI create form). */

export type AlarmNameValidation = {
  ok: boolean;
  message?: string;
  qualifiedName?: string;
  baseName?: string;
};

export function alarmNameBaseSegment(name: string): string {
  const parts = (name || "").trim().split(".").filter(Boolean);
  return parts.length ? parts[parts.length - 1] : (name || "").trim();
}

export function validateUserAlarmNameInput(
  name: string,
  site: string,
  area: string
): AlarmNameValidation {
  const raw = (name || "").trim();
  if (!raw) {
    return { ok: false, message: "required" };
  }
  if (!site || !area) {
    return { ok: true, qualifiedName: raw, baseName: alarmNameBaseSegment(raw) };
  }

  const prefix = `alarm.${site}.${area}`;
  const parts = raw.split(".").filter(Boolean);

  if (parts.length === 1) {
    const base = parts[0];
    return {
      ok: true,
      qualifiedName: `${prefix}.${base}`,
      baseName: base,
    };
  }
  if (parts.length === 2) {
    return {
      ok: false,
      message: "twoParts",
      qualifiedName: `${prefix}.${parts[parts.length - 1]}`,
      baseName: parts[parts.length - 1],
    };
  }
  if (parts.length === 4) {
    const [lead, inputSite, inputArea, base] = parts;
    if (lead !== "alarm") {
      return { ok: false, message: "prefix", qualifiedName: `${prefix}.${base}`, baseName: base };
    }
    if (inputSite !== site && inputArea !== area) {
      return { ok: false, message: "mismatch", qualifiedName: `${prefix}.${base}`, baseName: base };
    }
    if (inputArea !== area) {
      return { ok: false, message: "areaMismatch", qualifiedName: `${prefix}.${base}`, baseName: base };
    }
    if (inputSite !== site) {
      return { ok: false, message: "siteMismatch", qualifiedName: `${prefix}.${base}`, baseName: base };
    }
    return { ok: true, qualifiedName: raw, baseName: base };
  }
  if (parts.length > 4) {
    return { ok: false, message: "reserved", baseName: parts[parts.length - 1] };
  }
  return { ok: false, message: "invalid", baseName: parts[parts.length - 1] };
}
