export const DISPLAY_TIMEZONE_KEY = "display_timezone";

export type DisplayTimezoneMode = "plant" | "local";

const hasExplicitOffset = (value: string): boolean =>
  /[zZ]$/.test(value.trim()) || /[+-]\d{2}:\d{2}$/.test(value.trim()) || /T/.test(value);

export function getBrowserTimeZone(): string {
  try {
    return Intl.DateTimeFormat().resolvedOptions().timeZone || "";
  } catch (_e) {
    return "";
  }
}

export function loadDisplayTimezoneMode(): DisplayTimezoneMode {
  try {
    const saved = localStorage.getItem(DISPLAY_TIMEZONE_KEY);
    if (saved === "plant" || saved === "local") {
      return saved;
    }
  } catch (_e) {
    // ignore
  }
  return getBrowserTimeZone() ? "local" : "plant";
}

export function persistDisplayTimezoneMode(mode: DisplayTimezoneMode): void {
  try {
    localStorage.setItem(DISPLAY_TIMEZONE_KEY, mode);
  } catch (_e) {
    // ignore
  }
}

type DateParts = {
  year: number;
  month: number;
  day: number;
  hour: number;
  minute: number;
  second: number;
  millisecond: number;
};

const partNumber = (parts: Intl.DateTimeFormatPart[], type: string, fallback = "0"): number =>
  Number(parts.find((part) => part.type === type)?.value || fallback);

export function getTimeZoneParts(date: Date, timeZone: string): DateParts {
  const parts = new Intl.DateTimeFormat("en-US", {
    timeZone: timeZone || undefined,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hourCycle: "h23",
    fractionalSecondDigits: 3,
  }).formatToParts(date);
  let hour = partNumber(parts, "hour");
  if (hour === 24) hour = 0;
  return {
    year: partNumber(parts, "year"),
    month: partNumber(parts, "month"),
    day: partNumber(parts, "day"),
    hour,
    minute: partNumber(parts, "minute"),
    second: partNumber(parts, "second"),
    millisecond: partNumber(parts, "fractionalSecond"),
  };
}

const pad2 = (value: number): string => String(value).padStart(2, "0");
const pad3 = (value: number): string => String(value).padStart(3, "0");

/** Value for `<input type="datetime-local" step="1">` including seconds. */
export function formatDateTimeLocalInput(date: Date): string {
  return `${date.getFullYear()}-${pad2(date.getMonth() + 1)}-${pad2(date.getDate())}T${pad2(date.getHours())}:${pad2(date.getMinutes())}:${pad2(date.getSeconds())}`;
}

export function formatInstantForBackend(date: Date, timeZone: string): string {
  const parts = getTimeZoneParts(date, timeZone);
  return `${parts.year}-${pad2(parts.month)}-${pad2(parts.day)} ${pad2(parts.hour)}:${pad2(parts.minute)}:${pad2(parts.second)}.00`;
}

export function formatDateTimeLocalForBackend(dateTimeString: string, timeZone: string): string {
  if (!dateTimeString) return "";
  const normalized = dateTimeString.length === 16 ? `${dateTimeString}:00` : dateTimeString;
  const asLocal = new Date(normalized);
  if (Number.isNaN(asLocal.getTime())) {
    return dateTimeString.replace("T", " ") + (dateTimeString.includes(":") ? ":00.00" : "");
  }
  return formatInstantForBackend(asLocal, timeZone);
}

export function parseTimestamp(value: string | Date): Date {
  if (value instanceof Date) return value;
  return new Date(value);
}

export function formatTimestamp(value: string | Date | null | undefined, timeZone: string): string {
  if (value == null || value === "") return "";
  if (typeof value === "string" && !hasExplicitOffset(value)) {
    return value;
  }
  const date = parseTimestamp(value);
  if (Number.isNaN(date.getTime())) {
    return typeof value === "string" ? value : "";
  }
  try {
    return new Intl.DateTimeFormat(undefined, {
      timeZone: timeZone || undefined,
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
      hour12: false,
      fractionalSecondDigits: 3,
    }).format(date);
  } catch (_e) {
    return date.toISOString();
  }
}

/** Date whose local wall-clock equals the instant in ``timeZone`` (Plotly). */
export function toDisplayDate(value: string | Date, timeZone: string): Date {
  const date = parseTimestamp(value);
  if (Number.isNaN(date.getTime()) || !timeZone) return date;
  const browserTz = getBrowserTimeZone();
  if (!browserTz || timeZone === browserTz) return date;
  const parts = getTimeZoneParts(date, timeZone);
  return new Date(
    parts.year,
    parts.month - 1,
    parts.day,
    parts.hour,
    parts.minute,
    parts.second,
    parts.millisecond
  );
}

export type UiLocale = "en" | "es";

const padStamp = (value: number): string => String(value).padStart(2, "0");

function assembleLocaleStamp(
  year: string,
  month: string,
  day: string,
  hour: string,
  minute: string,
  second: string,
  locale: UiLocale,
  fractional?: string
): string {
  const date = locale === "es" ? `${day}/${month}/${year}` : `${month}/${day}/${year}`;
  const time = `${hour}:${minute}:${second}`;
  return fractional ? `${date} ${time}.${fractional}` : `${date} ${time}`;
}

function toFractionalSeconds(rawDigits: string | undefined, digits: 0 | 3): string | undefined {
  if (digits !== 3) return undefined;
  if (!rawDigits) return "000";
  return rawDigits.padEnd(3, "0").slice(0, 3);
}

export type OperatorTimestampOptions = {
  /** 0 (default): seconds only. 3: milliseconds, e.g. DataLogger. */
  fractionalDigits?: 0 | 3;
};

/**
 * Format historian timestamps like the header clock:
 * Spanish → DD/MM/YYYY HH:MM:SS; English → MM/DD/YYYY HH:MM:SS.
 * Backend serializes ``%m/%d/%Y, %H:%M:%S.%f`` (US order, microseconds)
 * or ISO ``YYYY-MM-DD HH:MM:SS.%f``.
 * Operator tables never need sub-second precision unless ``fractionalDigits`` is set.
 */
export function formatOperatorTimestamp(
  value: string | Date | null | undefined,
  locale: UiLocale,
  options?: OperatorTimestampOptions
): string {
  const fractionalDigits = options?.fractionalDigits ?? 0;
  if (value == null || value === "") return "-";
  if (value instanceof Date) {
    if (Number.isNaN(value.getTime())) return "-";
    return assembleLocaleStamp(
      String(value.getFullYear()),
      padStamp(value.getMonth() + 1),
      padStamp(value.getDate()),
      padStamp(value.getHours()),
      padStamp(value.getMinutes()),
      padStamp(value.getSeconds()),
      locale,
      toFractionalSeconds(pad3(value.getMilliseconds()), fractionalDigits)
    );
  }

  const raw = String(value).trim();
  const us = raw.match(
    /^(\d{1,2})\/(\d{1,2})\/(\d{4}),?\s+(\d{1,2}):(\d{2}):(\d{2})(?:\.(\d+))?/
  );
  if (us) {
    const [, month, day, year, hour, minute, second, fraction] = us;
    return assembleLocaleStamp(
      year,
      padStamp(Number(month)),
      padStamp(Number(day)),
      padStamp(Number(hour)),
      minute,
      second,
      locale,
      toFractionalSeconds(fraction, fractionalDigits)
    );
  }

  const iso = raw.match(
    /^(\d{4})-(\d{2})-(\d{2})[ T](\d{2}):(\d{2}):(\d{2})(?:\.(\d+))?/
  );
  if (iso) {
    const [, year, month, day, hour, minute, second, fraction] = iso;
    return assembleLocaleStamp(
      year,
      month,
      day,
      hour,
      minute,
      second,
      locale,
      toFractionalSeconds(fraction, fractionalDigits)
    );
  }

  const parsed = new Date(raw);
  if (!Number.isNaN(parsed.getTime())) {
    return formatOperatorTimestamp(parsed, locale, options);
  }
  return raw;
}

/** Plotly d3-time-format strings matching operator date order. */
export function plotlyLocaleTimeFormats(locale: UiLocale): {
  tickformat: string;
  hoverformat: string;
  tickformatstops: Array<{ dtickrange: [number | null, number | null]; value: string }>;
} {
  const date = locale === "es" ? "%d/%m/%Y" : "%m/%d/%Y";
  const dateShort = locale === "es" ? "%d/%m" : "%m/%d";
  const hoverformat = `${date} %H:%M:%S`;
  return {
    tickformat: hoverformat,
    hoverformat,
    tickformatstops: [
      { dtickrange: [null, 1000], value: "%H:%M:%S.%L" },
      { dtickrange: [1000, 60000], value: "%H:%M:%S" },
      { dtickrange: [60000, 3600000], value: "%H:%M:%S" },
      { dtickrange: [3600000, 86400000], value: `${dateShort} %H:%M` },
      { dtickrange: [86400000, 604800000], value: dateShort },
      { dtickrange: [604800000, null], value: date },
    ],
  };
}
