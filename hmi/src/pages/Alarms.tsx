import { useEffect, useState, useMemo, memo } from "react";
import { Card } from "../components/Card";
import { Button } from "../components/Button";
import { getAlarms, createAlarm, updateAlarm, deleteAlarm, type Alarm, type AlarmsResponse } from "../services/alarms";
import { getTags, type Tag } from "../services/tags";
import { useTranslation } from "../hooks/useTranslation";
import { useAppSelector } from "../hooks/useAppSelector";
import { useAppDispatch } from "../hooks/useAppDispatch";
import { loadAllAlarms } from "../store/slices/alarmsSlice";

export function Alarms() {
  const { t } = useTranslation();
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
    getStateLabel
  }: {
    alarm: Alarm;
    realTimeAlarms: Record<string, Alarm>;
    tagValues: Record<string, Tag>;
    onEdit: (alarm: Alarm) => void;
    onDelete: (alarm: Alarm) => void;
    getStateBadgeClass: (state: any) => string;
    getStateLabel: (state: any) => string;
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
              title="Editar alarma"
            >
              <i className="bi bi-pencil"></i>
            </Button>
            <Button
              variant="danger"
              className="btn-sm"
              onClick={() => onDelete(currentAlarm)}
              title="Eliminar alarma"
            >
              <i className="bi bi-trash"></i>
            </Button>
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
    return (
      prevAlarmKey === nextAlarmKey &&
      prevAlarm.name === nextAlarm.name &&
      prevAlarm.tag === nextAlarm.tag &&
      prevAlarm.alarm_type === nextAlarm.alarm_type &&
      prevAlarm.trigger_value === nextAlarm.trigger_value &&
      prevAlarm.description === nextAlarm.description &&
      JSON.stringify(prevAlarm.state) === JSON.stringify(nextAlarm.state) &&
      prevTagValue === nextTagValue
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
      const errorMsg = e?.response?.data?.message || e?.message || "Error al cargar alarmas";
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
      setError("La alarma no tiene ID, no se puede editar");
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
      setError("La alarma no tiene ID, no se puede eliminar");
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
        setError("No hay alarmas para exportar");
        return;
      }

      // Preparar los datos para CSV
      const headers = [
        "Nombre",
        "Tag",
        "Tipo de Alarma",
        "Valor de Disparo",
        "Descripción",
        "Estado",
        "Mnemonic",
        "Timestamp",
        "Ack Timestamp"
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
      const errorMsg = e?.response?.data?.message || e?.message || "Error al exportar alarmas a CSV";
      setError(errorMsg);
    }
  };

  const confirmDeleteAlarm = async () => {
    if (!alarmToDelete || (!alarmToDelete.identifier && !alarmToDelete.id)) {
      setError("No hay alarma seleccionada para eliminar");
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
      const errorMsg = e?.response?.data?.message || e?.message || "Error al eliminar la alarma";
      setError(errorMsg);
    } finally {
      setDeleting(false);
    }
  };

  const handleUpdateAlarm = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!editingAlarm || (!editingAlarm.identifier && !editingAlarm.id)) {
      setError("No hay alarma seleccionada para actualizar");
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
        setError("No se han realizado cambios para actualizar");
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
      const errorMsg = e?.response?.data?.message || e?.message || "Error al actualizar la alarma";
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
        setError("Los campos Nombre y Tag son requeridos");
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
      const errorMsg = e?.response?.data?.message || e?.message || "Error al crear la alarma";
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
              <span>Alarmas</span>
              <div className="d-flex gap-2">
                <Button
                  variant="info"
                  className="btn-sm"
                  onClick={handleExportCSV}
                  disabled={loading || alarms.length === 0}
                >
                  <i className="bi bi-download me-1"></i>
                  Exportar CSV
                </Button>
                <Button
                  variant="success"
                  className="btn-sm"
                  onClick={() => setShowCreateModal(true)}
                >
                  <i className="bi bi-plus-circle me-1"></i>
                  Crear Alarma
                </Button>
              </div>
            </div>
          }
          footer={
            <div className="d-flex justify-content-between align-items-center">
              <div className="d-flex align-items-center gap-2">
                <label className="mb-0 small">Items por página:</label>
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
                  Página {pagination.page} de {pagination.pages} ({pagination.total} total)
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
                <span className="visually-hidden">Cargando...</span>
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
                    <th>Value</th>
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
                        No hay alarmas disponibles
                      </td>
                    </tr>
                  ) : (
                    alarms.map((alarm) => (
                      <AlarmTableRow
                        key={alarm.identifier || alarm.id || alarm.name}
                        alarm={alarm}
                        realTimeAlarms={realTimeAlarms}
                        tagValues={tagValues}
                        onEdit={handleEditAlarm}
                        onDelete={handleDeleteAlarm}
                        getStateBadgeClass={getStateBadgeClass}
                        getStateLabel={getStateLabel}
                      />
                    ))
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
                  <h5 className="modal-title">Crear Nueva Alarma</h5>
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
                          Nombre <span className="text-danger">*</span>
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
                          Tag <span className="text-danger">*</span>
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
                            {loadingTags ? "Cargando tags..." : "Seleccione un tag"}
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
                          Tipo de Alarma <span className="text-danger">*</span>
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
                          Valor de Disparo <span className="text-danger">*</span>
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
                            <option value="">Seleccione un valor</option>
                            <option value="true">True</option>
                            <option value="false">False</option>
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
                            placeholder="Ingrese el valor de disparo"
                          />
                        )}
                      </div>
                      <div className="col-12">
                        <label className="form-label">Descripción</label>
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
                      Cancelar
                    </button>
                    <Button type="submit" variant="success" loading={creating}>
                      Crear Alarma
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
                  <h5 className="modal-title">Editar Alarma: {editingAlarm.name}</h5>
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
                          Nombre <span className="text-danger">*</span>
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
                          Tag <span className="text-danger">*</span>
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
                          <option value="">Seleccione un tag</option>
                          {availableTags.map((tag) => (
                            <option key={tag.name} value={tag.name}>
                              {tag.name}
                            </option>
                          ))}
                        </select>
                      </div>
                      <div className="col-md-6">
                        <label className="form-label">
                          Tipo de Alarma <span className="text-danger">*</span>
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
                          Valor de Disparo <span className="text-danger">*</span>
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
                            <option value="">Seleccione un valor</option>
                            <option value="true">True</option>
                            <option value="false">False</option>
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
                            placeholder="Ingrese el valor de disparo"
                          />
                        )}
                      </div>
                      <div className="col-12">
                        <label className="form-label">Descripción</label>
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
                      Cancelar
                    </button>
                    <Button type="submit" variant="success" loading={updating}>
                      Actualizar Alarma
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
                  <h5 className="modal-title">Confirmar Eliminación</h5>
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
                    ¿Está seguro de que desea eliminar la alarma <strong>"{alarmToDelete.name}"</strong>?
                  </p>
                  <p className="text-muted small mb-0">
                    Esta acción no se puede deshacer.
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
                    Cancelar
                  </button>
                  <Button
                    variant="danger"
                    onClick={confirmDeleteAlarm}
                    loading={deleting}
                  >
                    Eliminar
                  </Button>
                </div>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
