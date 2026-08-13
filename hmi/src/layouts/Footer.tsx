import { useEffect, useState, useRef } from "react";
import { useNavigate } from "react-router-dom";
import { useAppSelector } from "../hooks/useAppSelector";
import { acknowledgeAlarm, acknowledgeAllAlarms, type Alarm } from "../services/alarms";
import { selectActiveAlarmsPreview } from "../store/slices/alarmsSlice";
import { showToast } from "../utils/toast";

export function Footer() {
  const navigate = useNavigate();
  const preview = useAppSelector(selectActiveAlarmsPreview);
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

  const activeAlarms: (Alarm | null)[] = [...preview];
  while (activeAlarms.length < 3) {
    activeAlarms.push(null);
  }

  // Close context menu when clicking outside
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (contextMenuRef.current && !contextMenuRef.current.contains(event.target as Node)) {
        setContextMenu({ visible: false, x: 0, y: 0, alarmName: null });
      }
    };

    if (contextMenu.visible) {
      document.addEventListener("mousedown", handleClickOutside);
      return () => {
        document.removeEventListener("mousedown", handleClickOutside);
      };
    }
  }, [contextMenu.visible]);

  const getStateLabel = (alarm: Alarm): string => {
    const state = alarm.state;
    if (typeof state === "object") {
      return state.mnemonic || state.state || "-";
    }
    return String(state || "-");
  };

  const isUnacknowledged = (alarm: Alarm): boolean => {
    const state = alarm.state;
    if (typeof state === "object") {
      const stateStr = state.mnemonic || state.state || "";
      return stateStr.includes("UNACK");
    }
    return String(state).includes("Unacknowledged");
  };

  const handleRowClick = (alarm: Alarm) => {
    navigate("/alarms/summary");
  };

  const handleRowDoubleClick = async (alarm: Alarm) => {
    if (acknowledging || acknowledgingAll) return;
    const alarmName = alarm.name;
    if (!alarmName) return;

    setAcknowledging(alarmName);
    try {
      const response = await acknowledgeAlarm(alarmName);
      const message = response?.message || response?.data?.message || `${alarmName} was acknowledged successfully`;
      showToast(message, "success");
    } catch (error: any) {
      const errorMessage = error?.response?.data?.message || error?.message || `Error acknowledging alarm ${alarmName}`;
      showToast(errorMessage, "error");
    } finally {
      setAcknowledging(null);
    }
  };

  const handleRowContextMenu = (e: React.MouseEvent, alarm: Alarm) => {
    e.preventDefault();
    e.stopPropagation();
    setContextMenu({
      visible: true,
      x: e.clientX,
      y: e.clientY,
      alarmName: alarm.name || null,
    });
  };

  const handleAcknowledgeAlarm = async () => {
    if (!contextMenu.alarmName || acknowledging || acknowledgingAll) return;

    const alarmName = contextMenu.alarmName;
    setAcknowledging(alarmName);
    setContextMenu({ visible: false, x: 0, y: 0, alarmName: null });
    try {
      const response = await acknowledgeAlarm(alarmName);
      const message = response?.message || response?.data?.message || `${alarmName} was acknowledged successfully`;
      showToast(message, "success");
    } catch (error: any) {
      const errorMessage = error?.response?.data?.message || error?.message || `Error acknowledging alarm ${alarmName}`;
      showToast(errorMessage, "error");
    } finally {
      setAcknowledging(null);
    }
  };

  const handleAcknowledgeAll = async () => {
    if (acknowledging || acknowledgingAll) return;

    setAcknowledgingAll(true);
    setContextMenu({ visible: false, x: 0, y: 0, alarmName: null });
    try {
      const response = await acknowledgeAllAlarms();
      const message = response?.message || response?.data?.message || "Alarms were acknowledged successfully";
      showToast(message, "success");
    } catch (error: any) {
      const errorMessage = error?.response?.data?.message || error?.message || "Error acknowledging all alarms";
      showToast(errorMessage, "error");
    } finally {
      setAcknowledgingAll(false);
    }
  };

  return (
    <footer className="app-footer text-sm">
      <table className="table table-sm table-borderless mb-0 footer-alarms-table">
        <thead>
          <tr>
            <th>Name</th>
            <th>Type</th>
            <th>State</th>
            <th>Trigger Value</th>
            <th>Alarm Time</th>
            <th>Ack Timestamp</th>
          </tr>
        </thead>
        <tbody>
          {activeAlarms.map((alarm, index) => {
            if (!alarm) {
              // Empty row
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
            
            const isUnack = isUnacknowledged(alarm);
            const alarmType = alarm.alarm_type || (alarm.alarm_setpoint?.type) || "-";
            const triggerValue = alarm.trigger_value !== undefined 
              ? String(alarm.trigger_value)
              : (alarm.alarm_setpoint?.value !== undefined ? String(alarm.alarm_setpoint.value) : "-");
            
            return (
              <tr
                key={alarm.identifier || alarm.id || alarm.name}
                className={`footer-alarm-row ${isUnack ? "alarm-unacknowledged" : "alarm-acknowledged"}`}
                onClick={() => handleRowClick(alarm)}
                onDoubleClick={() => handleRowDoubleClick(alarm)}
                onContextMenu={(e) => handleRowContextMenu(e, alarm)}
                style={{ 
                  cursor: "pointer",
                  backgroundColor: "#dc3545",
                  color: "#fff"
                }}
              >
                <td style={{ backgroundColor: "#dc3545", color: "#fff" }}>
                  <span
                    title={alarm.tag || undefined}
                    style={{ cursor: alarm.tag ? "help" : "default", color: "#fff" }}
                  >
                    {alarm.name || "-"}
                  </span>
                </td>
                <td style={{ backgroundColor: "#dc3545", color: "#fff" }}>
                  <span className="badge" style={{ backgroundColor: "rgba(255, 255, 255, 0.2)", color: "#fff" }}>{alarmType}</span>
                </td>
                <td style={{ backgroundColor: "#dc3545", color: "#fff" }}>
                  <span className="badge" style={{ backgroundColor: "rgba(255, 255, 255, 0.2)", color: "#fff" }}>{getStateLabel(alarm)}</span>
                </td>
                <td style={{ backgroundColor: "#dc3545", color: "#fff" }}>{triggerValue}</td>
                <td style={{ backgroundColor: "#dc3545", color: "#fff" }}>
                  {alarm.timestamp || "-"}
                </td>
                <td style={{ backgroundColor: "#dc3545", color: "#fff" }}>
                  {alarm.ack_timestamp || "-"}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>

      {/* Context Menu */}
      {contextMenu.visible && (
        <div
          ref={contextMenuRef}
          className="dropdown-menu show"
          style={{
            position: "fixed",
            bottom: `${window.innerHeight - contextMenu.y}px`,
            left: `${contextMenu.x}px`,
            zIndex: 1000,
            transform: "translateY(0)",
          }}
        >
          {contextMenu.alarmName && (
            <button
              className="dropdown-item"
              onClick={handleAcknowledgeAlarm}
              disabled={acknowledging === contextMenu.alarmName || acknowledgingAll}
            >
              <i className="bi bi-check-circle me-2"></i>
              Reconocer Alarma
            </button>
          )}
          <button
            className="dropdown-item"
            onClick={handleAcknowledgeAll}
            disabled={acknowledging !== null || acknowledgingAll}
          >
            <i className="bi bi-check-all me-2"></i>
            Reconocer Todas
          </button>
        </div>
      )}
    </footer>
  );
}
