import { memo } from "react";
import { Button } from "./Button";
import { QualityBadge } from "./QualityBadge";
import { useTranslation } from "../hooks/useTranslation";
import type { Alarm } from "../services/alarms";
import type { Tag } from "../services/tags";
import { translateAlarmDescription } from "../utils/alarmCatalog";

type AlarmTableRowProps = {
  alarm: Alarm;
  realTimeAlarm?: Alarm;
  tagValue?: Tag["value"];
  tagQuality?: number | string | null;
  tagQualityLabel?: string | null;
  tagStale?: boolean;
  tagStaleAgeMs?: number | null;
  onEdit: (alarm: Alarm) => void;
  onDelete: (alarm: Alarm) => void;
  getStateBadgeClass: (state: any) => string;
  getStateLabel: (state: any) => string;
  actions: { [key: string]: string } | undefined;
  loadingActions: boolean;
  executingAction: boolean;
  onLoadActions: (alarmName: string) => void;
  onExecuteAction: (actionValue: string, alarmName: string) => void;
  isActionDropdownOpen: boolean;
  onToggleActionDropdown: (alarmName: string) => void;
  actionDropdownRef: (el: HTMLDivElement | null) => void;
};

export const AlarmTableRow = memo(
  ({
    alarm,
    realTimeAlarm,
    tagValue,
    tagQuality,
    tagQualityLabel,
    tagStale,
    tagStaleAgeMs,
    onEdit,
    onDelete,
    getStateBadgeClass,
    getStateLabel,
    actions,
    loadingActions,
    executingAction,
    onLoadActions,
    onExecuteAction,
    isActionDropdownOpen,
    onToggleActionDropdown,
    actionDropdownRef,
  }: AlarmTableRowProps) => {
    const { t } = useTranslation();
    const currentAlarm = realTimeAlarm || alarm;
    const displayTagValue =
      tagValue !== undefined && tagValue !== null
        ? typeof tagValue === "boolean"
          ? tagValue
            ? "true"
            : "false"
          : String(tagValue)
        : "-";

    const alarmType = currentAlarm.alarm_type || currentAlarm.alarm_setpoint?.type || "-";
    const triggerValue =
      currentAlarm.trigger_value !== undefined
        ? String(currentAlarm.trigger_value)
        : currentAlarm.alarm_setpoint?.value !== undefined
          ? String(currentAlarm.alarm_setpoint.value)
          : "-";

    return (
      <tr>
        <td>
          <strong
            title={currentAlarm.tag || undefined}
            style={{ cursor: currentAlarm.tag ? "help" : "default" }}
          >
            {currentAlarm.name || "-"}
          </strong>
        </td>
        <td>
          <span className="badge bg-primary">{alarmType}</span>
        </td>
        <td>
          <span className="d-inline-flex align-items-center gap-1">
            <span>{displayTagValue}</span>
            {currentAlarm.tag ? (
              <QualityBadge
                quality={tagQuality}
                qualityLabel={tagQualityLabel}
                stale={Boolean(tagStale)}
                staleAgeMs={typeof tagStaleAgeMs === "number" ? tagStaleAgeMs : null}
              />
            ) : null}
          </span>
        </td>
        <td>{triggerValue}</td>
        <td>{translateAlarmDescription(currentAlarm.description, currentAlarm.name, t)}</td>
        <td>
          <span className={`badge ${getStateBadgeClass(currentAlarm.state)}`}>
            {getStateLabel(currentAlarm.state)}
          </span>
        </td>
        <td>
          <div className="d-flex gap-2">
            <Button
              variant="secondary"
              className="btn-sm"
              onClick={() => onEdit(currentAlarm)}
              title={t("alarms.editAlarm")}
            >
              <i className="bi bi-pencil"></i>
            </Button>
            <Button
              variant="danger"
              className="btn-sm"
              onClick={() => onDelete(currentAlarm)}
              title={t("alarms.deleteAlarm")}
            >
              <i className="bi bi-trash"></i>
            </Button>
            <div className="btn-group" ref={actionDropdownRef} style={{ position: "relative" }}>
              <Button
                variant="secondary"
                className="btn-sm dropdown-toggle"
                onClick={(e) => {
                  e.stopPropagation();
                  onToggleActionDropdown(currentAlarm.name);
                  if (!actions && !loadingActions) {
                    onLoadActions(currentAlarm.name);
                  }
                }}
                disabled={executingAction}
                title={t("alarms.alarmActions")}
              >
                {loadingActions ? (
                  <span className="spinner-border spinner-border-sm" role="status" aria-hidden="true"></span>
                ) : (
                  <i className="bi bi-gear"></i>
                )}
              </Button>
              {isActionDropdownOpen && (
                <div
                  className="dropdown-menu show"
                  style={{
                    position: "absolute",
                    right: 0,
                    top: "100%",
                    zIndex: 1000,
                    minWidth: "200px",
                  }}
                  onClick={(e) => e.stopPropagation()}
                >
                  {loadingActions ? (
                    <div className="dropdown-item-text">
                      <span className="spinner-border spinner-border-sm me-2" role="status" aria-hidden="true"></span>
                      {t("alarms.loadingActions")}
                    </div>
                  ) : actions && Object.keys(actions).length > 0 ? (
                    Object.entries(actions).map(([actionLabel, actionValue]) => (
                      <button
                        key={actionValue}
                        className="dropdown-item"
                        onClick={() => {
                          onExecuteAction(actionValue, currentAlarm.name);
                          onToggleActionDropdown(currentAlarm.name);
                        }}
                        disabled={executingAction}
                      >
                        {actionLabel}
                      </button>
                    ))
                  ) : (
                    <div className="dropdown-item-text text-muted">{t("alarms.noActionsAvailable")}</div>
                  )}
                </div>
              )}
            </div>
          </div>
        </td>
      </tr>
    );
  },
  (prevProps, nextProps) => {
    const prevAlarm = prevProps.realTimeAlarm || prevProps.alarm;
    const nextAlarm = nextProps.realTimeAlarm || nextProps.alarm;
    return (
      prevAlarm.name === nextAlarm.name &&
      prevAlarm.tag === nextAlarm.tag &&
      prevAlarm.alarm_type === nextAlarm.alarm_type &&
      prevAlarm.trigger_value === nextAlarm.trigger_value &&
      prevAlarm.description === nextAlarm.description &&
      JSON.stringify(prevAlarm.state) === JSON.stringify(nextAlarm.state) &&
      prevProps.tagValue === nextProps.tagValue &&
      prevProps.tagQuality === nextProps.tagQuality &&
      prevProps.tagQualityLabel === nextProps.tagQualityLabel &&
      prevProps.tagStale === nextProps.tagStale &&
      prevProps.tagStaleAgeMs === nextProps.tagStaleAgeMs &&
      JSON.stringify(prevProps.actions) === JSON.stringify(nextProps.actions) &&
      prevProps.loadingActions === nextProps.loadingActions &&
      prevProps.executingAction === nextProps.executingAction &&
      prevProps.isActionDropdownOpen === nextProps.isActionDropdownOpen
    );
  }
);

AlarmTableRow.displayName = "AlarmTableRow";
