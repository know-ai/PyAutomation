import { useEffect, useState } from "react";
import { TimezoneBadge } from "./TimezoneBadge";
import { ClockBadge } from "./ClockBadge";
import { SocketBadge } from "./SocketBadge";
import { useDisplayTimezone } from "../hooks/useDisplayTimezone";
import { useTranslation } from "../hooks/useTranslation";
import { getNodeIdentity } from "../services/health";
import { formatHeaderClock } from "../utils/timezone";

export function HeaderClock() {
  const { t, locale } = useTranslation();
  const { timeZone } = useDisplayTimezone();
  const [now, setNow] = useState(() => new Date());
  const [site, setSite] = useState("");
  const [area, setArea] = useState("");
  const [nodeId, setNodeId] = useState("");

  useEffect(() => {
    const id = window.setInterval(() => setNow(new Date()), 1000);
    return () => window.clearInterval(id);
  }, []);

  useEffect(() => {
    let cancelled = false;
    getNodeIdentity()
      .then((identity) => {
        if (cancelled) return;
        setSite(identity.site.trim());
        setArea(identity.area.trim());
        setNodeId(identity.nodeId.trim());
      })
      .catch(() => {
        // Identity is decorative; the clock still runs.
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const clock = formatHeaderClock(now, timeZone, locale);
  const identity = [site, area].filter(Boolean).join(".");
  const identityTitle = [nodeId, identity].filter(Boolean).join(" · ") || t("header.identityUnknown");

  return (
    <div className="header-clock" aria-label={t("header.clockLabel")}>
      <div className="header-clock__lead">
        <ClockBadge />
        <SocketBadge />
        <TimezoneBadge compact />
      </div>
      <time className="header-clock__stamp" dateTime={now.toISOString()}>
        <span className="header-clock__date">{clock.date}</span>
        <span className="header-clock__time">{clock.time}</span>
      </time>
      <div className="header-clock__identity" title={identityTitle}>
        {site || area ? (
          <>
            {site ? <span className="header-clock__site">{site}</span> : null}
            {site && area ? <span className="header-clock__dot" aria-hidden="true">.</span> : null}
            {area ? <span className="header-clock__area">{area}</span> : null}
          </>
        ) : (
          <span className="header-clock__identity-empty">{t("header.identityUnknown")}</span>
        )}
      </div>
    </div>
  );
}
