import { useEffect, useState } from "react";
import { Card } from "./Card";
import { Button } from "./Button";
import { useTranslation } from "../hooks/useTranslation";
import { useAuthz } from "../hooks/useAuthz";
import { useAppSelector } from "../hooks/useAppSelector";
import { useOperatorConfirmation } from "./OperatorConfirmationProvider";
import { showToast } from "../utils/toast";
import { formatOperatorTimestamp, getBrowserTimeZone } from "../utils/timezone";
import {
  filterLeaks,
  getFalseAlarmMetrics,
  reportLeak,
  type FalseAlarmMetrics,
  type LeakPage,
  type LeakRow,
  type LeakUnit,
} from "../services/leaks";

const PAGE_SIZE = 10;
const WINDOWS = [
  { id: "24h", hours: 24, labelKey: "machines.ldsWindow24h" },
  { id: "7d", hours: 24 * 7, labelKey: "machines.ldsWindow7d" },
  { id: "30d", hours: 24 * 30, labelKey: "machines.ldsWindow30d" },
] as const;

type WindowId = (typeof WINDOWS)[number]["id"];
type Queue = "open" | "all";

export function isLdsEngineName(name: string): boolean {
  return (name.split(".").pop() || "").trim().toUpperCase() === "LDS";
}

function stampInZone(date: Date, timeZone: string): string {
  const parts = new Intl.DateTimeFormat("en-US", {
    timeZone: timeZone || undefined,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hourCycle: "h23",
  }).formatToParts(date);
  const pick = (type: string) => parts.find((part) => part.type === type)?.value ?? "00";
  return `${pick("year")}-${pick("month")}-${pick("day")}T${pick("hour")}:${pick("minute")}:${pick("second")}`;
}

function unitLabel(unit: LeakUnit): string {
  if (!unit) return "";
  if (typeof unit === "string") return unit;
  return unit.unit ? String(unit.unit) : "";
}

function measure(value: number | null | undefined, unit: LeakUnit, locale: string): string {
  if (value == null || Number.isNaN(Number(value))) return "—";
  const text = Number(value).toLocaleString(locale === "es" ? "es-PE" : "en-US", {
    maximumFractionDigits: 3,
  });
  const suffix = unitLabel(unit);
  return suffix ? `${text} ${suffix}` : text;
}

function formatDuration(seconds: number | null | undefined, locale: string): string {
  if (seconds == null || !Number.isFinite(seconds) || seconds < 0) return "—";
  const tag = locale === "es" ? "es-PE" : "en-US";
  if (seconds < 60) return `${Math.round(seconds)} s`;
  if (seconds < 3600) {
    return `${(seconds / 60).toLocaleString(tag, { maximumFractionDigits: 1 })} min`;
  }
  return `${(seconds / 3600).toLocaleString(tag, { maximumFractionDigits: 1 })} h`;
}

const METERS_PER_UNIT: Record<string, number> = {
  m: 1,
  meter: 1,
  meters: 1,
  metre: 1,
  metres: 1,
  km: 1000,
  kilometer: 1000,
  kilometers: 1000,
  kilometre: 1000,
  kilometres: 1000,
  ft: 0.3048,
  foot: 0.3048,
  feet: 0.3048,
};

function metersFactor(unit: LeakUnit): number | null {
  const name = unitLabel(unit).trim().toLowerCase();
  if (!name) return null;
  return METERS_PER_UNIT[name] ?? null;
}

function locationErrorMeters(estimated: number | null | undefined, unit: LeakUnit, reportedRaw: string): number | null {
  const reported = Number(reportedRaw.trim());
  if (estimated == null || !Number.isFinite(Number(estimated)) || !Number.isFinite(reported)) return null;
  const factor = metersFactor(unit);
  if (factor == null) return null;
  return Math.abs(Number(estimated) * factor - reported);
}

function formatMeters(value: number | null | undefined, locale: string): string {
  if (value == null || !Number.isFinite(value)) return "—";
  const text = value.toLocaleString(locale === "es" ? "es-PE" : "en-US", {
    maximumFractionDigits: 1,
  });
  return `${text} m`;
}

function formatRate(value: number, locale: string): string {
  return `${value.toLocaleString(locale === "es" ? "es-PE" : "en-US", {
    minimumFractionDigits: 0,
    maximumFractionDigits: 1,
  })}%`;
}

function classifierOf(row: LeakRow): string {
  return row.classified_by || row.user?.username || "—";
}

export function LdsLeakPerformance() {
  const { t, locale } = useTranslation();
  const { canRest } = useAuthz();
  const { confirm } = useOperatorConfirmation();
  const mode = useAppSelector((state) => state.displayTimezone.mode);
  const plantTimezone = useAppSelector((state) => state.displayTimezone.plantTimezone);
  const timeZone = mode === "plant" && plantTimezone ? plantTimezone : getBrowserTimeZone();
  const canRead =
    canRest("/api/leaks/metrics/false-alarms", "view") && canRest("/api/leaks/filter_by", "use");
  const canClassify = canRest("/api/leaks/report", "use");

  const [windowId, setWindowId] = useState<WindowId>("7d");
  const [queue, setQueue] = useState<Queue>("open");
  const [page, setPage] = useState(1);
  const [reloadKey, setReloadKey] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [metrics, setMetrics] = useState<FalseAlarmMetrics | null>(null);
  const [list, setList] = useState<LeakPage | null>(null);
  const [draft, setDraft] = useState<{
    id: number;
    isLeak: boolean;
    estimatedLocation: number | null;
    estimatedUnit: LeakUnit;
  } | null>(null);
  const [size, setSize] = useState("");
  const [volume, setVolume] = useState("");
  const [location, setLocation] = useState("");
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (!canRead) return;
    const hours = WINDOWS.find((item) => item.id === windowId)?.hours ?? 24 * 7;
    const to = new Date();
    const from = new Date(to.getTime() - hours * 60 * 60 * 1000);
    const range = {
      from: stampInZone(from, timeZone),
      to: stampInZone(to, timeZone),
      timezone: timeZone || "UTC",
    };
    const controller = new AbortController();
    setLoading(true);
    setError(null);
    Promise.all([
      getFalseAlarmMetrics(range, controller.signal),
      filterLeaks(
        {
          greater_than_timestamp: range.from,
          less_than_timestamp: range.to,
          timezone: range.timezone,
          page,
          limit: PAGE_SIZE,
          state: queue === "open" ? "unconfirmed" : undefined,
        },
        controller.signal
      ),
    ])
      .then(([nextMetrics, nextList]) => {
        setMetrics(nextMetrics);
        setList(nextList);
        const nextPages = Math.max(1, nextList?.pagination?.pages ?? 1);
        if (page > nextPages) setPage(nextPages);
      })
      .catch((err: { code?: string; response?: { data?: { message?: string } }; message?: string }) => {
        if (controller.signal.aborted || err?.code === "ERR_CANCELED") return;
        const message = err?.response?.data?.message || err?.message || t("machines.ldsLoadError");
        setError(message);
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, [canRead, windowId, queue, page, timeZone, reloadKey, t]);

  if (!canRead) return null;

  const declared = metrics?.total_alarms ?? 0;
  const confirmed = metrics?.confirmed_real ?? 0;
  const falseAlarms = metrics?.false_alarms ?? 0;
  const pending = Math.max(0, declared - confirmed - falseAlarms);
  const judged = confirmed + falseAlarms;
  const judgedRate = judged > 0 ? (falseAlarms / judged) * 100 : null;
  const rows = list?.data ?? [];
  const total = list?.pagination?.total ?? 0;
  const pages = Math.max(1, list?.pagination?.pages ?? 1);
  const rangeStart = total === 0 ? 0 : (page - 1) * PAGE_SIZE + 1;
  const rangeEnd = total === 0 ? 0 : Math.min(page * PAGE_SIZE, total);
  const draftLocationError = draft
    ? locationErrorMeters(draft.estimatedLocation, draft.estimatedUnit, location)
    : null;

  const openDraft = (row: LeakRow, isLeak: boolean) => {
    setDraft({
      id: row.id,
      isLeak,
      estimatedLocation: row.location ?? null,
      estimatedUnit: row.location_unit,
    });
    setSize("");
    setVolume("");
    setLocation("");
  };

  const optionalNumber = (raw: string): number | undefined => {
    const trimmed = raw.trim();
    if (!trimmed) return undefined;
    const value = Number(trimmed);
    return Number.isFinite(value) ? value : undefined;
  };

  const submitDraft = async () => {
    if (!draft || saving) return;
    const id = draft.id;
    const isLeak = draft.isLeak;
    const estimatedLocation = draft.estimatedLocation;
    const estimatedUnit = draft.estimatedUnit;
    setDraft(null);
    const confirmed = await confirm({
      method: "PUT",
      path: `/api/leaks/report/${id}`,
      title: t("operatorConfirm.title"),
      detail: isLeak ? t("machines.ldsRealLeak") : t("machines.ldsFalseAlarm"),
    });
    if (!confirmed) {
      setDraft({ id, isLeak, estimatedLocation, estimatedUnit });
      return;
    }
    setSaving(true);
    try {
      await reportLeak(
        id,
        {
          is_leak: isLeak,
          size: optionalNumber(size),
          volume: optionalNumber(volume),
          location: optionalNumber(location),
        },
        confirmed.token
      );
      showToast(t("machines.ldsClassified"), "success");
      setReloadKey((value) => value + 1);
    } catch (err: unknown) {
      const data = (err as { response?: { data?: { message?: string } } })?.response?.data;
      showToast(data?.message || t("machines.ldsClassifyError"), "error");
      setDraft({ id, isLeak, estimatedLocation, estimatedUnit });
    } finally {
      setSaving(false);
    }
  };

  return (
    <Card
      className="lds-performance"
      title={
        <div className="d-flex flex-wrap justify-content-between align-items-center gap-2">
          <h3 className="card-title m-0">{t("machines.ldsPerformanceTitle")}</h3>
          <div className="btn-group btn-group-sm" role="group" aria-label={t("machines.ldsPerformanceTitle")}>
            {WINDOWS.map((item) => (
              <button
                key={item.id}
                type="button"
                className={`btn ${windowId === item.id ? "btn-primary" : "btn-outline-secondary"}`}
                onClick={() => {
                  setWindowId(item.id);
                  setPage(1);
                }}
              >
                {t(item.labelKey)}
              </button>
            ))}
          </div>
        </div>
      }
    >
      <p className="text-muted small mb-3">{t("machines.ldsPerformanceLede")}</p>
      {error && (
        <div className="alert alert-warning py-2" role="alert">
          {error}
        </div>
      )}
      <div className="lds-performance-stats mb-3">
        <Stat label={t("machines.ldsDeclared")} value={String(declared)} />
        <Stat label={t("machines.ldsConfirmed")} value={String(confirmed)} />
        <Stat label={t("machines.ldsFalseAlarms")} value={String(falseAlarms)} />
        <Stat label={t("machines.ldsPending")} value={String(pending)} />
        <Stat
          label={t("machines.ldsFalseAlarmRate")}
          value={metrics ? formatRate(metrics.false_alarm_rate, locale) : "—"}
        />
        <Stat
          label={t("machines.ldsMeanResponse")}
          value={formatDuration(metrics?.mean_response_time_seconds, locale)}
        />
        <Stat
          label={t("machines.ldsLocationAccuracy")}
          value={formatMeters(metrics?.mean_location_error_m, locale)}
          hint={t("machines.ldsLocationAccuracyHint")}
        />
      </div>
      {judgedRate != null && (
        <p className="text-muted small mt-2 mb-3">
          {t("machines.ldsRateAmongClassified", { value: formatRate(judgedRate, locale) })}
        </p>
      )}
      <div className="btn-group btn-group-sm mb-2" role="group">
        <button
          type="button"
          className={`btn ${queue === "open" ? "btn-primary" : "btn-outline-secondary"}`}
          onClick={() => {
            setQueue("open");
            setPage(1);
          }}
        >
          {t("machines.ldsQueueOpen")}
        </button>
        <button
          type="button"
          className={`btn ${queue === "all" ? "btn-primary" : "btn-outline-secondary"}`}
          onClick={() => {
            setQueue("all");
            setPage(1);
          }}
        >
          {t("machines.ldsQueueAll")}
        </button>
      </div>
      {loading && rows.length === 0 ? (
        <div className="text-muted small py-3">{t("common.loading")}</div>
      ) : rows.length === 0 ? (
        <div className="text-muted small py-3">
          {queue === "open" ? t("machines.ldsEmptyOpen") : t("machines.ldsEmptyAll")}
        </div>
      ) : (
        <div className="table-responsive">
          <table className="table table-sm table-hover mb-2">
            <thead>
              <tr>
                <th>{t("machines.ldsWhen")}</th>
                <th>{t("machines.ldsMode")}</th>
                <th>{t("machines.ldsFlow")}</th>
                <th>{t("machines.ldsLocation")}</th>
                <th>{t("machines.ldsStatus")}</th>
                <th>{t("machines.ldsClassifier")}</th>
                {canClassify && <th />}
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr key={row.id}>
                  <td>{formatOperatorTimestamp(row.timestamp, locale)}</td>
                  <td>{row.operation_mode || "—"}</td>
                  <td>{measure(row.flow, row.flow_unit, locale)}</td>
                  <td>{measure(row.location, row.location_unit, locale)}</td>
                  <td>{row.state || "—"}</td>
                  <td>{classifierOf(row)}</td>
                  {canClassify && row.state === "unconfirmed" && (
                    <td className="text-nowrap">
                      <Button className="btn-sm me-1" onClick={() => openDraft(row, true)} disabled={saving}>
                        {t("machines.ldsRealLeak")}
                      </Button>
                      <Button variant="secondary" className="btn-sm" onClick={() => openDraft(row, false)} disabled={saving}>
                        {t("machines.ldsFalseAlarm")}
                      </Button>
                    </td>
                  )}
                  {canClassify && row.state !== "unconfirmed" && <td />}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <div className="d-flex flex-wrap justify-content-between align-items-center gap-2 mt-2">
        <span className="text-muted small">
          {t("machines.ldsPageRange", {
            page,
            pages,
            start: rangeStart,
            end: rangeEnd,
            total,
          })}
        </span>
        <div className="d-flex gap-2">
          <Button variant="secondary" className="btn-sm" disabled={page <= 1 || loading} onClick={() => setPage((value) => Math.max(1, value - 1))}>
            {t("pagination.previous")}
          </Button>
          <Button variant="secondary" className="btn-sm" disabled={page >= pages || loading} onClick={() => setPage((value) => value + 1)}>
            {t("pagination.next")}
          </Button>
        </div>
      </div>
      {draft && (
        <div className="modal fade show" style={{ display: "block", backgroundColor: "rgba(0,0,0,0.5)" }} role="dialog" aria-modal="true">
          <div className="modal-dialog modal-dialog-centered">
            <div className="modal-content">
              <div className="modal-header">
                <h5 className="modal-title">{t("machines.ldsClassifyTitle")}</h5>
                <button type="button" className="btn-close" aria-label={t("common.cancel")} onClick={() => setDraft(null)} />
              </div>
              <div className="modal-body">
                <p className="mb-2">{draft.isLeak ? t("machines.ldsRealLeak") : t("machines.ldsFalseAlarm")}</p>
                {!draft.isLeak && <div className="alert alert-warning py-2">{t("machines.ldsClassifyFalseWarning")}</div>}
                <label className="form-label small mb-1">{t("machines.ldsSizeOptional")}</label>
                <input className="form-control form-control-sm mb-2" inputMode="decimal" value={size} onChange={(event) => setSize(event.target.value)} />
                <label className="form-label small mb-1">{t("machines.ldsVolumeOptional")}</label>
                <input className="form-control form-control-sm mb-2" inputMode="decimal" value={volume} onChange={(event) => setVolume(event.target.value)} />
                <label className="form-label small mb-1">{t("machines.ldsLocationOptional")}</label>
                <input className="form-control form-control-sm" inputMode="decimal" value={location} onChange={(event) => setLocation(event.target.value)} />
                {draftLocationError != null && (
                  <p className="text-muted small mt-2 mb-0">
                    {t("machines.ldsLocationErrorPreview", { value: formatMeters(draftLocationError, locale) })}
                  </p>
                )}
              </div>
              <div className="modal-footer">
                <Button variant="secondary" onClick={() => setDraft(null)}>{t("common.cancel")}</Button>
                <Button onClick={() => void submitDraft()} disabled={saving}>{t("machines.ldsClassifyConfirm")}</Button>
              </div>
            </div>
          </div>
        </div>
      )}
    </Card>
  );
}

function Stat({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <div className="lds-performance-stat">
      <div className="text-muted small">{label}</div>
      <div className="fw-semibold">{value}</div>
      {hint ? <div className="text-muted small">{hint}</div> : null}
    </div>
  );
}
