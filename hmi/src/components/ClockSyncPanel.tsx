import { useCallback, useEffect, useMemo, useState } from "react";
import clsx from "clsx";
import { Button } from "./Button";
import { SettingsChapter } from "./SettingsChapter";
import { useTranslation } from "../hooks/useTranslation";
import { useDisplayTimezone } from "../hooks/useDisplayTimezone";
import { useAppSelector } from "../hooks/useAppSelector";
import { formatTimestamp } from "../utils/timezone";
import {
  forceClockCheck,
  getClockSettings,
  getClockStatus,
  updateClockSettings,
  type ClockStatus,
} from "../services/clock";
import { showToast } from "../utils/toast";

type StatusLevel = "disabled" | "ok" | "warn" | "alarm";

function statusLevel(status: ClockStatus): StatusLevel {
  if (!status.enabled && !status.config?.effective_enabled) return "disabled";
  if (status.synced === false) return "alarm";
  if (status.warn) return "warn";
  if (status.synced) return "ok";
  return "disabled";
}

function formatUtcStamp(value?: string | null): string {
  if (!value) return "—";
  try {
    return formatTimestamp(value, "UTC");
  } catch {
    return value;
  }
}

function nudgeNumber(current: number, delta: number, min: number, max?: number): number {
  const next = Math.round(current + delta);
  if (max != null) return Math.max(min, Math.min(max, next));
  return Math.max(min, next);
}

export function ClockSyncPanel() {
  const { t } = useTranslation();
  const { timeZone } = useDisplayTimezone();
  const role = useAppSelector((state) => state.auth.user?.role)?.toLowerCase() || "";
  const isAdmin = role === "admin" || role === "sudo";

  const [status, setStatus] = useState<ClockStatus>({});
  const [servers, setServers] = useState("");
  const [intervalS, setIntervalS] = useState(3600);
  const [warnMs, setWarnMs] = useState(50);
  const [alarmMs, setAlarmMs] = useState(1000);
  const [enabled, setEnabled] = useState(true);
  const [failClosed, setFailClosed] = useState(false);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [checking, setChecking] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [snapshot, settings] = await Promise.all([
        getClockStatus(),
        getClockSettings(),
      ]);
      setStatus(snapshot);
      const list = settings.ntp_servers_list?.length
        ? settings.ntp_servers_list
        : (settings.ntp_servers || "").split(",").map((s) => s.trim()).filter(Boolean);
      setServers(list.join(", "));
      setIntervalS(Number(settings.ntp_check_interval_s ?? snapshot.check_interval_s ?? 3600));
      setWarnMs(Number(settings.ntp_warn_offset_ms ?? snapshot.warn_offset_ms ?? 50));
      setAlarmMs(Number(settings.ntp_alarm_offset_ms ?? snapshot.alarm_offset_ms ?? 1000));
      setEnabled(Boolean(settings.ntp_enabled ?? true));
      setFailClosed(Boolean(settings.ntp_fail_closed ?? false));
    } catch (error: any) {
      showToast(error.response?.data?.message || t("clock.loadError"), "error");
    } finally {
      setLoading(false);
    }
  }, [t]);

  useEffect(() => {
    void load();
  }, [load]);

  const level = useMemo(() => statusLevel(status), [status]);
  const statusTone = level === "disabled" ? "unknown" : level === "ok" ? "ok" : level === "warn" ? "warn" : "error";

  const handleSave = async () => {
    if (!isAdmin) return;
    setSaving(true);
    try {
      await updateClockSettings({
        ntp_servers: servers,
        ntp_check_interval_s: intervalS,
        ntp_warn_offset_ms: warnMs,
        ntp_alarm_offset_ms: alarmMs,
        ntp_enabled: enabled,
        ntp_fail_closed: failClosed,
      });
      showToast(t("clock.saved"), "success");
      await load();
    } catch (error: any) {
      showToast(error.response?.data?.message || t("clock.saveError"), "error");
    } finally {
      setSaving(false);
    }
  };

  const handleCheck = async () => {
    setChecking(true);
    try {
      const result = await forceClockCheck();
      if (!result.ok) {
        showToast(result.message || t("clock.checkRateLimited"), "warning");
      } else {
        showToast(t("clock.checkDone"), "success");
      }
      await load();
    } catch (error: any) {
      showToast(error.response?.data?.message || t("clock.checkError"), "error");
    } finally {
      setChecking(false);
    }
  };

  return (
    <SettingsChapter
      id="settings-clock"
      index="02"
      kicker={t("clock.kicker")}
      title={t("clock.title")}
      lede={t("clock.lede")}
    >
      <div className="settings-split settings-split--clock">
        <article className="settings-tile settings-tile--clock-status">
          <div className="settings-tile__label">{t("clock.statusLabel")}</div>
          <p className="settings-tile__hint">{t("clock.statusHint")}</p>

          {loading ? (
            <div className="settings-tile__loading">
              <div className="spinner-border spinner-border-sm text-primary" role="status">
                <span className="visually-hidden">{t("clock.loading")}</span>
              </div>
            </div>
          ) : (
            <>
              <div
                className={clsx("clock-sync-banner", `clock-sync-banner--${statusTone}`)}
                role="status"
              >
                <span className={`clock-sync-banner__led clock-sync-banner__led--${statusTone}`} aria-hidden="true" />
                <div className="clock-sync-banner__copy">
                  <span className="clock-sync-banner__label">{t(`clock.status.${level}`)}</span>
                  <span className="clock-sync-banner__meta">
                    {status.server_used
                      ? t("clock.bannerMetaWithServer", { server: status.server_used })
                      : t("clock.bannerMetaIdle")}
                  </span>
                </div>
                {status.offset_ms != null ? (
                  <span className="clock-sync-banner__chip">
                    Δ {status.offset_ms} ms
                  </span>
                ) : null}
              </div>

              <div className="clock-sync-stats">
                <div className="clock-sync-stat">
                  <span className="clock-sync-stat__label">{t("clock.server")}</span>
                  <span className="clock-sync-stat__value clock-sync-stat__value--mono">
                    {status.server_used || "—"}
                  </span>
                </div>
                <div className="clock-sync-stat">
                  <span className="clock-sync-stat__label">{t("clock.addressUsed")}</span>
                  <span className="clock-sync-stat__value clock-sync-stat__value--mono">
                    {status.last_address_used || "—"}
                  </span>
                </div>
                <div className="clock-sync-stat">
                  <span className="clock-sync-stat__label">{t("clock.stratum")}</span>
                  <span className="clock-sync-stat__value">
                    {status.stratum != null ? status.stratum : "—"}
                  </span>
                </div>
                <div className="clock-sync-stat">
                  <span className="clock-sync-stat__label">{t("clock.protocol")}</span>
                  <span className="clock-sync-stat__value">
                    {status.protocol_version || "—"}
                  </span>
                </div>
                <div className="clock-sync-stat">
                  <span className="clock-sync-stat__label">{t("clock.lastCheck")}</span>
                  <span className="clock-sync-stat__value">
                    {formatUtcStamp(status.last_check_utc)}
                  </span>
                </div>
                <div className="clock-sync-stat">
                  <span className="clock-sync-stat__label">{t("clock.nextCheck")}</span>
                  <span className="clock-sync-stat__value">
                    {formatUtcStamp(status.next_check_utc)}
                  </span>
                </div>
              </div>

              {(level === "alarm" || status.last_error || status.auth_required_detected) && (
                <div className="settings-callout clock-sync-callout clock-sync-callout--error">
                  <i className="bi bi-exclamation-triangle" aria-hidden="true" />
                  <div>
                    {status.auth_required_detected ? (
                      <p>{t("clock.authRequired")}</p>
                    ) : null}
                    {status.last_error ? (
                      <p className="mb-0">
                        <strong>{t("clock.lastError")}:</strong>{" "}
                        <span className="clock-sync-stat__value--mono">{status.last_error}</span>
                      </p>
                    ) : null}
                  </div>
                </div>
              )}

              {status.jump_detected ? (
                <div className="settings-callout clock-sync-callout">
                  <i className="bi bi-lightning" aria-hidden="true" />
                  <p>{t("clock.stepDetected")}</p>
                </div>
              ) : null}

              <div className="settings-callout clock-sync-callout">
                <i className="bi bi-hdd-network" aria-hidden="true" />
                <p>{t("clock.hostTimeNote", { zone: timeZone })}</p>
              </div>
            </>
          )}

          <div className="settings-panel__actions">
            <Button variant="secondary" onClick={() => void handleCheck()} loading={checking} disabled={loading}>
              {t("clock.forceCheck")}
            </Button>
          </div>
        </article>

        {isAdmin ? (
          <article className="settings-tile settings-tile--clock-config">
            <div className="settings-tile__label">{t("clock.configLabel")}</div>
            <p className="settings-tile__hint">{t("clock.configHint")}</p>

            <div className="clock-sync-form">
              <div className="settings-form-field settings-form-field--span">
                <label htmlFor="ntp-servers" className="form-label">
                  {t("clock.servers")}
                </label>
                <input
                  id="ntp-servers"
                  className="form-control clock-sync-servers-input"
                  value={servers}
                  onChange={(e) => setServers(e.target.value)}
                  placeholder={t("clock.serversPlaceholder")}
                  spellCheck={false}
                  autoComplete="off"
                  inputMode="text"
                />
                <small className="form-text text-muted">{t("clock.serversHint")}</small>
                <small className="form-text text-muted d-block">{t("clock.serversTooltip")}</small>
              </div>

              <div className="clock-sync-form__metrics">
                <div className="settings-form-field">
                  <label htmlFor="ntp-interval" className="form-label">
                    {t("clock.interval")}
                  </label>
                  <div className="settings-metric settings-metric--fluid">
                    <button
                      type="button"
                      className="settings-metric__step"
                      onClick={() => setIntervalS((v) => nudgeNumber(v, -300, 60, 86400))}
                      aria-label={t("clock.intervalDecrease")}
                    >
                      −
                    </button>
                    <input
                      id="ntp-interval"
                      className="settings-metric__input settings-metric__input--wide"
                      type="number"
                      min={60}
                      max={86400}
                      step={60}
                      value={intervalS}
                      onChange={(e) => setIntervalS(nudgeNumber(Number(e.target.value) || 3600, 0, 60, 86400))}
                    />
                    <span className="settings-metric__unit">{t("settings.secondsUnit")}</span>
                    <button
                      type="button"
                      className="settings-metric__step"
                      onClick={() => setIntervalS((v) => nudgeNumber(v, 300, 60, 86400))}
                      aria-label={t("clock.intervalIncrease")}
                    >
                      +
                    </button>
                  </div>
                  <small className="form-text text-muted">{t("clock.intervalHint")}</small>
                </div>

                <div className="settings-form-field">
                  <label htmlFor="ntp-warn" className="form-label">
                    {t("clock.warnMs")}
                  </label>
                  <div className="settings-metric settings-metric--fluid">
                    <button
                      type="button"
                      className="settings-metric__step"
                      onClick={() => setWarnMs((v) => nudgeNumber(v, -10, 1))}
                      aria-label={t("clock.warnDecrease")}
                    >
                      −
                    </button>
                    <input
                      id="ntp-warn"
                      className="settings-metric__input settings-metric__input--wide"
                      type="number"
                      min={1}
                      value={warnMs}
                      onChange={(e) => setWarnMs(nudgeNumber(Number(e.target.value) || 50, 0, 1))}
                    />
                    <span className="settings-metric__unit">ms</span>
                    <button
                      type="button"
                      className="settings-metric__step"
                      onClick={() => setWarnMs((v) => nudgeNumber(v, 10, 1))}
                      aria-label={t("clock.warnIncrease")}
                    >
                      +
                    </button>
                  </div>
                </div>

                <div className="settings-form-field">
                  <label htmlFor="ntp-alarm" className="form-label">
                    {t("clock.alarmMs")}
                  </label>
                  <div className="settings-metric settings-metric--fluid">
                    <button
                      type="button"
                      className="settings-metric__step"
                      onClick={() => setAlarmMs((v) => nudgeNumber(v, -50, warnMs))}
                      aria-label={t("clock.alarmDecrease")}
                    >
                      −
                    </button>
                    <input
                      id="ntp-alarm"
                      className="settings-metric__input settings-metric__input--wide"
                      type="number"
                      min={warnMs}
                      value={alarmMs}
                      onChange={(e) =>
                        setAlarmMs(Math.max(warnMs, nudgeNumber(Number(e.target.value) || 1000, 0, 1)))
                      }
                    />
                    <span className="settings-metric__unit">ms</span>
                    <button
                      type="button"
                      className="settings-metric__step"
                      onClick={() => setAlarmMs((v) => nudgeNumber(v, 50, warnMs))}
                      aria-label={t("clock.alarmIncrease")}
                    >
                      +
                    </button>
                  </div>
                </div>
              </div>

              <div className="settings-form-field settings-form-field--span">
                <div className="settings-field__label">{t("clock.policyLabel")}</div>
                <div className="clock-sync-policy">
                  <button
                    type="button"
                    className={clsx("settings-choice__card", enabled && "is-selected")}
                    onClick={() => setEnabled((v) => !v)}
                    aria-pressed={enabled}
                  >
                    <i className="bi bi-broadcast settings-choice__icon" aria-hidden="true" />
                    <span className="settings-choice__copy">
                      <span className="settings-choice__name">{t("clock.enabled")}</span>
                      <span className="settings-choice__hint">{t("clock.enabledHint")}</span>
                    </span>
                  </button>
                  <button
                    type="button"
                    className={clsx("settings-choice__card", failClosed && "is-selected")}
                    onClick={() => setFailClosed((v) => !v)}
                    aria-pressed={failClosed}
                  >
                    <i className="bi bi-shield-exclamation settings-choice__icon" aria-hidden="true" />
                    <span className="settings-choice__copy">
                      <span className="settings-choice__name">{t("clock.failClosed")}</span>
                      <span className="settings-choice__hint">{t("clock.failClosedHint")}</span>
                    </span>
                  </button>
                </div>
              </div>
            </div>

            <div className="settings-split__footer">
              <p className="settings-split__note">{t("clock.saveNote")}</p>
              <Button variant="primary" onClick={() => void handleSave()} loading={saving} disabled={loading}>
                {t("clock.save")}
              </Button>
            </div>
          </article>
        ) : (
          <article className="settings-tile settings-tile--clock-config">
            <div className="settings-tile__label">{t("clock.configLabel")}</div>
            <p className="settings-tile__hint">{t("clock.adminOnly")}</p>
          </article>
        )}
      </div>
    </SettingsChapter>
  );
}
