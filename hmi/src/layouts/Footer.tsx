import { useEffect, useState, useRef } from "react";
import { createPortal } from "react-dom";
import { useNavigate } from "react-router-dom";
import { useAppSelector } from "../hooks/useAppSelector";
import { acknowledgeAlarm, acknowledgeAllAlarms, type Alarm } from "../services/alarms";
import { selectActiveAlarmsPreview } from "../store/slices/alarmsSlice";
import { showToast } from "../utils/toast";
import { useDisplayTimezone } from "../hooks/useDisplayTimezone";
import { useTranslation } from "../hooks/useTranslation";
import { formatTimestamp } from "../utils/timezone";
import { isSystemUser } from "../utils/systemUser";
import { translateAlarmDescription } from "../utils/alarmCatalog";
import {
  alarmDelayBadgeClass,
  formatDelayRemaining,
  isUnacknowledgedAlarm,
} from "../utils/alarmState";

const MENU_WIDTH = 240;
const MENU_HEIGHT = 96;
const MENU_PAD = 8;
const OUTSIDE_LISTENER_DELAY_MS = 100;

function clampMenuPosition(clientX: number, clientY: number): { x: number; y: number } {
  const maxX = Math.max(MENU_PAD, window.innerWidth - MENU_WIDTH - MENU_PAD);
  const maxY = Math.max(MENU_PAD, window.innerHeight - MENU_HEIGHT - MENU_PAD);
  return {
    x: Math.min(Math.max(MENU_PAD, clientX), maxX),
    y: Math.min(Math.max(MENU_PAD, clientY - MENU_HEIGHT), maxY),
  };
}

export function Footer() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const user = useAppSelector((s) => s.auth.user);
  const preview = useAppSelector(selectActiveAlarmsPreview);
  const { timeZone } = useDisplayTimezone();
  const [contextMenu, setContextMenu] = useState<{
    visible: boolean;
    x: number;
    y: number;
    alarmName: string | null;
  }>({
    visible: false,
    x: 0,
    y: 0,
    alarmName: null,
  });
  const [acknowledging, setAcknowledging] = useState<string | null>(null);
  const [acknowledgingAll, setAcknowledgingAll] = useState(false);
  const contextMenuRef = useRef<HTMLDivElement>(null);
  const pendingAlarmNameRef = useRef<string | null>(null);

  const activeAlarms: (Alarm | null)[] = [...preview];
  while (activeAlarms.length < 3) {
    activeAlarms.push(null);
  }

  const closeContextMenu = () => {
    pendingAlarmNameRef.current = null;
    setContextMenu({ visible: false, x: 0, y: 0, alarmName: null });
  };

  useEffect(() => {
    if (!contextMenu.visible) {
      return undefined;
    }
    const handlePointerDown = (event: MouseEvent) => {
      if (contextMenuRef.current?.contains(event.target as Node)) {
        return;
      }
      closeContextMenu();
    };
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        closeContextMenu();
      }
    };
    const timer = window.setTimeout(() => {
      document.addEventListener("mousedown", handlePointerDown);
    }, OUTSIDE_LISTENER_DELAY_MS);
    document.addEventListener("keydown", handleKeyDown);
    return () => {
      window.clearTimeout(timer);
      document.removeEventListener("mousedown", handlePointerDown);
      document.removeEventListener("keydown", handleKeyDown);
    };
  }, [contextMenu.visible]);

  if (isSystemUser(user)) {
    return null;
  }

  const getStateLabel = (alarm: Alarm): string => {
    if (alarm.delay_phase === "pending") {
      return t("alarms.pendingOnDelay", {
        seconds: formatDelayRemaining(alarm.on_timer_remaining),
      });
    }
    if (alarm.delay_phase === "clearing") {
      return t("alarms.clearingOffDelay", {
        seconds: formatDelayRemaining(alarm.off_timer_remaining),
      });
    }
    const state = alarm.state;
    if (typeof state === "object") {
      const raw = state.mnemonic || state.state || "-";
      return t(`alarms.states.${raw}`) !== `alarms.states.${raw}` ? t(`alarms.states.${raw}`) : String(raw);
    }
    const raw = String(state || "-");
    const key = `alarms.states.${raw}`;
    return t(key) !== key ? t(key) : raw;
  };

  const handleRowClick = () => {
    navigate("/alarms/summary");
  };

  const handleRowDoubleClick = (alarm: Alarm) => {
    if (acknowledging || acknowledgingAll) return;
    const alarmName = alarm.name;
    if (!alarmName) return;
    void runAcknowledgeOne(alarmName);
  };

  const handleRowContextMenu = (e: React.MouseEvent, alarm: Alarm) => {
    e.preventDefault();
    e.stopPropagation();
    const alarmName = alarm.name || null;
    pendingAlarmNameRef.current = alarmName;
    const { x, y } = clampMenuPosition(e.clientX, e.clientY);
    setContextMenu({
      visible: true,
      x,
      y,
      alarmName,
    });
  };

  const runAcknowledgeOne = async (alarmName: string) => {
    if (acknowledging || acknowledgingAll) return;
    setAcknowledging(alarmName);
    closeContextMenu();
    try {
      const response = await acknowledgeAlarm(alarmName);
      const message =
        response?.message ||
        response?.data?.message ||
        t("alarms.acknowledgeOneSuccess", { name: alarmName });
      showToast(message, "success");
    } catch (error: any) {
      const errorMessage =
        error?.response?.data?.message ||
        error?.message ||
        t("alarms.acknowledgeOneError", { name: alarmName });
      showToast(errorMessage, "error");
    } finally {
      setAcknowledging(null);
    }
  };

  const runAcknowledgeAll = async () => {
    if (acknowledging || acknowledgingAll) return;
    setAcknowledgingAll(true);
    closeContextMenu();
    try {
      const response = await acknowledgeAllAlarms();
      const message =
        response?.message ||
        response?.data?.message ||
        t("alarms.acknowledgeAllSuccess");
      showToast(message, "success");
    } catch (error: any) {
      const errorMessage =
        error?.response?.data?.message ||
        error?.message ||
        t("alarms.acknowledgeAllError");
      showToast(errorMessage, "error");
    } finally {
      setAcknowledgingAll(false);
    }
  };

  const handleAcknowledgeAlarm = (event: React.MouseEvent) => {
    event.preventDefault();
    event.stopPropagation();
    const alarmName = pendingAlarmNameRef.current || contextMenu.alarmName;
    if (!alarmName) return;
    void runAcknowledgeOne(alarmName);
  };

  const handleAcknowledgeAll = (event: React.MouseEvent) => {
    event.preventDefault();
    event.stopPropagation();
    void runAcknowledgeAll();
  };

  const contextMenuNode =
    contextMenu.visible &&
    createPortal(
      <div
        ref={contextMenuRef}
        className="dropdown-menu show footer-alarm-context-menu"
        role="menu"
        style={{
          position: "fixed",
          top: `${contextMenu.y}px`,
          left: `${contextMenu.x}px`,
          zIndex: 2000,
          minWidth: `${MENU_WIDTH}px`,
        }}
      >
        {contextMenu.alarmName && (
          <button
            type="button"
            className="dropdown-item"
            role="menuitem"
            onMouseDown={handleAcknowledgeAlarm}
            disabled={acknowledging === contextMenu.alarmName || acknowledgingAll}
          >
            <i className="bi bi-check-circle me-2"></i>
            {t("alarms.acknowledgeOne")}
          </button>
        )}
        <button
          type="button"
          className="dropdown-item"
          role="menuitem"
          onMouseDown={handleAcknowledgeAll}
          disabled={acknowledging !== null || acknowledgingAll}
        >
          <i className="bi bi-check-all me-2"></i>
          {t("alarms.acknowledgeAll")}
        </button>
      </div>,
      document.body
    );

  return (
    <footer className="app-footer text-sm">
      <table className="table table-sm table-borderless mb-0 footer-alarms-table">
        <thead>
          <tr>
            <th>{t("tables.name")}</th>
            <th>{t("tables.type")}</th>
            <th>{t("tables.state")}</th>
            <th>{t("tables.triggerValue")}</th>
            <th>{t("tables.alarmDateTime")}</th>
            <th>{t("alarms.ackTimestamp")}</th>
          </tr>
        </thead>
        <tbody>
          {activeAlarms.map((alarm, index) => {
            if (!alarm) {
              return (
                <tr key={`empty-${index}`} className="footer-alarm-row-empty">
                  <td>-</td>
                  <td>-</td>
                  <td>-</td>
                  <td>-</td>
                  <td>-</td>
                  <td>-</td>
                </tr>
              );
            }

            const isUnack = isUnacknowledgedAlarm(alarm.state);
            const alarmType = alarm.alarm_type || alarm.alarm_setpoint?.type || "-";
            const triggerValue =
              alarm.trigger_value !== undefined
                ? String(alarm.trigger_value)
                : alarm.alarm_setpoint?.value !== undefined
                  ? String(alarm.alarm_setpoint.value)
                  : "-";
            const delayPhase = alarm.delay_phase;
            const rowColor =
              delayPhase === "pending" ? "#f9a825" : delayPhase === "clearing" ? "#29b6f6" : "#dc3545";
            const rowText = delayPhase === "pending" || delayPhase === "clearing" ? "#212121" : "#fff";
            const delayBadge = alarmDelayBadgeClass(delayPhase);

            return (
              <tr
                key={alarm.identifier || alarm.id || alarm.name}
                className={`footer-alarm-row ${isUnack ? "alarm-unacknowledged" : "alarm-acknowledged"}`}
                onClick={handleRowClick}
                onDoubleClick={() => handleRowDoubleClick(alarm)}
                onContextMenu={(e) => handleRowContextMenu(e, alarm)}
                style={{
                  cursor: "pointer",
                  backgroundColor: rowColor,
                  color: rowText,
                }}
              >
                <td style={{ backgroundColor: rowColor, color: rowText }}>
                  <span
                    title={translateAlarmDescription(alarm.description, alarm.name, t)}
                    style={{ cursor: alarm.tag || alarm.description ? "help" : "default", color: rowText }}
                  >
                    {alarm.name || "-"}
                  </span>
                </td>
                <td style={{ backgroundColor: rowColor, color: rowText }}>
                  <span className="badge" style={{ backgroundColor: "rgba(255, 255, 255, 0.2)", color: rowText }}>
                    {alarmType}
                  </span>
                </td>
                <td style={{ backgroundColor: rowColor, color: rowText }}>
                  <span
                    className={`badge ${delayBadge || ""}`}
                    style={delayBadge ? undefined : { backgroundColor: "rgba(255, 255, 255, 0.2)", color: rowText }}
                  >
                    {getStateLabel(alarm)}
                  </span>
                </td>
                <td style={{ backgroundColor: rowColor, color: rowText }}>{triggerValue}</td>
                <td style={{ backgroundColor: rowColor, color: rowText }}>
                  {formatTimestamp(alarm.timestamp, timeZone) || "-"}
                </td>
                <td style={{ backgroundColor: rowColor, color: rowText }}>
                  {formatTimestamp(alarm.ack_timestamp, timeZone) || "-"}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
      {contextMenuNode}
    </footer>
  );
}
