import { useEffect, useState, useMemo, memo, useRef } from "react";
import { Card } from "../components/Card";
import { Button } from "../components/Button";
import { getAlarms, createAlarm, updateAlarm, deleteAlarm, getAlarmByName, executeAlarmAction, shelveAlarm, type Alarm, type AlarmsResponse } from "../services/alarms";
import { getTags, type Tag } from "../services/tags";
import { useTranslation } from "../hooks/useTranslation";
import { useAppSelector } from "../hooks/useAppSelector";
import { useAppDispatch } from "../hooks/useAppDispatch";
import { loadAllAlarms } from "../store/slices/alarmsSlice";
import { showToast } from "../utils/toast";

export function Alarms() {
  const { t } = useTranslation();
  const dispatch = useAppDispatch();
  const [alarms, setAlarms] = useState<Alarm[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [showEditModal, setShowEditModal] = useState(false);
  const [showDeleteModal, setShowDeleteModal] = useState(false);
  const [editingAlarm, setEditingAlarm] = useState<Alarm | null>(null);
  const [alarmToDelete, setAlarmToDelete] = useState<Alarm | null>(null);
  const [creating, setCreating] = useState(false);
  const [updating, setUpdating] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [availableTags, setAvailableTags] = useState<Tag[]>([]);
  const [loadingTags, setLoadingTags] = useState(false);
  const [pagination, setPagination] = useState({
    page: 1,
    limit: 20,
    total: 0,
    pages: 0,
  });
  const [alarmActions, setAlarmActions] = useState<Record<string, { [key: string]: string }>>({});
  const [loadingActions, setLoadingActions] = useState<Record<string, boolean>>({});
  const [executingAction, setExecutingAction] = useState<Record<string, boolean>>({});
  const [openActionDropdowns, setOpenActionDropdowns] = useState<Record<string, boolean>>({});
  const actionDropdownRefs = useRef<Record<string, HTMLDivElement | null>>({});
  const [showShelveModal, setShowShelveModal] = useState(false);
  const [alarmToShelve, setAlarmToShelve] = useState<string | null>(null);
  const [shelveDuration, setShelveDuration] = useState({
    seconds: 0,
    minutes: 0,
    hours: 0,
    days: 0,
    weeks: 0,
  });
  const [shelving, setShelving] = useState(false);
  
  // Form state
  const [formData, setFormData] = useState({
    name: "",
    tag: "",
    alarm_type: "BOOL",
    trigger_value: "",
    description: "",
  });

  const alarmTypes = ["BOOL", "HIGH", "LOW", "HIGH-HIGH", "LOW-LOW"];

  // Get real-time data from Redux store
  const realTimeAlarms = useAppSelector((state) => state.alarms.alarms);
  const tagValues = useAppSelector((state) => state.tags.tagValues);

  // Memoized row component to prevent unnecessary re-renders
  const AlarmTableRow = memo(({ 
    alarm, 
    realTimeAlarms,
    tagValues,
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
    actionDropdownRef
  }: {
    alarm: Alarm;
    realTimeAlarms: Record<string, Alarm>;
    tagValues: Record<string, Tag>;
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
  }) => {
    // Get real-time alarm data from store if available, otherwise use alarm prop
    const alarmKey = alarm.identifier || alarm.id || alarm.name;
    const realTimeAlarm = alarmKey ? realTimeAlarms[String(alarmKey)] : null;
    const currentAlarm = realTimeAlarm || alarm;

    // Get real-time tag value if available
    const tagName = currentAlarm.tag;
    const realTimeTag = tagName ? tagValues[tagName] : null;
    const tagValue = realTimeTag?.value !== undefined && realTimeTag?.value !== null
      ? realTimeTag.value 
      : null;
    
    const displayTagValue = tagValue !== undefined && tagValue !== null
      ? typeof tagValue === "boolean"
        ? tagValue ? "true" : "false"
        : String(tagValue)
      : "-";

    const alarmType = currentAlarm.alarm_type || (currentAlarm.alarm_setpoint?.type) || "-";
    const triggerValue = currentAlarm.trigger_value !== undefined 
      ? String(currentAlarm.trigger_value)
      : (currentAlarm.alarm_setpoint?.value !== undefined ? String(currentAlarm.alarm_setpoint.value) : "-");

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
          <span className="badge bg-primary">
            {alarmType}
          </span>
        </td>
        <td>{displayTagValue}</td>
        <td>{triggerValue}</td>
        <td>{currentAlarm.description || "-"}</td>
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
            <div 
              className="btn-group" 
              ref={actionDropdownRef}
              style={{ position: "relative" }}
            >
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
                    <div className="dropdown-item-text text-muted">
                      {t("alarms.noActionsAvailable")}
                    </div>
                  )}
                </div>
              )}
            </div>
          </div>
        </td>
      </tr>
    );
  }, (prevProps, nextProps) => {
    // Custom comparison function for memo
    const prevAlarmKey = prevProps.alarm.identifier || prevProps.alarm.id || prevProps.alarm.name;
    const nextAlarmKey = nextProps.alarm.identifier || nextProps.alarm.id || nextProps.alarm.name;
    
    // Get real-time alarm data
    const prevRealTimeAlarm = prevAlarmKey ? prevProps.realTimeAlarms[String(prevAlarmKey)] : null;
    const nextRealTimeAlarm = nextAlarmKey ? nextProps.realTimeAlarms[String(nextAlarmKey)] : null;
    const prevAlarm = prevRealTimeAlarm || prevProps.alarm;
    const nextAlarm = nextRealTimeAlarm || nextProps.alarm;

    // Get real-time tag values
    const prevTagName = prevAlarm.tag;
    const nextTagName = nextAlarm.tag;
    const prevTagValue = prevTagName ? prevProps.tagValues[prevTagName]?.value : undefined;
    const nextTagValue = nextTagName ? nextProps.tagValues[nextTagName]?.value : undefined;

    // Re-render if:
    // - Alarm ID/name changed
    // - Alarm state changed
    // - Tag value changed
    // - Other alarm properties changed
    // - Actions changed
    // - Loading/executing state changed
    return (
      prevAlarmKey === nextAlarmKey &&
      prevAlarm.name === nextAlarm.name &&
      prevAlarm.tag === nextAlarm.tag &&
      prevAlarm.alarm_type === nextAlarm.alarm_type &&
      prevAlarm.trigger_value === nextAlarm.trigger_value &&
      prevAlarm.description === nextAlarm.description &&
      JSON.stringify(prevAlarm.state) === JSON.stringify(nextAlarm.state) &&
      prevTagValue === nextTagValue &&
      JSON.stringify(prevProps.actions) === JSON.stringify(nextProps.actions) &&
      prevProps.loadingActions === nextProps.loadingActions &&
      prevProps.executingAction === nextProps.executingAction &&
      prevProps.isActionDropdownOpen === nextProps.isActionDropdownOpen
    );
  });

  AlarmTableRow.displayName = "AlarmTableRow";

  const loadAlarms = async (page: number = pagination.page, limit: number = pagination.limit) => {
    setLoading(true);
    setError(null);
    try {
      const response: AlarmsResponse = await getAlarms(page, limit);
      const loadedAlarms = response.data || [];
      setAlarms(loadedAlarms);
      setPagination(response.pagination || {
        page: page,
        limit: limit,
        total: 0,
        pages: 0,
      });
      
      // Update Redux buffer with all alarms (get all for buffer)
      try {
        const allAlarmsResponse = await getAlarms(1, 10000);
        if (allAlarmsResponse.data) {
          dispatch(loadAllAlarms(allAlarmsResponse.data));
        }
      } catch (_e) {
        // Silently fail - buffer update is not critical
      }
    } catch (e: any) {
      const data = e?.response?.data;
      const backendMessage =
        (typeof data === "string" ? data : undefined) ??
        data?.message ??
        data?.detail ??
        data?.error;
      const errorMsg = backendMessage || e?.message || t("alarms.loadError");
      setError(errorMsg);
      setAlarms([]);
    } finally {
      setLoading(false);
    }
  };

  const loadTags = async () => {
    setLoadingTags(true);
    try {
      const response = await getTags(1, 1000); // Obtener todos los tags
      setAvailableTags(response.data || []);
    } catch (e: any) {
      console.error("Error loading tags:", e);
      setAvailableTags([]);
    } finally {
      setLoadingTags(false);
    }
  };

  useEffect(() => {
    loadAlarms(1, 20);
    loadTags();
  }, []);

  // Update local alarms state when real-time alarms change
  useEffect(() => {
    if (Object.keys(realTimeAlarms).length > 0) {
      setAlarms((prevAlarms) => {
        // Update only alarms that are in the current page
        return prevAlarms.map((alarm) => {
          const key = alarm.identifier || alarm.id || alarm.name;
          if (key && realTimeAlarms[String(key)]) {
            // Merge real-time data with existing alarm data
            return { ...alarm, ...realTimeAlarms[String(key)] };
          }
          return alarm;
        });
      });
    }
  }, [realTimeAlarms]);

  // Cargar tags cuando se abre el modal
  useEffect(() => {
    if ((showCreateModal || showEditModal) && availableTags.length === 0) {
      loadTags();
    }
  }, [showCreateModal, showEditModal]);

  // Close action dropdowns when clicking outside
  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      const target = e.target as HTMLElement;
      // Don't close if clicking on a dropdown toggle button
      if (target.closest('.dropdown-toggle') || target.closest('.dropdown-menu')) {
        return;
      }
      Object.keys(openActionDropdowns).forEach((alarmName) => {
        if (openActionDropdowns[alarmName]) {
          const ref = actionDropdownRefs.current[alarmName];
          if (ref && !ref.contains(target)) {
            setOpenActionDropdowns((prev) => ({ ...prev, [alarmName]: false }));
          }
        }
      });
    };
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, [openActionDropdowns]);

  const loadAlarmActions = async (alarmName: string) => {
    if (loadingActions[alarmName] || alarmActions[alarmName]) {
      return; // Already loading or loaded
    }

    setLoadingActions((prev) => ({ ...prev, [alarmName]: true }));
    try {
      const alarm = await getAlarmByName(alarmName);
      if (alarm.actions) {
        setAlarmActions((prev) => ({ ...prev, [alarmName]: alarm.actions! }));
      }
    } catch (e: any) {
      console.error(`Error loading actions for alarm ${alarmName}:`, e);
    } finally {
      setLoadingActions((prev) => ({ ...prev, [alarmName]: false }));
    }
  };

  const handleExecuteAction = async (actionValue: string, alarmName: string) => {
    // If action is "shelve", open modal instead of executing directly
    if (actionValue === "shelve") {
      setAlarmToShelve(alarmName);
      setShowShelveModal(true);
      setShelveDuration({
        seconds: 0,
        minutes: 0,
        hours: 0,
        days: 0,
        weeks: 0,
      });
      return;
    }

    // For other actions, execute directly
    setExecutingAction((prev) => ({ ...prev, [alarmName]: true }));
    try {
      const result = await executeAlarmAction(actionValue, alarmName);
      showToast("success", result.message || t("alarms.actionExecutedSuccess", { alarmName }));
      
      // Reload alarms to get updated state
      await loadAlarms(pagination.page, pagination.limit);
      
      // Clear cached actions to reload them next time
      setAlarmActions((prev) => {
        const updated = { ...prev };
        delete updated[alarmName];
        return updated;
      });
    } catch (e: any) {
      const data = e?.response?.data;
      const backendMessage =
        (typeof data === "string" ? data : undefined) ??
        data?.message ??
        data?.detail ??
        data?.error;
      const errorMsg =
        backendMessage || e?.message || t("alarms.executeActionError", { alarmName });
      showToast("error", errorMsg);
    } finally {
      setExecutingAction((prev) => ({ ...prev, [alarmName]: false }));
    }
  };

  const handleShelveAlarm = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!alarmToShelve) return;

    // Validate that at least one duration field is set
    const hasDuration = shelveDuration.seconds > 0 || 
                       shelveDuration.minutes > 0 || 
                       shelveDuration.hours > 0 || 
                       shelveDuration.days > 0 || 
                       shelveDuration.weeks > 0;

    if (!hasDuration) {
      setError(t("alarms.durationRequired"));
      return;
    }

    setShelving(true);
    setError(null);
    try {
      // Build payload with only non-zero values
      const payload: any = {};
      if (shelveDuration.seconds > 0) payload.seconds = shelveDuration.seconds;
      if (shelveDuration.minutes > 0) payload.minutes = shelveDuration.minutes;
      if (shelveDuration.hours > 0) payload.hours = shelveDuration.hours;
      if (shelveDuration.days > 0) payload.days = shelveDuration.days;
      if (shelveDuration.weeks > 0) payload.weeks = shelveDuration.weeks;

      const result = await shelveAlarm(alarmToShelve, payload);
      showToast("success", result.message || t("alarms.shelveSuccess", { alarmName: alarmToShelve }));
      
      // Close modal
      setShowShelveModal(false);
      setAlarmToShelve(null);
      setShelveDuration({
        seconds: 0,
        minutes: 0,
        hours: 0,
        days: 0,
        weeks: 0,
      });
      
      // Close action dropdown
      setOpenActionDropdowns((prev) => ({ ...prev, [alarmToShelve]: false }));
      
      // Reload alarms to get updated state
      await loadAlarms(pagination.page, pagination.limit);
      
      // Clear cached actions to reload them next time
      setAlarmActions((prev) => {
        const updated = { ...prev };
        delete updated[alarmToShelve];
        return updated;
      });
    } catch (e: any) {
      const data = e?.response?.data;
      const backendMessage =
        (typeof data === "string" ? data : undefined) ??
        data?.message ??
        data?.detail ??
        data?.error;
      const errorMsg =
        backendMessage ||
        e?.message ||
        t("alarms.shelveError", { alarmName: alarmToShelve });
      setError(errorMsg);
      showToast("error", errorMsg);
    } finally {
      setShelving(false);
    }
  };

  const toggleActionDropdown = (alarmName: string) => {
    setOpenActionDropdowns((prev) => ({
      ...prev,
      [alarmName]: !prev[alarmName],
    }));
  };

  const handlePageChange = (newPage: number) => {
    if (newPage >= 1 && newPage <= pagination.pages) {
      loadAlarms(newPage, pagination.limit);
    }
  };

  const handleLimitChange = (newLimit: number) => {
    if (newLimit > 0) {
      loadAlarms(1, newLimit);
    }
  };

  const handleEditAlarm = (alarm: Alarm) => {
    if (!alarm.identifier && !alarm.id) {
      setError(t("alarms.noIdToEdit"));
      return;
    }
    
    // Extraer alarm_type y trigger_value de la estructura de la alarma
    const alarmType = alarm.alarm_type || (alarm.alarm_setpoint?.type) || "BOOL";
    const triggerValue = alarm.trigger_value !== undefined 
      ? alarm.trigger_value 
      : (alarm.alarm_setpoint?.value !== undefined ? alarm.alarm_setpoint.value : "");
    
    // Cargar datos de la alarma en el formulario
    setFormData({
      name: alarm.name || "",
      tag: alarm.tag || "",
      alarm_type: alarmType,
      trigger_value: triggerValue !== undefined ? String(triggerValue) : "",
      description: alarm.description || "",
    });
    
    setEditingAlarm(alarm);
    setShowEditModal(true);
    setError(null);
  };

  const handleDeleteAlarm = (alarm: Alarm) => {
    if (!alarm.identifier && !alarm.id) {
      setError(t("alarms.noIdToDelete"));
      return;
    }
    
    setAlarmToDelete(alarm);
    setShowDeleteModal(true);
    setError(null);
  };

  const handleExportCSV = async () => {
    try {
      setError(null);
      // Obtener todas las alarmas (sin paginación)
      const response = await getAlarms(1, 10000);
      const allAlarms = response.data || [];
      
      if (!allAlarms || allAlarms.length === 0) {
        setError(t("alarms.noAlarmsToExport"));
        return;
      }

      // Preparar los datos para CSV
      const headers = [
        t("tables.name"),
        t("tables.tag"),
        t("alarms.alarmType"),
        t("tables.triggerValue"),
        t("tables.description"),
        t("tables.state"),
        t("alarms.mnemonic"),
        t("tables.timestamp"),
        t("alarms.ackTimestamp")
      ];

      // Convertir alarmas a filas CSV
      const rows = allAlarms.map((alarm: Alarm) => {
        const alarmType = alarm.alarm_type || (alarm.alarm_setpoint?.type) || "";
        const triggerValue = alarm.trigger_value !== undefined 
          ? alarm.trigger_value 
          : (alarm.alarm_setpoint?.value !== undefined ? alarm.alarm_setpoint.value : "");
        const state = typeof alarm.state === "object" ? alarm.state : {};
        const stateMnemonic = typeof state === "object" && state.mnemonic ? state.mnemonic : (typeof alarm.state === "string" ? alarm.state : "");
        const stateName = typeof state === "object" && state.state ? state.state : "";
        
        return [
          alarm.name || "",
          alarm.tag || "",
          alarmType,
          triggerValue !== undefined ? String(triggerValue) : "",
          alarm.description || "",
          stateName || "",
          stateMnemonic || "",
          alarm.timestamp || "",
          alarm.ack_timestamp || ""
        ];
      });

      // Crear contenido CSV
      const csvContent = [
        headers.join(","),
        ...rows.map(row => 
          row.map(cell => {
            // Escapar comillas y envolver en comillas si contiene comas o comillas
            const cellStr = String(cell);
            if (cellStr.includes(",") || cellStr.includes('"') || cellStr.includes("\n")) {
              return `"${cellStr.replace(/"/g, '""')}"`;
            }
            return cellStr;
          }).join(",")
        )
      ].join("\n");

      // Crear blob y descargar
      const blob = new Blob([csvContent], { type: "text/csv;charset=utf-8;" });
      const link = document.createElement("a");
      const url = URL.createObjectURL(blob);
      
      link.setAttribute("href", url);
      link.setAttribute("download", `alarms_${new Date().toISOString().split("T")[0]}.csv`);
      link.style.visibility = "hidden";
      
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      
      URL.revokeObjectURL(url);
    } catch (e: any) {
      const data = e?.response?.data;
      const backendMessage =
        (typeof data === "string" ? data : undefined) ??
        data?.message ??
        data?.detail ??
        data?.error;
      const errorMsg =
        backendMessage || e?.message || t("alarms.exportError");
      setError(errorMsg);
    }
  };

  const confirmDeleteAlarm = async () => {
    if (!alarmToDelete || (!alarmToDelete.identifier && !alarmToDelete.id)) {
      setError(t("alarms.noAlarmSelectedToDelete"));
      return;
    }

    setDeleting(true);
    setError(null);

    try {
      const alarmId = alarmToDelete.identifier || alarmToDelete.id;
      await deleteAlarm(alarmId!);
      
      // Cerrar modal y limpiar
      setShowDeleteModal(false);
      setAlarmToDelete(null);
      
      // Recargar alarmas and update buffer
      await loadAlarms(pagination.page, pagination.limit);
    } catch (e: any) {
      const data = e?.response?.data;
      const backendMessage =
        (typeof data === "string" ? data : undefined) ??
        data?.message ??
        data?.detail ??
        data?.error;
      const errorMsg =
        backendMessage || e?.message || t("alarms.deleteError");
      setError(errorMsg);
    } finally {
      setDeleting(false);
    }
  };

  const handleUpdateAlarm = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!editingAlarm || (!editingAlarm.identifier && !editingAlarm.id)) {
      setError(t("alarms.noAlarmSelectedToUpdate"));
      return;
    }
    
    setUpdating(true);
    setError(null);
    
    try {
      // Preparar payload solo con campos que han cambiado
      const payload: any = {
        id: editingAlarm.identifier || editingAlarm.id,
      };

      // Comparar valores originales con los nuevos
      const original = editingAlarm;
      
      // Comparar name
      if (formData.name !== (original.name || "")) {
        payload.name = formData.name;
      }
      
      // Comparar tag
      if (formData.tag !== (original.tag || "")) {
        payload.tag = formData.tag;
      }
      
      // Comparar alarm_type
      const originalAlarmType = original.alarm_type || (original.alarm_setpoint?.type) || "BOOL";
      if (formData.alarm_type !== originalAlarmType) {
        payload.alarm_type = formData.alarm_type;
      }
      
      // Comparar trigger_value
      const originalTriggerValue = original.trigger_value !== undefined 
        ? original.trigger_value 
        : (original.alarm_setpoint?.value !== undefined ? original.alarm_setpoint.value : "");
      const newTriggerValue = formData.trigger_value ? 
        (formData.alarm_type === "BOOL" ? formData.trigger_value === "true" : parseFloat(formData.trigger_value)) : 
        "";
      
      if (String(newTriggerValue) !== String(originalTriggerValue)) {
        payload.trigger_value = newTriggerValue;
      }
      
      // Comparar description
      if (formData.description !== (original.description || "")) {
        payload.description = formData.description;
      }

      // Si no hay campos para actualizar, mostrar error
      const fieldsToUpdate = Object.keys(payload).filter(key => key !== 'id');
      if (fieldsToUpdate.length === 0) {
        setError(t("alarms.noChangesToUpdate"));
        setUpdating(false);
        return;
      }

      await updateAlarm(payload);
      
      // Cerrar modal y resetear formulario
      setShowEditModal(false);
      setEditingAlarm(null);
      setFormData({
        name: "",
        tag: "",
        alarm_type: "BOOL",
        trigger_value: "",
        description: "",
      });
      
      // Recargar alarmas
      loadAlarms(pagination.page, pagination.limit);
    } catch (e: any) {
      const data = e?.response?.data;
      const backendMessage =
        (typeof data === "string" ? data : undefined) ??
        data?.message ??
        data?.detail ??
        data?.error;
      const errorMsg =
        backendMessage || e?.message || t("alarms.updateError");
      setError(errorMsg);
    } finally {
      setUpdating(false);
    }
  };

  const handleCreateAlarm = async (e: React.FormEvent) => {
    e.preventDefault();
    setCreating(true);
    setError(null);
    
    try {
      // Validar campos requeridos
      if (!formData.name || !formData.tag) {
        setError(t("alarms.nameAndTagRequired"));
        setCreating(false);
        return;
      }

      // Preparar payload
      const payload: any = {
        name: formData.name,
        tag: formData.tag,
        alarm_type: formData.alarm_type || "BOOL",
      };

      // Convertir trigger_value según el tipo
      if (formData.trigger_value) {
        if (formData.alarm_type === "BOOL") {
          payload.trigger_value = formData.trigger_value === "true" || formData.trigger_value === "1";
        } else {
          payload.trigger_value = parseFloat(formData.trigger_value);
        }
      } else {
        // Valor por defecto según el tipo
        payload.trigger_value = formData.alarm_type === "BOOL" ? true : 0;
      }

      // Agregar descripción si existe
      if (formData.description) {
        payload.description = formData.description;
      }

      await createAlarm(payload);
      
      // Cerrar modal y resetear formulario
      setShowCreateModal(false);
      setFormData({
        name: "",
        tag: "",
        alarm_type: "BOOL",
        trigger_value: "",
        description: "",
      });
      
      // Recargar alarmas and update buffer
      await loadAlarms(pagination.page, pagination.limit);
    } catch (e: any) {
      const data = e?.response?.data;
      const backendMessage =
        (typeof data === "string" ? data : undefined) ??
        data?.message ??
        data?.detail ??
        data?.error;
      const errorMsg =
        backendMessage || e?.message || t("alarms.createError");
      setError(errorMsg);
    } finally {
      setCreating(false);
    }
  };

  const getStateBadgeClass = (state: any) => {
    if (!state) return "bg-secondary";
    const stateStr = typeof state === "object" ? state.mnemonic || state.state || "" : String(state);
    if (stateStr.includes("NORM") || stateStr.includes("Normal")) return "bg-success";
    if (stateStr.includes("UNACK") || stateStr.includes("Unacknowledged")) return "bg-danger";
    if (stateStr.includes("ACK") || stateStr.includes("Acknowledged")) return "bg-warning";
    if (stateStr.includes("RTN") || stateStr.includes("Return")) return "bg-info";
    return "bg-secondary";
  };

  const getStateLabel = (state: any) => {
    if (!state) return "-";
    if (typeof state === "object") {
      return state.mnemonic || state.state || "-";
    }
    return String(state);
  };

  return (
    <div className="row">
      <div className="col-12">
        <Card
          title={
            <div className="d-flex justify-content-between align-items-center w-100">
              <span>{t("navigation.alarms")}</span>
              <div className="d-flex gap-2">
                <Button
                  variant="secondary"
                  className="btn-sm"
                  onClick={handleExportCSV}
                  disabled={loading || alarms.length === 0}
                >
                  <i className="bi bi-download me-1"></i>
                  {t("alarms.exportCSV")}
                </Button>
                <Button
                  variant="success"
                  className="btn-sm"
                  onClick={() => setShowCreateModal(true)}
                >
                  <i className="bi bi-plus-circle me-1"></i>
                  {t("alarms.createAlarm")}
                </Button>
              </div>
            </div>
          }
          footer={
            <div className="d-flex justify-content-between align-items-center">
              <div className="d-flex align-items-center gap-2">
                <label className="mb-0 small">{t("pagination.itemsPerPage")}</label>
                <select
                  className="form-select form-select-sm"
                  style={{ width: "auto" }}
                  value={pagination.limit}
                  onChange={(e) => handleLimitChange(Number(e.target.value))}
                  disabled={loading}
                >
                  <option value={10}>10</option>
                  <option value={20}>20</option>
                  <option value={50}>50</option>
                  <option value={100}>100</option>
                </select>
              </div>
              <div className="d-flex align-items-center gap-2">
                <span className="small text-muted">
                  {t("pagination.pageOf", {
                    current: pagination.page,
                    total: pagination.pages,
                    count: pagination.total,
                  })}
                </span>
                <div className="btn-group" role="group">
                  <Button
                    variant="secondary"
                    className="btn-sm"
                    onClick={() => handlePageChange(1)}
                    disabled={loading || pagination.page === 1}
                  >
                    «
                  </Button>
                  <Button
                    variant="secondary"
                    className="btn-sm"
                    onClick={() => handlePageChange(pagination.page - 1)}
                    disabled={loading || pagination.page === 1}
                  >
                    ‹
                  </Button>
                  <Button
                    variant="secondary"
                    className="btn-sm"
                    onClick={() => handlePageChange(pagination.page + 1)}
                    disabled={loading || pagination.page >= pagination.pages}
                  >
                    ›
                  </Button>
                  <Button
                    variant="secondary"
                    className="btn-sm"
                    onClick={() => handlePageChange(pagination.pages)}
                    disabled={loading || pagination.page >= pagination.pages}
                  >
                    »
                  </Button>
                </div>
              </div>
            </div>
          }
        >
          {error && (
            <div className="alert alert-danger mb-3" role="alert">
              {error}
            </div>
          )}

          {loading && (
            <div className="text-center py-4">
              <div className="spinner-border text-primary" role="status">
                <span className="visually-hidden">{t("common.loading")}</span>
              </div>
            </div>
          )}

          {!loading && (
            <div className="table-responsive">
              <table className="table table-striped table-hover table-sm">
                <thead>
                  <tr>
                    <th>{t("tables.name")}</th>
                    <th>{t("tables.type")}</th>
                    <th>{t("tables.value")}</th>
                    <th>{t("tables.triggerValue")}</th>
                    <th>{t("tables.description")}</th>
                    <th>{t("tables.state")}</th>
                    <th>{t("tables.actions")}</th>
                  </tr>
                </thead>
                <tbody>
                  {alarms.length === 0 ? (
                    <tr>
                      <td colSpan={7} className="text-center text-muted py-4">
                        {t("alarms.noAlarmsAvailable")}
                      </td>
                    </tr>
                  ) : (
                    alarms.map((alarm) => {
                      const alarmName = alarm.name;
                      return (
                        <AlarmTableRow
                          key={alarm.identifier || alarm.id || alarmName}
                          alarm={alarm}
                          realTimeAlarms={realTimeAlarms}
                          tagValues={tagValues}
                          onEdit={handleEditAlarm}
                          onDelete={handleDeleteAlarm}
                          getStateBadgeClass={getStateBadgeClass}
                          getStateLabel={getStateLabel}
                          actions={alarmActions[alarmName]}
                          loadingActions={loadingActions[alarmName] || false}
                          executingAction={executingAction[alarmName] || false}
                          onLoadActions={loadAlarmActions}
                          onExecuteAction={handleExecuteAction}
                          isActionDropdownOpen={openActionDropdowns[alarmName] || false}
                          onToggleActionDropdown={toggleActionDropdown}
                          actionDropdownRef={(el) => {
                            actionDropdownRefs.current[alarmName] = el;
                          }}
                        />
                      );
                    })
                  )}
                </tbody>
              </table>
            </div>
          )}
        </Card>

        {/* Modal para crear alarma */}
        {showCreateModal && (
          <div
            className="modal fade show"
            style={{ display: "block", backgroundColor: "rgba(0,0,0,0.5)" }}
            tabIndex={-1}
            role="dialog"
          >
            <div className="modal-dialog modal-lg" role="document">
              <div className="modal-content">
                <div className="modal-header">
                  <h5 className="modal-title">{t("alarms.createNewAlarm")}</h5>
                  <button
                    type="button"
                    className="btn-close"
                    onClick={() => {
                      setShowCreateModal(false);
                      setError(null);
                    }}
                    aria-label="Close"
                  ></button>
                </div>
                <form onSubmit={handleCreateAlarm}>
                  <div className="modal-body">
                    {error && (
                      <div className="alert alert-danger" role="alert">
                        {error}
                      </div>
                    )}

                    <div className="row g-3">
                      <div className="col-md-6">
                        <label className="form-label">
                          {t("tables.name")} <span className="text-danger">*</span>
                        </label>
                        <input
                          type="text"
                          className="form-control"
                          required
                          value={formData.name}
                          onChange={(e) =>
                            setFormData({ ...formData, name: e.target.value })
                          }
                        />
                      </div>
                      <div className="col-md-6">
                        <label className="form-label">
                          {t("tables.tag")} <span className="text-danger">*</span>
                        </label>
                        <select
                          className="form-select"
                          required
                          value={formData.tag}
                          onChange={(e) =>
                            setFormData({ ...formData, tag: e.target.value })
                          }
                          disabled={loadingTags}
                        >
                          <option value="">
                            {loadingTags ? t("alarms.loadingTags") : t("alarms.selectTag")}
                          </option>
                          {availableTags.map((tag) => (
                            <option key={tag.name} value={tag.name}>
                              {tag.name}
                            </option>
                          ))}
                        </select>
                      </div>
                      <div className="col-md-6">
                        <label className="form-label">
                          {t("alarms.alarmType")} <span className="text-danger">*</span>
                        </label>
                        <select
                          className="form-select"
                          required
                          value={formData.alarm_type}
                          onChange={(e) => {
                            setFormData({ 
                              ...formData, 
                              alarm_type: e.target.value,
                              trigger_value: "" // Limpiar trigger_value al cambiar tipo
                            });
                          }}
                        >
                          {alarmTypes.map((type) => (
                            <option key={type} value={type}>
                              {type}
                            </option>
                          ))}
                        </select>
                      </div>
                      <div className="col-md-6">
                        <label className="form-label">
                          {t("tables.triggerValue")} <span className="text-danger">*</span>
                        </label>
                        {formData.alarm_type === "BOOL" ? (
                          <select
                            className="form-select"
                            required
                            value={formData.trigger_value}
                            onChange={(e) =>
                              setFormData({ ...formData, trigger_value: e.target.value })
                            }
                          >
                            <option value="">{t("alarms.selectValue")}</option>
                            <option value="true">{t("alarms.true")}</option>
                            <option value="false">{t("alarms.false")}</option>
                          </select>
                        ) : (
                          <input
                            type="number"
                            className="form-control"
                            required
                            step="0.01"
                            value={formData.trigger_value}
                            onChange={(e) =>
                              setFormData({ ...formData, trigger_value: e.target.value })
                            }
                            placeholder={t("alarms.enterTriggerValue")}
                          />
                        )}
                      </div>
                      <div className="col-12">
                        <label className="form-label">{t("tables.description")}</label>
                        <textarea
                          className="form-control"
                          rows={2}
                          value={formData.description}
                          onChange={(e) =>
                            setFormData({ ...formData, description: e.target.value })
                          }
                        />
                      </div>
                    </div>
                  </div>
                  <div className="modal-footer">
                    <button
                      type="button"
                      className="btn btn-secondary"
                      onClick={() => {
                        setShowCreateModal(false);
                        setError(null);
                      }}
                      disabled={creating}
                    >
                      {t("common.cancel")}
                    </button>
                    <Button type="submit" variant="success" loading={creating}>
                      {t("alarms.createAlarm")}
                    </Button>
                  </div>
                </form>
              </div>
            </div>
          </div>
        )}

        {/* Modal para editar alarma */}
        {showEditModal && editingAlarm && (
          <div
            className="modal fade show"
            style={{ display: "block", backgroundColor: "rgba(0,0,0,0.5)" }}
            tabIndex={-1}
            role="dialog"
          >
            <div className="modal-dialog modal-lg" role="document">
              <div className="modal-content">
                <div className="modal-header">
                  <h5 className="modal-title">{t("alarms.editAlarmTitle", { name: editingAlarm.name })}</h5>
                  <button
                    type="button"
                    className="btn-close"
                    onClick={() => {
                      setShowEditModal(false);
                      setEditingAlarm(null);
                      setError(null);
                    }}
                    aria-label="Close"
                  ></button>
                </div>
                <form onSubmit={handleUpdateAlarm}>
                  <div className="modal-body">
                    {error && (
                      <div className="alert alert-danger" role="alert">
                        {error}
                      </div>
                    )}

                    <div className="row g-3">
                      <div className="col-md-6">
                        <label className="form-label">
                          {t("tables.name")} <span className="text-danger">*</span>
                        </label>
                        <input
                          type="text"
                          className="form-control"
                          required
                          value={formData.name}
                          onChange={(e) =>
                            setFormData({ ...formData, name: e.target.value })
                          }
                        />
                      </div>
                      <div className="col-md-6">
                        <label className="form-label">
                          {t("tables.tag")} <span className="text-danger">*</span>
                        </label>
                        <select
                          className="form-select"
                          required
                          value={formData.tag}
                          onChange={(e) =>
                            setFormData({ ...formData, tag: e.target.value })
                          }
                          disabled={loadingTags}
                        >
                          <option value="">{t("alarms.selectTag")}</option>
                          {availableTags.map((tag) => (
                            <option key={tag.name} value={tag.name}>
                              {tag.name}
                            </option>
                          ))}
                        </select>
                      </div>
                      <div className="col-md-6">
                        <label className="form-label">
                          {t("alarms.alarmType")} <span className="text-danger">*</span>
                        </label>
                        <select
                          className="form-select"
                          required
                          value={formData.alarm_type}
                          onChange={(e) => {
                            setFormData({ 
                              ...formData, 
                              alarm_type: e.target.value,
                              trigger_value: "" // Limpiar trigger_value al cambiar tipo
                            });
                          }}
                        >
                          {alarmTypes.map((type) => (
                            <option key={type} value={type}>
                              {type}
                            </option>
                          ))}
                        </select>
                      </div>
                      <div className="col-md-6">
                        <label className="form-label">
                          {t("tables.triggerValue")} <span className="text-danger">*</span>
                        </label>
                        {formData.alarm_type === "BOOL" ? (
                          <select
                            className="form-select"
                            required
                            value={formData.trigger_value}
                            onChange={(e) =>
                              setFormData({ ...formData, trigger_value: e.target.value })
                            }
                          >
                            <option value="">{t("alarms.selectValue")}</option>
                            <option value="true">{t("alarms.true")}</option>
                            <option value="false">{t("alarms.false")}</option>
                          </select>
                        ) : (
                          <input
                            type="number"
                            className="form-control"
                            required
                            step="0.01"
                            value={formData.trigger_value}
                            onChange={(e) =>
                              setFormData({ ...formData, trigger_value: e.target.value })
                            }
                            placeholder={t("alarms.enterTriggerValue")}
                          />
                        )}
                      </div>
                      <div className="col-12">
                        <label className="form-label">{t("tables.description")}</label>
                        <textarea
                          className="form-control"
                          rows={2}
                          value={formData.description}
                          onChange={(e) =>
                            setFormData({ ...formData, description: e.target.value })
                          }
                        />
                      </div>
                    </div>
                  </div>
                  <div className="modal-footer">
                    <button
                      type="button"
                      className="btn btn-secondary"
                      onClick={() => {
                        setShowEditModal(false);
                        setEditingAlarm(null);
                        setError(null);
                      }}
                      disabled={updating}
                    >
                      {t("common.cancel")}
                    </button>
                    <Button type="submit" variant="success" loading={updating}>
                      {t("alarms.updateAlarm")}
                    </Button>
                  </div>
                </form>
              </div>
            </div>
          </div>
        )}

        {/* Modal para confirmar eliminación de alarma */}
        {showDeleteModal && alarmToDelete && (
          <div
            className="modal fade show"
            style={{ display: "block", backgroundColor: "rgba(0,0,0,0.5)" }}
            tabIndex={-1}
            role="dialog"
          >
            <div className="modal-dialog" role="document">
              <div className="modal-content">
                <div className="modal-header">
                  <h5 className="modal-title">{t("alarms.confirmDelete")}</h5>
                  <button
                    type="button"
                    className="btn-close"
                    onClick={() => {
                      setShowDeleteModal(false);
                      setAlarmToDelete(null);
                      setError(null);
                    }}
                    aria-label="Close"
                    disabled={deleting}
                  ></button>
                </div>
                <div className="modal-body">
                  {error && (
                    <div className="alert alert-danger" role="alert">
                      {error}
                    </div>
                  )}
                  <p>
                    {t("alarms.confirmDeleteMessage", { name: alarmToDelete.name })}
                  </p>
                  <p className="text-muted small mb-0">
                    {t("alarms.cannotUndo")}
                  </p>
                </div>
                <div className="modal-footer">
                  <button
                    type="button"
                    className="btn btn-secondary"
                    onClick={() => {
                      setShowDeleteModal(false);
                      setAlarmToDelete(null);
                      setError(null);
                    }}
                    disabled={deleting}
                  >
                    {t("common.cancel")}
                  </button>
                  <Button
                    variant="danger"
                    onClick={confirmDeleteAlarm}
                    loading={deleting}
                  >
                    {t("common.delete")}
                  </Button>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* Modal para configurar Shelve */}
        {showShelveModal && alarmToShelve && (
          <div
            className="modal fade show"
            style={{ display: "block", backgroundColor: "rgba(0,0,0,0.5)" }}
            tabIndex={-1}
            role="dialog"
          >
            <div className="modal-dialog" role="document">
              <div className="modal-content">
                <div className="modal-header">
                  <h5 className="modal-title">{t("alarms.configureShelve", { alarmName: alarmToShelve })}</h5>
                  <button
                    type="button"
                    className="btn-close"
                    onClick={() => {
                      setShowShelveModal(false);
                      setAlarmToShelve(null);
                      setError(null);
                      setShelveDuration({
                        seconds: 0,
                        minutes: 0,
                        hours: 0,
                        days: 0,
                        weeks: 0,
                      });
                    }}
                    aria-label="Close"
                    disabled={shelving}
                  ></button>
                </div>
                <form onSubmit={handleShelveAlarm}>
                  <div className="modal-body">
                    {error && (
                      <div className="alert alert-danger" role="alert">
                        {error}
                      </div>
                    )}

                    <p className="text-muted mb-3">
                      {t("alarms.shelveDurationDescription")}
                    </p>

                    <div className="row g-3">
                      <div className="col-md-6">
                        <label className="form-label">{t("alarms.weeks")}</label>
                        <input
                          type="number"
                          className="form-control"
                          min="0"
                          value={shelveDuration.weeks}
                          onChange={(e) =>
                            setShelveDuration({ ...shelveDuration, weeks: parseInt(e.target.value) || 0 })
                          }
                          disabled={shelving}
                        />
                      </div>
                      <div className="col-md-6">
                        <label className="form-label">{t("alarms.days")}</label>
                        <input
                          type="number"
                          className="form-control"
                          min="0"
                          value={shelveDuration.days}
                          onChange={(e) =>
                            setShelveDuration({ ...shelveDuration, days: parseInt(e.target.value) || 0 })
                          }
                          disabled={shelving}
                        />
                      </div>
                      <div className="col-md-6">
                        <label className="form-label">{t("alarms.hours")}</label>
                        <input
                          type="number"
                          className="form-control"
                          min="0"
                          value={shelveDuration.hours}
                          onChange={(e) =>
                            setShelveDuration({ ...shelveDuration, hours: parseInt(e.target.value) || 0 })
                          }
                          disabled={shelving}
                        />
                      </div>
                      <div className="col-md-6">
                        <label className="form-label">{t("alarms.minutes")}</label>
                        <input
                          type="number"
                          className="form-control"
                          min="0"
                          value={shelveDuration.minutes}
                          onChange={(e) =>
                            setShelveDuration({ ...shelveDuration, minutes: parseInt(e.target.value) || 0 })
                          }
                          disabled={shelving}
                        />
                      </div>
                      <div className="col-md-6">
                        <label className="form-label">{t("alarms.seconds")}</label>
                        <input
                          type="number"
                          className="form-control"
                          min="0"
                          value={shelveDuration.seconds}
                          onChange={(e) =>
                            setShelveDuration({ ...shelveDuration, seconds: parseInt(e.target.value) || 0 })
                          }
                          disabled={shelving}
                        />
                      </div>
                    </div>
                  </div>
                  <div className="modal-footer">
                    <button
                      type="button"
                      className="btn btn-secondary"
                      onClick={() => {
                        setShowShelveModal(false);
                        setAlarmToShelve(null);
                        setError(null);
                        setShelveDuration({
                          seconds: 0,
                          minutes: 0,
                          hours: 0,
                          days: 0,
                          weeks: 0,
                        });
                      }}
                      disabled={shelving}
                    >
                      {t("common.cancel")}
                    </button>
                <Button type="submit" variant="secondary" loading={shelving}>
                      {t("alarms.applyShelve")}
                    </Button>
                  </div>
                </form>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
