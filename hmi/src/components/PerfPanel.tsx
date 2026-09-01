import clsx from "clsx";
import type { ButtonHTMLAttributes, MouseEvent, ReactNode } from "react";
import { Sparkline } from "./Sparkline";
import type { PerfAlarmLifecycle, TileTone } from "../services/performanceAlarms";
import { useTranslation } from "../hooks/useTranslation";

type PerfPanelProps = {
  title: string;
  tone?: TileTone;
  lifecycle?: PerfAlarmLifecycle;
  alarmable?: boolean;
  thresholdLabel?: string;
  canConfigure?: boolean;
  spark?: number[];
  children: ReactNode;
  actions?: ReactNode;
  onOpen?: () => void;
  onConfigure?: () => void;
  /** Tooltip del icono "i". Cadena vacía o ausente: se oculta. */
  info?: string;
  subtitle?: string;
  dragHandle?: boolean;
  className?: string;
  bodyClassName?: string;
};

export function PerfInfoTip({ text }: { text: string }) {
  return (
    <button
      type="button"
      className="perf-info"
      aria-label={text}
      onClick={(event) => event.stopPropagation()}
      onMouseDown={(event) => event.stopPropagation()}
    >
      <i className="bi bi-info-circle" aria-hidden="true" />
      <span className="perf-info__bubble" role="tooltip">
        {text}
      </span>
    </button>
  );
}

type OpsHintButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  hint: string;
};

export function OpsHintButton({ hint, className, children, type, ...props }: OpsHintButtonProps) {
  return (
    <button
      {...props}
      type={type ?? "button"}
      className={clsx("perf-ops-tip", className)}
    >
      {children}
      <span className="perf-ops-tip__bubble" role="tooltip">
        {hint}
      </span>
    </button>
  );
}

export function PerfPanel({
  title,
  tone = "unknown",
  lifecycle = "normal",
  alarmable = false,
  thresholdLabel,
  canConfigure = false,
  spark,
  children,
  actions,
  onOpen,
  onConfigure,
  info,
  subtitle,
  dragHandle = false,
  className,
  bodyClassName,
}: PerfPanelProps) {
  const { t } = useTranslation();
  const status =
    lifecycle === "unack"
      ? t("performance.badgeActive")
      : lifecycle === "ack"
        ? t("performance.badgeAck")
        : lifecycle === "shelved"
          ? t("performance.badgeShelved")
          : alarmable
            ? t("performance.badgeOk")
            : null;

  const openConfigure = (event: MouseEvent) => {
    event.stopPropagation();
    onConfigure?.();
  };

  return (
    <section
      className={clsx("perf-panel", `perf-panel--${tone}`, onOpen && "perf-panel--clickable", className)}
      onClick={onOpen}
      role={onOpen ? "button" : undefined}
      tabIndex={onOpen ? 0 : undefined}
      onKeyDown={(event) => {
        if (!onOpen) return;
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          onOpen();
        }
      }}
    >
      <header className={clsx("perf-panel__head", dragHandle && "lds-card-handle")}>
        <div>
          <h4 className="perf-panel__title">{title}</h4>
          {subtitle ? <p className="perf-panel__subtitle">{subtitle}</p> : null}
          {status ? (
            <span className={clsx("perf-badge", `perf-badge--${lifecycle === "normal" ? "ok" : lifecycle}`)}>
              <span className={clsx("perf-badge__dot", lifecycle === "unack" && "perf-badge__dot--live")} />
              {status}
            </span>
          ) : null}
        </div>
        <span className="perf-tile__tools">
          {alarmable ? (
            <i className="bi bi-bell perf-tile__mark" title={t("performance.alarmable")} aria-hidden="true" />
          ) : info ? (
            <PerfInfoTip text={info} />
          ) : null}
          {canConfigure && onConfigure ? (
            <button
              type="button"
              className="perf-tile__gear"
              title={t("performance.alarmConfigure")}
              aria-label={t("performance.alarmConfigure")}
              onClick={openConfigure}
            >
              <i className="bi bi-gear" aria-hidden="true" />
            </button>
          ) : null}
        </span>
      </header>
      <div className={clsx("perf-panel__body", bodyClassName)}>{children}</div>
      {actions ? (
        <div className="perf-panel__actions" onClick={(event) => event.stopPropagation()}>
          {actions}
        </div>
      ) : null}
      {thresholdLabel ? <p className="perf-tile__threshold">{t("performance.thresholdLine", { value: thresholdLabel })}</p> : null}
      {spark && spark.length > 1 ? <Sparkline values={spark} tone={tone} /> : null}
    </section>
  );
}

export function PerfStat({ label, value }: { label: string; value: string }) {
  return (
    <div className="perf-stat">
      <span className="perf-stat__label">{label}</span>
      <span className="perf-stat__value">{value}</span>
    </div>
  );
}
