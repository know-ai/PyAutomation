import { useEffect, useState } from "react";
import { TimezoneBadge } from "./TimezoneBadge";
import { useDisplayTimezone } from "../hooks/useDisplayTimezone";
import { useTranslation } from "../hooks/useTranslation";

function partValue(parts: Intl.DateTimeFormatPart[], type: string): string {
  return parts.find((part) => part.type === type)?.value ?? "";
}

function formatHeaderClock(date: Date, timeZone: string, locale: string): { date: string; time: string } {
  const intlLocale = locale === "es" ? "es-PE" : "en-US";
  try {
    const parts = new Intl.DateTimeFormat(intlLocale, {
      timeZone: timeZone || undefined,
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
      hourCycle: "h23",
    }).formatToParts(date);
    const day = partValue(parts, "day");
    const month = partValue(parts, "month");
    const year = partValue(parts, "year");
    const hour = partValue(parts, "hour");
    const minute = partValue(parts, "minute");
    const second = partValue(parts, "second");
    return {
      date: locale === "es" ? `${day}/${month}/${year}` : `${month}/${day}/${year}`,
      time: `${hour}:${minute}:${second}`,
    };
  } catch {
    const iso = date.toISOString();
    return { date: iso.slice(0, 10), time: iso.slice(11, 19) };
  }
}

export function HeaderClock() {
  const { t, locale } = useTranslation();
  const { timeZone } = useDisplayTimezone();
  const [now, setNow] = useState(() => new Date());

  useEffect(() => {
    const id = window.setInterval(() => setNow(new Date()), 1000);
    return () => window.clearInterval(id);
  }, []);

  const clock = formatHeaderClock(now, timeZone, locale);

  return (
    <div className="header-clock" aria-label={t("header.clockLabel")}>
      <time className="header-clock__stamp" dateTime={now.toISOString()}>
        <span className="header-clock__date">{clock.date}</span>
        <span className="header-clock__time">{clock.time}</span>
      </time>
      <TimezoneBadge compact />
    </div>
  );
}
