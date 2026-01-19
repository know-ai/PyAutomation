import { useEffect, useState, useMemo, memo } from "react";
import { Card } from "../components/Card";
import { Button } from "../components/Button";
import { getTags, createTag, updateTag, deleteTag, getVariables, getUnitsByVariable, type Tag, type TagsResponse } from "../services/tags";
import { listClients, getClientVariablesWithOptions, getNodeAttributes, type OpcUaClient } from "../services/opcua";
import { useTranslation } from "../hooks/useTranslation";
import { useAppSelector } from "../hooks/useAppSelector";
import { showToast } from "../utils/toast";

// Memoized row component to prevent unnecessary re-renders
const TagTableRow = memo(({ 
  tag, 
  tagValues, 
  opcuaClientNamesByAddress,
  opcuaClientAddresses,
  opcuaNodeDisplayNames,
  onEdit,
  onDelete 
}: {
  tag: Tag;
  tagValues: Record<string, Tag>;
  opcuaClientNamesByAddress: Record<string, string>;
  opcuaClientAddresses: Record<string, string>;
  opcuaNodeDisplayNames: Record<string, string>;
  onEdit: (tag: Tag) => void;
  onDelete: (tag: Tag) => void;
}) => {
  const { t } = useTranslation();
  // Get real-time value from store if available, otherwise use tag.value
  const realTimeTag = tag.name ? tagValues[tag.name] : null;
  const value = realTimeTag?.value !== undefined && realTimeTag?.value !== null
    ? realTimeTag.value 
    : (tag.value !== undefined && tag.value !== null ? tag.value : null);
  
  const displayValue = value !== undefined && value !== null
    ? typeof value === "boolean"
      ? value ? "true" : "false"
      : String(value)
    : "-";

  return (
    <tr>
      <td>
        <strong
          title={tag.display_name || undefined}
          style={{ cursor: tag.display_name ? "help" : "default" }}
        >
          {tag.name || "-"}
        </strong>
      </td>
      <td>{tag.variable || "-"}</td>
      <td>{displayValue}</td>
      <td
        title={tag.unit || undefined}
        style={{ cursor: tag.unit ? "help" : "default" }}
      >
        {tag.display_unit || "-"}
      </td>
      <td>
        {(() => {
          // Priorizar opcua_client_name (más legible)
          if (tag.opcua_client_name) {
            return tag.opcua_client_name;
          }
          // Si tiene opcua_address pero no opcua_client_name, intentar obtener el nombre del cliente
          if (tag.opcua_address) {
            return opcuaClientNamesByAddress[tag.opcua_address] || tag.opcua_address;
          }
          return "-";
        })()}
      </td>
      <td>
        {tag.node_namespace
          ? opcuaNodeDisplayNames[tag.node_namespace] || tag.node_namespace
          : "-"}
      </td>
      <td>{tag.scan_time || "-"}</td>
      <td>{tag.dead_band !== undefined ? tag.dead_band : "-"}</td>
      <td>
        <div className="d-flex gap-2">
          <Button
            variant="secondary"
            className="btn-sm"
            onClick={() => onEdit(tag)}
            title={t("tags.editTag")}
          >
            <i className="bi bi-pencil"></i>
          </Button>
          <Button
            variant="danger"
            className="btn-sm"
            onClick={() => onDelete(tag)}
            title={t("tags.deleteTag")}
          >
            <i className="bi bi-trash"></i>
          </Button>
        </div>
      </td>
    </tr>
  );
}, (prevProps, nextProps) => {
  // Custom comparison function for memo
  // Only re-render if the tag data or real-time value changed
  const prevRealTimeTag = prevProps.tag.name ? prevProps.tagValues[prevProps.tag.name] : null;
  const nextRealTimeTag = nextProps.tag.name ? nextProps.tagValues[nextProps.tag.name] : null;
  
  const prevValue = prevRealTimeTag?.value ?? prevProps.tag.value;
  const nextValue = nextRealTimeTag?.value ?? nextProps.tag.value;
  
  // Re-render if:
  // - Tag ID or name changed
  // - Real-time value changed
  // - Tag properties changed
  return (
    prevProps.tag.id === nextProps.tag.id &&
    prevProps.tag.name === nextProps.tag.name &&
    prevValue === nextValue &&
    prevProps.tag.variable === nextProps.tag.variable &&
    prevProps.tag.unit === nextProps.tag.unit &&
    prevProps.tag.display_unit === nextProps.tag.display_unit &&
    prevProps.tag.opcua_address === nextProps.tag.opcua_address &&
    prevProps.tag.opcua_client_name === nextProps.tag.opcua_client_name &&
    prevProps.tag.node_namespace === nextProps.tag.node_namespace &&
    prevProps.tag.scan_time === nextProps.tag.scan_time &&
    prevProps.tag.dead_band === nextProps.tag.dead_band &&
    prevProps.opcuaClientAddresses === nextProps.opcuaClientAddresses
  );
});

TagTableRow.displayName = "TagTableRow";

export function Tags() {
  const { t } = useTranslation();
  const tagValues = useAppSelector((state) => state.tags.tagValues);
  const [tags, setTags] = useState<Tag[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [showEditModal, setShowEditModal] = useState(false);
  const [showDeleteModal, setShowDeleteModal] = useState(false);
  const [editingTag, setEditingTag] = useState<Tag | null>(null);
  const [tagToDelete, setTagToDelete] = useState<Tag | null>(null);
  const [creating, setCreating] = useState(false);
  const [updating, setUpdating] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [variables, setVariables] = useState<string[]>([]);
  const [availableUnits, setAvailableUnits] = useState<string[]>([]);
  const [loadingVariables, setLoadingVariables] = useState(false);
  const [loadingUnits, setLoadingUnits] = useState(false);
  const [opcuaClients, setOpcuaClients] = useState<OpcUaClient[]>([]);
  const [opcuaClientAddresses, setOpcuaClientAddresses] = useState<Record<string, string>>({});
  const [opcuaClientNamesByAddress, setOpcuaClientNamesByAddress] = useState<Record<string, string>>({});
  const [opcuaNodes, setOpcuaNodes] = useState<Array<{ namespace: string; displayName: string }>>([]);
  const [opcuaNodesByClient, setOpcuaNodesByClient] = useState<Record<string, Array<{ namespace: string; displayName: string }>>>({});
  const [opcuaNodeFilter, setOpcuaNodeFilter] = useState<string>("");
  const [opcuaNodeDisplayNames, setOpcuaNodeDisplayNames] = useState<Record<string, string>>({});
  const [loadingClients, setLoadingClients] = useState(false);
  const [loadingNodes, setLoadingNodes] = useState(false);
  const [pagination, setPagination] = useState({
    page: 1,
    limit: 20,
    total: 0,
    pages: 0,
  });
  
  // Filtros por columna
  const [columnFilters, setColumnFilters] = useState({
    name: "",
    variable: "",
    value: "",
    displayUnit: "",
    opcuaClientName: "",
    nodeNamespace: "",
    scanTime: "",
    deadBand: "",
  });
  
  // Form state
  const [formData, setFormData] = useState({
    name: "",
    unit: "",
    variable: "",
    display_unit: "",
    data_type: "float",
    description: "",
    display_name: "",
    opcua_address: "",
    node_namespace: "",
    scan_time: "",
    dead_band: "",
    process_filter: false,
    gaussian_filter: false,
    gaussian_filter_threshold: "1.0",
    gaussian_filter_r_value: "0.0",
    outlier_detection: false,
    out_of_range_detection: false,
    frozen_data_detection: false,
    segment: "",
    manufacturer: "",
  });

  const loadTags = async (page: number = pagination.page, limit: number = pagination.limit) => {
    setLoading(true);
    setError(null);
    try {
      const response: TagsResponse = await getTags(page, limit);
      const loadedTags = response.data || [];
      setTags(loadedTags);
      setPagination(response.pagination || {
        page: page,
        limit: limit,
        total: 0,
        pages: 0,
      });
      
      // Cargar display names de los nodos OPC UA que están en los tags
      // Recopilar namespaces únicos y sus clientes asociados
      const namespaceToClientName: Record<string, string> = {};
      loadedTags.forEach((tag) => {
        if (tag.node_namespace) {
          // Priorizar opcua_client_name sobre opcua_address
          if (tag.opcua_client_name) {
            namespaceToClientName[tag.node_namespace] = tag.opcua_client_name;
          } else if (tag.opcua_address) {
            const clientName = opcuaClientNamesByAddress[tag.opcua_address];
            if (clientName) {
              namespaceToClientName[tag.node_namespace] = clientName;
            }
          }
        }
      });
      
      // Cargar árboles de clientes únicos para obtener display names
      const uniqueClientNames = new Set<string>();
      Object.values(namespaceToClientName).forEach((clientName) => {
        if (clientName) {
          uniqueClientNames.add(clientName);
        }
      });
      
      // Cargar nodos de todos los clientes únicos
      const displayNamesMap: Record<string, string> = {};
      for (const clientName of uniqueClientNames) {
        try {
          // Mucho más rápido que browse: leer atributos SOLO de los namespaces usados.
          const namespaces = Object.entries(namespaceToClientName)
            .filter(([_ns, c]) => c === clientName)
            .map(([ns]) => ns);
          if (namespaces.length === 0) continue;

          const attrs = await getNodeAttributes(clientName, namespaces);
          attrs.forEach((a: any) => {
            const ns = a?.Namespace ?? a?.namespace;
            const dn = a?.DisplayName ?? a?.displayName ?? a?.display_name;
            if (ns && dn) displayNamesMap[String(ns)] = String(dn);
          });
        } catch (e) {
          console.error(`Error loading node attributes for client ${clientName}:`, e);
        }
      }
      setOpcuaNodeDisplayNames((prev) => ({ ...prev, ...displayNamesMap }));
    } catch (e: any) {
      const data = e?.response?.data;
      const backendMessage =
        (typeof data === "string" ? data : undefined) ??
        data?.message ??
        data?.detail ??
        data?.error;
      const errorMsg = backendMessage || e?.message || t("tags.loadError");
      setError(errorMsg);
      setTags([]);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadTags(1, 20);
    // Cargar clientes OPC UA al montar para tener los nombres disponibles en la tabla
    loadOpcuaClients();
  }, []);

  // Cargar variables y clientes OPC UA disponibles cuando se abre el modal
  useEffect(() => {
    if (showCreateModal || showEditModal) {
      if (variables.length === 0) {
        loadVariables();
      }
      if (opcuaClients.length === 0) {
        loadOpcuaClients();
      }
    }
  }, [showCreateModal, showEditModal]);

  // Cargar unidades cuando cambia la variable seleccionada
  useEffect(() => {
    if (formData.variable && (showCreateModal || showEditModal)) {
      loadUnits(formData.variable);
    } else {
      if (!(showCreateModal || showEditModal)) {
        setAvailableUnits([]);
        // Limpiar unidades si no hay variable seleccionada
        if (!formData.variable) {
          setFormData((prev) => ({ ...prev, unit: "", display_unit: "" }));
        }
      }
    }
  }, [formData.variable, showCreateModal, showEditModal]);

  // Cargar nodos OPC UA cuando cambia el cliente seleccionado
  useEffect(() => {
    if (formData.opcua_address && (showCreateModal || showEditModal)) {
      // Buscar el nombre del cliente por su dirección
      const clientName = Object.keys(opcuaClientAddresses).find(
        (name) => opcuaClientAddresses[name] === formData.opcua_address
      );
      if (clientName) {
        loadOpcuaNodes(clientName);
      } else {
        setOpcuaNodes([]);
        if (!showEditModal) {
          setFormData((prev) => ({ ...prev, node_namespace: "" }));
        }
      }
    } else {
      if (!(showCreateModal || showEditModal)) {
        setOpcuaNodes([]);
        if (!formData.opcua_address) {
          setFormData((prev) => ({ ...prev, node_namespace: "" }));
        }
      }
    }
  }, [formData.opcua_address, showCreateModal, showEditModal]);

  const loadVariables = async () => {
    setLoadingVariables(true);
    try {
      const vars = await getVariables();
      setVariables(vars);
    } catch (e: any) {
      console.error("Error loading variables:", e);
      setVariables([]);
    } finally {
      setLoadingVariables(false);
    }
  };

  const loadUnits = async (variableName: string) => {
    if (!variableName) {
      setAvailableUnits([]);
      return;
    }
    setLoadingUnits(true);
    try {
      const units = await getUnitsByVariable(variableName);
      setAvailableUnits(units);
      // Si la unidad actual no está en las disponibles, limpiarla
      if (formData.unit && !units.includes(formData.unit)) {
        setFormData((prev) => ({ ...prev, unit: "" }));
      }
      if (formData.display_unit && !units.includes(formData.display_unit)) {
        setFormData((prev) => ({ ...prev, display_unit: "" }));
      }
    } catch (e: any) {
      console.error("Error loading units:", e);
      setAvailableUnits([]);
    } finally {
      setLoadingUnits(false);
    }
  };

  const loadOpcuaClients = async () => {
    setLoadingClients(true);
    try {
      const clients = await listClients();
      setOpcuaClients(clients);
      // Crear un mapa de nombre de cliente -> dirección
      const addresses: Record<string, string> = {};
      // Crear un mapa inverso de dirección -> nombre de cliente
      const namesByAddress: Record<string, string> = {};
      clients.forEach((client) => {
        const clientName = typeof client === "string" ? client : client.name || "";
        const address = typeof client === "object" && client.server_url ? client.server_url : "";
        if (clientName && address) {
          addresses[clientName] = address;
          namesByAddress[address] = clientName;
        }
      });
      setOpcuaClientAddresses(addresses);
      setOpcuaClientNamesByAddress(namesByAddress);
    } catch (e: any) {
      console.error("Error loading OPC UA clients:", e);
      setOpcuaClients([]);
      setOpcuaClientAddresses({});
      setOpcuaClientNamesByAddress({});
    } finally {
      setLoadingClients(false);
    }
  };

  const loadOpcuaNodes = async (clientName: string) => {
    if (!clientName) {
      setOpcuaNodes([]);
      return;
    }
    setLoadingNodes(true);
    try {
      // Cache local por cliente para no reconsultar cada vez que abres el modal.
      const cached = opcuaNodesByClient[clientName];
      const nodes = cached
        ? cached
        : await getClientVariablesWithOptions(clientName, {
            mode: "generic",
            max_depth: 25,
            max_nodes: 50_000,
            timeout_ms: 60_000,
            fallback_to_legacy: true,
          });
      if (!cached) {
        setOpcuaNodesByClient((prev) => ({ ...prev, [clientName]: nodes }));
      }
      setOpcuaNodes(nodes);
      setOpcuaNodeFilter(""); // reset filtro al cambiar cliente
      // Crear un mapa de namespace -> displayName para búsqueda rápida
      const displayNamesMap: Record<string, string> = {};
      nodes.forEach((node) => {
        if (node.namespace && node.displayName) {
          displayNamesMap[node.namespace] = node.displayName;
        }
      });
      setOpcuaNodeDisplayNames((prev) => ({ ...prev, ...displayNamesMap }));
      // Si el namespace actual no está en los disponibles, limpiarlo
      if (formData.node_namespace && !nodes.some((n) => n.namespace === formData.node_namespace)) {
        // En vez de borrar inmediatamente, intentamos resolver displayName del enlazado (por si quedó fuera del max_nodes)
        try {
          const attrs = await getNodeAttributes(clientName, [formData.node_namespace]);
          const a: any = attrs?.[0];
          const dn = a?.DisplayName ?? a?.displayName ?? a?.display_name;
          if (dn) {
            const single = { namespace: formData.node_namespace, displayName: String(dn) };
            setOpcuaNodes((prev) => (prev.some((p) => p.namespace === single.namespace) ? prev : [single, ...prev]));
            setOpcuaNodeDisplayNames((prev) => ({ ...prev, [single.namespace]: single.displayName }));
          } else {
            setFormData((prev) => ({ ...prev, node_namespace: "" }));
          }
        } catch {
          setFormData((prev) => ({ ...prev, node_namespace: "" }));
        }
      }
    } catch (e: any) {
      console.error("Error loading OPC UA nodes:", e);
      setOpcuaNodes([]);
    } finally {
      setLoadingNodes(false);
    }
  };

  const filteredOpcuaNodes = useMemo(() => {
    if (!opcuaNodeFilter.trim()) return opcuaNodes.slice(0, 5000);
    const q = opcuaNodeFilter.trim().toLowerCase();
    return opcuaNodes
      .filter((n) => (n.displayName || "").toLowerCase().includes(q) || (n.namespace || "").toLowerCase().includes(q))
      .slice(0, 5000);
  }, [opcuaNodes, opcuaNodeFilter]);

  const handlePageChange = (newPage: number) => {
    if (newPage >= 1 && newPage <= pagination.pages) {
      loadTags(newPage, pagination.limit);
    }
  };

  const handleLimitChange = (newLimit: number) => {
    if (newLimit > 0) {
      loadTags(1, newLimit);
    }
  };

  const handleEditTag = (tag: Tag) => {
    if (!tag.id) {
      setError(t("tags.noIdToEdit"));
      return;
    }
    
    // Cargar datos del tag en el formulario
    setFormData({
      name: tag.name || "",
      unit: tag.unit || "",
      variable: tag.variable || "",
      display_unit: tag.display_unit || "",
      data_type: tag.data_type || "float",
      description: tag.description || "",
      display_name: tag.display_name || "",
      opcua_address: tag.opcua_client_name 
        ? opcuaClientAddresses[tag.opcua_client_name] || ""
        : tag.opcua_address || "",
      node_namespace: tag.node_namespace || "",
      scan_time: tag.scan_time ? String(tag.scan_time) : "",
      dead_band: tag.dead_band !== undefined ? String(tag.dead_band) : "",
      process_filter: tag.process_filter || false,
      gaussian_filter: tag.gaussian_filter || false,
      gaussian_filter_threshold: tag.gaussian_filter_threshold !== undefined ? String(tag.gaussian_filter_threshold) : "1.0",
      gaussian_filter_r_value: tag.gaussian_filter_r_value !== undefined ? String(tag.gaussian_filter_r_value) : "0.0",
      outlier_detection: tag.outlier_detection || false,
      out_of_range_detection: tag.out_of_range_detection || false,
      frozen_data_detection: tag.frozen_data_detection || false,
      segment: tag.segment || "",
      manufacturer: tag.manufacturer || "",
    });
    
    setEditingTag(tag);
    setShowEditModal(true);
    setError(null);
    
    // Cargar unidades si hay variable
    if (tag.variable) {
      loadUnits(tag.variable);
    }
    
    // Cargar nodos si hay cliente OPC UA
    // Priorizar opcua_client_name sobre opcua_address
    if (tag.opcua_client_name) {
      loadOpcuaNodes(tag.opcua_client_name);
    } else if (tag.opcua_address) {
      const clientName = opcuaClientNamesByAddress[tag.opcua_address];
      if (clientName) {
        loadOpcuaNodes(clientName);
      }
    }
  };

  const handleDeleteTag = (tag: Tag) => {
    if (!tag.name) {
      setError(t("tags.noNameToDelete"));
      return;
    }
    
    setTagToDelete(tag);
    setShowDeleteModal(true);
    setError(null);
  };

  const handleExportCSV = async () => {
    try {
      setError(null);
      // Obtener todos los tags (sin paginación) usando el servicio
      // Necesitamos obtener todos los tags, así que usamos un límite grande
      const response = await getTags(1, 10000);
      const allTags = response.data || [];
      
      if (!allTags || allTags.length === 0) {
        setError(t("tags.noTagsToExport"));
        return;
      }

      // Preparar los datos para CSV
      const headers = [
        t("tables.name"),
        t("tables.displayName"),
        t("tables.variable"),
        t("tags.unit"),
        t("tables.displayUnit"),
        t("tables.dataType"),
        t("tables.opcuaAddress"),
        t("tables.nodeNamespace"),
        t("tables.scanTime"),
        t("tables.deadBand"),
        t("tags.processFilter"),
        t("tags.gaussianFilter"),
        t("tags.gaussianFilterThreshold"),
        t("tags.gaussianFilterRValue"),
        t("tags.outlierDetection"),
        t("tags.outOfRangeDetection"),
        t("tags.frozenDataDetection"),
        t("tags.segment"),
        t("tags.manufacturer"),
        t("tables.description")
      ];

      // Convertir tags a filas CSV
      const rows = allTags.map((tag: Tag) => {
        return [
          tag.name || "",
          tag.display_name || "",
          tag.variable || "",
          tag.unit || "",
          tag.display_unit || "",
          tag.data_type || "",
          (() => {
            // Si tiene opcua_client_name, usar ese para buscar la dirección
            if (tag.opcua_client_name) {
              const address = opcuaClientAddresses[tag.opcua_client_name];
              return address || tag.opcua_client_name;
            }
            // Si tiene opcua_address, usar ese (compatibilidad hacia atrás)
            if (tag.opcua_address) {
              return opcuaClientNamesByAddress[tag.opcua_address] || tag.opcua_address;
            }
            return "";
          })(),
          tag.node_namespace ? (opcuaNodeDisplayNames[tag.node_namespace] || tag.node_namespace) : "",
          tag.scan_time || "",
          tag.dead_band !== undefined ? tag.dead_band : "",
          tag.process_filter ? t("common.yes") : t("common.no"),
          tag.gaussian_filter ? t("common.yes") : t("common.no"),
          tag.gaussian_filter_threshold !== undefined ? tag.gaussian_filter_threshold : "",
          tag.gaussian_filter_r_value !== undefined ? tag.gaussian_filter_r_value : "",
          tag.outlier_detection ? t("common.yes") : t("common.no"),
          tag.out_of_range_detection ? t("common.yes") : t("common.no"),
          tag.frozen_data_detection ? t("common.yes") : t("common.no"),
          tag.segment || "",
          tag.manufacturer || "",
          tag.description || ""
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
      link.setAttribute("download", `tags_${new Date().toISOString().split("T")[0]}.csv`);
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
      const errorMsg = backendMessage || e?.message || t("tags.exportError");
      setError(errorMsg);
    }
  };

  const confirmDeleteTag = async () => {
    if (!tagToDelete || !tagToDelete.name) {
      setError(t("tags.noTagSelectedToDelete"));
      return;
    }

    setDeleting(true);
    setError(null);

    try {
      await deleteTag(tagToDelete.name);
      
      // Cerrar modal y limpiar
      setShowDeleteModal(false);
      setTagToDelete(null);
      
      // Recargar tags
      loadTags(pagination.page, pagination.limit);
    } catch (e: any) {
      const data = e?.response?.data;
      const backendMessage =
        (typeof data === "string" ? data : undefined) ??
        data?.message ??
        data?.detail ??
        data?.error;
      const errorMsg = backendMessage || e?.message || t("tags.deleteError");
      setError(errorMsg);
    } finally {
      setDeleting(false);
    }
  };

  const handleUpdateTag = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!editingTag || !editingTag.id) {
      setError(t("tags.noTagSelectedToUpdate"));
      return;
    }
    
    setUpdating(true);
    setError(null);
    
    try {
      // Preparar payload solo con campos que han cambiado
      const payload: any = {
        id: editingTag.id,
      };

      // Comparar valores originales con los nuevos y solo agregar los que cambiaron
      const original = editingTag;
      
      // Comparar name
      if (formData.name !== (original.name || "")) {
        payload.name = formData.name;
      }
      
      // Comparar unit
      if (formData.unit !== (original.unit || "")) {
        payload.unit = formData.unit;
      }
      
      // Comparar variable
      if (formData.variable !== (original.variable || "")) {
        payload.variable = formData.variable;
      }
      
      // Comparar display_unit
      if (formData.display_unit !== (original.display_unit || "")) {
        payload.display_unit = formData.display_unit;
      }
      
      // Comparar data_type
      if (formData.data_type !== (original.data_type || "float")) {
        payload.data_type = formData.data_type;
      }
      
      // Comparar description
      if (formData.description !== (original.description || "")) {
        payload.description = formData.description;
      }
      
      // Comparar display_name
      if (formData.display_name !== (original.display_name || "")) {
        payload.display_name = formData.display_name;
      }
      
      // Comparar opcua_address
      if (formData.opcua_address !== (original.opcua_address || "")) {
        payload.opcua_address = formData.opcua_address;
      }
      
      // Comparar node_namespace
      if (formData.node_namespace !== (original.node_namespace || "")) {
        payload.node_namespace = formData.node_namespace;
      }
      
      // Comparar scan_time
      const originalScanTime = original.scan_time ? String(original.scan_time) : "";
      if (formData.scan_time !== originalScanTime) {
        if (formData.scan_time) {
          payload.scan_time = parseInt(formData.scan_time);
        } else {
          payload.scan_time = null;
        }
      }
      
      // Comparar dead_band
      const originalDeadBand = original.dead_band !== undefined ? String(original.dead_band) : "";
      if (formData.dead_band !== originalDeadBand) {
        if (formData.dead_band) {
          payload.dead_band = parseFloat(formData.dead_band);
        } else {
          payload.dead_band = null;
        }
      }
      
      // Comparar segment
      if (formData.segment !== (original.segment || "")) {
        payload.segment = formData.segment;
      }
      
      // Comparar manufacturer
      if (formData.manufacturer !== (original.manufacturer || "")) {
        payload.manufacturer = formData.manufacturer;
      }

      // Comparar booleanos
      if (formData.process_filter !== (original.process_filter || false)) {
        payload.process_filter = formData.process_filter;
      }
      
      if (formData.gaussian_filter !== (original.gaussian_filter || false)) {
        payload.gaussian_filter = formData.gaussian_filter;
      }
      
      if (formData.outlier_detection !== (original.outlier_detection || false)) {
        payload.outlier_detection = formData.outlier_detection;
      }
      
      if (formData.out_of_range_detection !== (original.out_of_range_detection || false)) {
        payload.out_of_range_detection = formData.out_of_range_detection;
      }
      
      if (formData.frozen_data_detection !== (original.frozen_data_detection || false)) {
        payload.frozen_data_detection = formData.frozen_data_detection;
      }

      // Comparar valores de filtro gaussiano
      const originalGaussianThreshold = original.gaussian_filter_threshold !== undefined ? String(original.gaussian_filter_threshold) : "1.0";
      if (formData.gaussian_filter_threshold !== originalGaussianThreshold) {
        if (formData.gaussian_filter_threshold) {
          payload.gaussian_filter_threshold = parseFloat(formData.gaussian_filter_threshold);
        }
      }
      
      const originalGaussianRValue = original.gaussian_filter_r_value !== undefined ? String(original.gaussian_filter_r_value) : "0.0";
      if (formData.gaussian_filter_r_value !== originalGaussianRValue) {
        if (formData.gaussian_filter_r_value) {
          payload.gaussian_filter_r_value = parseFloat(formData.gaussian_filter_r_value);
        }
      }

      // Si no hay campos para actualizar, mostrar error
      const fieldsToUpdate = Object.keys(payload).filter(key => key !== 'id');
      if (fieldsToUpdate.length === 0) {
        showToast(t("tags.noChangesToUpdate"), "error");
        setUpdating(false);
        return;
      }

      await updateTag(payload);
      
      // Mostrar toast de éxito
      showToast(t("tags.updateSuccess"), "success");
      
      // Cerrar modal y resetear formulario
      setShowEditModal(false);
      setEditingTag(null);
      setFormData({
        name: "",
        unit: "",
        variable: "",
        display_unit: "",
        data_type: "float",
        description: "",
        display_name: "",
        opcua_address: "",
        node_namespace: "",
        scan_time: "",
        dead_band: "",
        process_filter: false,
        gaussian_filter: false,
        gaussian_filter_threshold: "1.0",
        gaussian_filter_r_value: "0.0",
        outlier_detection: false,
        out_of_range_detection: false,
        frozen_data_detection: false,
        segment: "",
        manufacturer: "",
      });
      setAvailableUnits([]);
      setOpcuaNodes([]);
      
      // Recargar tags
      loadTags(pagination.page, pagination.limit);
    } catch (e: any) {
      const data = e?.response?.data;
      const backendMessage =
        (typeof data === "string" ? data : undefined) ??
        data?.message ??
        data?.detail ??
        data?.error;
      const errorMsg = backendMessage || e?.message || t("tags.updateError");
      showToast(errorMsg, "error");
    } finally {
      setUpdating(false);
    }
  };

  const handleCreateTag = async (e: React.FormEvent) => {
    e.preventDefault();
    setCreating(true);
    setError(null);
    
    try {
      // Validar campos requeridos
      if (!formData.name || !formData.unit || !formData.variable) {
        setError(t("tags.nameUnitVariableRequired"));
        setCreating(false);
        return;
      }

      // Preparar payload
      const payload: any = {
        name: formData.name,
        unit: formData.unit,
        variable: formData.variable,
      };

      // Agregar campos opcionales solo si tienen valor
      if (formData.display_unit) payload.display_unit = formData.display_unit;
      if (formData.data_type) payload.data_type = formData.data_type;
      if (formData.description) payload.description = formData.description;
      if (formData.display_name) payload.display_name = formData.display_name;
      if (formData.opcua_address) payload.opcua_address = formData.opcua_address;
      if (formData.node_namespace) payload.node_namespace = formData.node_namespace;
      if (formData.scan_time) payload.scan_time = parseInt(formData.scan_time);
      if (formData.dead_band) payload.dead_band = parseFloat(formData.dead_band);
      if (formData.segment) payload.segment = formData.segment;
      if (formData.manufacturer) payload.manufacturer = formData.manufacturer;

      // Booleanos
      payload.process_filter = formData.process_filter;
      payload.gaussian_filter = formData.gaussian_filter;
      payload.outlier_detection = formData.outlier_detection;
      payload.out_of_range_detection = formData.out_of_range_detection;
      payload.frozen_data_detection = formData.frozen_data_detection;

      // Valores de filtro gaussiano
      if (formData.gaussian_filter_threshold) {
        payload.gaussian_filter_threshold = parseFloat(formData.gaussian_filter_threshold);
      }
      if (formData.gaussian_filter_r_value) {
        payload.gaussian_filter_r_value = parseFloat(formData.gaussian_filter_r_value);
      }

      await createTag(payload);
      
      // Cerrar modal y resetear formulario
      setShowCreateModal(false);
      setFormData({
        name: "",
        unit: "",
        variable: "",
        display_unit: "",
        data_type: "float",
        description: "",
        display_name: "",
        opcua_address: "",
        node_namespace: "",
        scan_time: "",
        dead_band: "",
        process_filter: false,
        gaussian_filter: false,
        gaussian_filter_threshold: "1.0",
        gaussian_filter_r_value: "0.0",
        outlier_detection: false,
        out_of_range_detection: false,
        frozen_data_detection: false,
        segment: "",
        manufacturer: "",
      });
      setAvailableUnits([]);
      setOpcuaNodes([]);
      
      // Recargar tags
      loadTags(pagination.page, pagination.limit);
    } catch (e: any) {
      const data = e?.response?.data;
      const backendMessage =
        (typeof data === "string" ? data : undefined) ??
        data?.message ??
        data?.detail ??
        data?.error;
      const errorMsg = backendMessage || e?.message || t("tags.createError");
      setError(errorMsg);
    } finally {
      setCreating(false);
    }
  };

  return (
    <div className="row">
      <div className="col-12">
        <Card
          title={
            <div className="d-flex justify-content-between align-items-center w-100">
              <span>{t("navigation.tags")}</span>
              <div className="d-flex gap-2">
                <Button
                  variant="secondary"
                  className="btn-sm"
                  onClick={handleExportCSV}
                  disabled={loading || tags.length === 0}
                >
                  <i className="bi bi-download me-1"></i>
                  {t("tags.exportCSV")}
                </Button>
                <Button
                  variant="success"
                  className="btn-sm"
                  onClick={() => setShowCreateModal(true)}
                >
                  <i className="bi bi-plus-circle me-1"></i>
                  {t("tags.createTag")}
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
                  {/* Fila de filtros */}
                  <tr>
                    <th>
                      <input
                        type="text"
                        className="form-control form-control-sm"
                        placeholder={t("common.filter")}
                        value={columnFilters.name}
                        onChange={(e) =>
                          setColumnFilters((prev) => ({ ...prev, name: e.target.value }))
                        }
                      />
                    </th>
                    <th>
                      <input
                        type="text"
                        className="form-control form-control-sm"
                        placeholder={t("common.filter")}
                        value={columnFilters.variable}
                        onChange={(e) =>
                          setColumnFilters((prev) => ({ ...prev, variable: e.target.value }))
                        }
                      />
                    </th>
                    <th>
                      <input
                        type="text"
                        className="form-control form-control-sm"
                        placeholder={t("common.filter")}
                        value={columnFilters.value}
                        onChange={(e) =>
                          setColumnFilters((prev) => ({ ...prev, value: e.target.value }))
                        }
                      />
                    </th>
                    <th>
                      <input
                        type="text"
                        className="form-control form-control-sm"
                        placeholder={t("common.filter")}
                        value={columnFilters.displayUnit}
                        onChange={(e) =>
                          setColumnFilters((prev) => ({ ...prev, displayUnit: e.target.value }))
                        }
                      />
                    </th>
                    <th>
                      <input
                        type="text"
                        className="form-control form-control-sm"
                        placeholder={t("common.filter")}
                        value={columnFilters.opcuaClientName}
                        onChange={(e) =>
                          setColumnFilters((prev) => ({ ...prev, opcuaClientName: e.target.value }))
                        }
                      />
                    </th>
                    <th>
                      <input
                        type="text"
                        className="form-control form-control-sm"
                        placeholder={t("common.filter")}
                        value={columnFilters.nodeNamespace}
                        onChange={(e) =>
                          setColumnFilters((prev) => ({ ...prev, nodeNamespace: e.target.value }))
                        }
                      />
                    </th>
                    <th>
                      <input
                        type="text"
                        className="form-control form-control-sm"
                        placeholder={t("common.filter")}
                        value={columnFilters.scanTime}
                        onChange={(e) =>
                          setColumnFilters((prev) => ({ ...prev, scanTime: e.target.value }))
                        }
                      />
                    </th>
                    <th>
                      <input
                        type="text"
                        className="form-control form-control-sm"
                        placeholder={t("common.filter")}
                        value={columnFilters.deadBand}
                        onChange={(e) =>
                          setColumnFilters((prev) => ({ ...prev, deadBand: e.target.value }))
                        }
                      />
                    </th>
                    <th></th>
                  </tr>
                  {/* Fila de headers */}
                  <tr>
                    <th>{t("tables.name")}</th>
                    <th>{t("tables.variable")}</th>
                    <th>{t("tables.value")}</th>
                    <th>{t("tables.displayUnit")}</th>
                    <th>{t("tables.opcuaClientName")}</th>
                    <th>{t("tables.nodeNamespace")}</th>
                    <th>{t("tables.scanTime")}</th>
                    <th>{t("tables.deadBand")}</th>
                    <th>{t("tables.actions")}</th>
                  </tr>
                </thead>
                <tbody>
                  {(() => {
                    // Filtrar tags basándose en los filtros de columna
                    const filteredTags = tags.filter((tag) => {
                      // Obtener valor real-time si está disponible
                      const realTimeTag = tag.name ? tagValues[tag.name] : null;
                      const value = realTimeTag?.value !== undefined && realTimeTag?.value !== null
                        ? realTimeTag.value 
                        : (tag.value !== undefined && tag.value !== null ? tag.value : null);
                      
                      const displayValue = value !== undefined && value !== null
                        ? typeof value === "boolean"
                          ? value ? "true" : "false"
                          : String(value)
                        : "-";

                      // Obtener OPC UA client name
                      const opcuaClientName = (() => {
                        if (tag.opcua_client_name) {
                          return tag.opcua_client_name;
                        }
                        if (tag.opcua_address) {
                          return opcuaClientNamesByAddress[tag.opcua_address] || tag.opcua_address;
                        }
                        return "-";
                      })();

                      // Obtener node namespace display name
                      const nodeNamespaceDisplay = tag.node_namespace
                        ? opcuaNodeDisplayNames[tag.node_namespace] || tag.node_namespace
                        : "-";

                      // Aplicar filtros (case-insensitive)
                      const matchesName = !columnFilters.name || 
                        (tag.name || "").toLowerCase().includes(columnFilters.name.toLowerCase());
                      const matchesVariable = !columnFilters.variable || 
                        (tag.variable || "").toLowerCase().includes(columnFilters.variable.toLowerCase());
                      const matchesValue = !columnFilters.value || 
                        displayValue.toLowerCase().includes(columnFilters.value.toLowerCase());
                      const matchesDisplayUnit = !columnFilters.displayUnit || 
                        (tag.display_unit || "-").toLowerCase().includes(columnFilters.displayUnit.toLowerCase());
                      const matchesOpcuaClientName = !columnFilters.opcuaClientName || 
                        opcuaClientName.toLowerCase().includes(columnFilters.opcuaClientName.toLowerCase());
                      const matchesNodeNamespace = !columnFilters.nodeNamespace || 
                        nodeNamespaceDisplay.toLowerCase().includes(columnFilters.nodeNamespace.toLowerCase());
                      const matchesScanTime = !columnFilters.scanTime || 
                        String(tag.scan_time || "-").toLowerCase().includes(columnFilters.scanTime.toLowerCase());
                      const matchesDeadBand = !columnFilters.deadBand || 
                        String(tag.dead_band !== undefined ? tag.dead_band : "-").toLowerCase().includes(columnFilters.deadBand.toLowerCase());

                      return matchesName && matchesVariable && matchesValue && matchesDisplayUnit && 
                             matchesOpcuaClientName && matchesNodeNamespace && matchesScanTime && matchesDeadBand;
                    });

                    if (filteredTags.length === 0) {
                      return (
                        <tr>
                          <td colSpan={9} className="text-center text-muted py-4">
                            {t("tags.noTagsAvailable")}
                          </td>
                        </tr>
                      );
                    }

                    return filteredTags.map((tag) => (
                      <TagTableRow
                        key={tag.id || tag.name}
                        tag={tag}
                        tagValues={tagValues}
                        opcuaClientNamesByAddress={opcuaClientNamesByAddress}
                        opcuaClientAddresses={opcuaClientAddresses}
                        opcuaNodeDisplayNames={opcuaNodeDisplayNames}
                        onEdit={handleEditTag}
                        onDelete={handleDeleteTag}
                      />
                    ));
                  })()}
                </tbody>
              </table>
            </div>
          )}
        </Card>

        {/* Modal para crear tag */}
        {showCreateModal && (
          <div
            className="modal fade show"
            style={{ display: "block", backgroundColor: "rgba(0,0,0,0.5)" }}
            tabIndex={-1}
            role="dialog"
          >
            <div className="modal-dialog modal-lg modal-dialog-scrollable" role="document" style={{ maxHeight: "90vh" }}>
              <div className="modal-content" style={{ maxHeight: "90vh", display: "flex", flexDirection: "column" }}>
                <div className="modal-header" style={{ flexShrink: 0 }}>
                  <h5 className="modal-title">{t("tags.createNewTag")}</h5>
                  <button
                    type="button"
                    className="btn-close"
                    onClick={() => {
                      setShowCreateModal(false);
                      setError(null);
                      setAvailableUnits([]);
                      setOpcuaNodes([]);
                    }}
                    aria-label="Close"
                  ></button>
                </div>
                <form onSubmit={handleCreateTag} style={{ display: "flex", flexDirection: "column", flex: 1, minHeight: 0 }}>
                  <div className="modal-body" style={{ overflowY: "auto", flex: 1, minHeight: 0 }}>
                    {error && (
                      <div className="alert alert-danger" role="alert">
                        {error}
                      </div>
                    )}

                    <div className="row g-3">
                      {/* Campos requeridos */}
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
                          {t("tables.variable")} <span className="text-danger">*</span>
                        </label>
                        <select
                          className="form-select"
                          required
                          value={formData.variable}
                          onChange={(e) =>
                            setFormData({ ...formData, variable: e.target.value, unit: "", display_unit: "" })
                          }
                          disabled={loadingVariables}
                        >
                          <option value="">{t("tags.selectVariable")}</option>
                          {variables.map((v) => (
                            <option key={v} value={v}>
                              {v}
                            </option>
                          ))}
                        </select>
                        {loadingVariables && (
                          <small className="text-muted">{t("tags.loadingVariables")}</small>
                        )}
                      </div>
                      <div className="col-md-6">
                        <label className="form-label">
                          {t("tags.unit")} <span className="text-danger">*</span>
                        </label>
                        <select
                          className="form-select"
                          required
                          value={formData.unit}
                          onChange={(e) =>
                            setFormData({ ...formData, unit: e.target.value })
                          }
                          disabled={!formData.variable || loadingUnits || availableUnits.length === 0}
                        >
                          <option value="">
                            {!formData.variable
                              ? t("tags.selectVariableFirst")
                              : loadingUnits
                              ? t("tags.loadingUnits")
                              : availableUnits.length === 0
                              ? t("tags.noUnitsAvailable")
                              : t("tags.selectUnit")}
                          </option>
                          {availableUnits.map((u) => (
                            <option key={u} value={u}>
                              {u}
                            </option>
                          ))}
                        </select>
                      </div>
                      <div className="col-md-6">
                        <label className="form-label">{t("tables.dataType")}</label>
                        <select
                          className="form-select"
                          value={formData.data_type}
                          onChange={(e) =>
                            setFormData({ ...formData, data_type: e.target.value })
                          }
                        >
                          <option value="float">float</option>
                          <option value="int">int</option>
                          <option value="bool">bool</option>
                          <option value="str">str</option>
                        </select>
                      </div>

                      {/* Campos opcionales básicos */}
                      <div className="col-md-6">
                        <label className="form-label">{t("tables.displayName")}</label>
                        <input
                          type="text"
                          className="form-control"
                          value={formData.display_name}
                          onChange={(e) =>
                            setFormData({ ...formData, display_name: e.target.value })
                          }
                        />
                      </div>
                      <div className="col-md-6">
                        <label className="form-label">{t("tables.displayUnit")}</label>
                        <select
                          className="form-select"
                          value={formData.display_unit}
                          onChange={(e) =>
                            setFormData({ ...formData, display_unit: e.target.value })
                          }
                          disabled={!formData.variable || loadingUnits || availableUnits.length === 0}
                        >
                          <option value="">
                            {!formData.variable
                              ? t("tags.selectVariableFirst")
                              : loadingUnits
                              ? t("tags.loadingUnits")
                              : availableUnits.length === 0
                              ? t("tags.noUnitsAvailable")
                              : t("tags.selectUnitOptional")}
                          </option>
                          {availableUnits.map((u) => (
                            <option key={u} value={u}>
                              {u}
                            </option>
                          ))}
                        </select>
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

                      {/* OPC UA */}
                      <div className="col-12">
                        <h6 className="border-bottom pb-2">{t("tags.opcuaConfiguration")}</h6>
                      </div>
                      <div className="col-md-6">
                        <label className="form-label">{t("tags.opcuaClient")}</label>
                        <select
                          className="form-select"
                          value={
                            Object.keys(opcuaClientAddresses).find(
                              (name) => opcuaClientAddresses[name] === formData.opcua_address
                            ) || ""
                          }
                          onChange={(e) => {
                            const selectedClientName = e.target.value;
                            const address = opcuaClientAddresses[selectedClientName] || "";
                            setFormData({
                              ...formData,
                              opcua_address: address,
                              node_namespace: "", // Limpiar namespace al cambiar cliente
                            });
                          }}
                          disabled={loadingClients}
                        >
                          <option value="">
                            {loadingClients ? t("tags.loadingClients") : t("tags.selectOpcuaClient")}
                          </option>
                          {Object.keys(opcuaClientAddresses).map((clientName) => (
                            <option key={clientName} value={clientName}>
                              {clientName} ({opcuaClientAddresses[clientName]})
                            </option>
                          ))}
                        </select>
                      </div>
                      <div className="col-md-6">
                        <label className="form-label">{t("tables.nodeNamespace")}</label>
                        <input
                          type="text"
                          className="form-control form-control-sm mb-1"
                          placeholder={t("common.filter")}
                          value={opcuaNodeFilter}
                          onChange={(e) => setOpcuaNodeFilter(e.target.value)}
                          disabled={!formData.opcua_address || loadingNodes || opcuaNodes.length === 0}
                        />
                        <select
                          className="form-select"
                          value={formData.node_namespace}
                          onChange={(e) =>
                            setFormData({ ...formData, node_namespace: e.target.value })
                          }
                          disabled={
                            !formData.opcua_address || loadingNodes || opcuaNodes.length === 0
                          }
                        >
                          <option value="">
                            {!formData.opcua_address
                              ? t("tags.selectOpcuaClientFirst")
                              : loadingNodes
                              ? t("tags.loadingNodes")
                              : opcuaNodes.length === 0
                              ? t("tags.noNodesAvailable")
                              : t("tags.selectNode")}
                          </option>
                          {filteredOpcuaNodes.map((node) => (
                            <option key={node.namespace} value={node.namespace}>
                              {node.displayName || node.namespace}
                            </option>
                          ))}
                        </select>
                      </div>

                      {/* Polling y Deadband */}
                      <div className="col-12">
                        <h6 className="border-bottom pb-2">{t("tags.pollingConfiguration")}</h6>
                      </div>
                      <div className="col-md-6">
                        <label className="form-label">{t("tables.scanTime")}</label>
                        <input
                          type="number"
                          className="form-control"
                          min="0"
                          value={formData.scan_time}
                          onChange={(e) =>
                            setFormData({ ...formData, scan_time: e.target.value })
                          }
                        />
                      </div>
                      <div className="col-md-6">
                        <label className="form-label">{t("tables.deadBand")}</label>
                        <input
                          type="number"
                          className="form-control"
                          step="0.01"
                          value={formData.dead_band}
                          onChange={(e) =>
                            setFormData({ ...formData, dead_band: e.target.value })
                          }
                        />
                      </div>

                      {/* Filtros */}
                      <div className="col-12">
                        <h6 className="border-bottom pb-2">{t("tags.filters")}</h6>
                      </div>
                      <div className="col-md-6">
                        <div className="form-check">
                          <input
                            className="form-check-input"
                            type="checkbox"
                            checked={formData.process_filter}
                            onChange={(e) =>
                              setFormData({
                                ...formData,
                                process_filter: e.target.checked,
                              })
                            }
                          />
                          <label className="form-check-label">{t("tags.processFilter")}</label>
                        </div>
                      </div>
                      <div className="col-md-6">
                        <div className="form-check">
                          <input
                            className="form-check-input"
                            type="checkbox"
                            checked={formData.gaussian_filter}
                            onChange={(e) =>
                              setFormData({
                                ...formData,
                                gaussian_filter: e.target.checked,
                              })
                            }
                          />
                          <label className="form-check-label">{t("tags.gaussianFilter")}</label>
                        </div>
                      </div>
                      {formData.gaussian_filter && (
                        <>
                          <div className="col-md-6">
                            <label className="form-label">{t("tags.gaussianFilterThreshold")}</label>
                            <input
                              type="number"
                              className="form-control"
                              step="0.1"
                              value={formData.gaussian_filter_threshold}
                              onChange={(e) =>
                                setFormData({
                                  ...formData,
                                  gaussian_filter_threshold: e.target.value,
                                })
                              }
                            />
                          </div>
                          <div className="col-md-6">
                            <label className="form-label">{t("tags.gaussianFilterRValue")}</label>
                            <input
                              type="number"
                              className="form-control"
                              step="0.1"
                              value={formData.gaussian_filter_r_value}
                              onChange={(e) =>
                                setFormData({
                                  ...formData,
                                  gaussian_filter_r_value: e.target.value,
                                })
                              }
                            />
                          </div>
                        </>
                      )}

                      {/* Detección */}
                      <div className="col-12">
                        <h6 className="border-bottom pb-2">{t("tags.detection")}</h6>
                      </div>
                      <div className="col-md-4">
                        <div className="form-check">
                          <input
                            className="form-check-input"
                            type="checkbox"
                            checked={formData.outlier_detection}
                            onChange={(e) =>
                              setFormData({
                                ...formData,
                                outlier_detection: e.target.checked,
                              })
                            }
                          />
                          <label className="form-check-label">{t("tags.outlierDetection")}</label>
                        </div>
                      </div>
                      <div className="col-md-4">
                        <div className="form-check">
                          <input
                            className="form-check-input"
                            type="checkbox"
                            checked={formData.out_of_range_detection}
                            onChange={(e) =>
                              setFormData({
                                ...formData,
                                out_of_range_detection: e.target.checked,
                              })
                            }
                          />
                          <label className="form-check-label">{t("tags.outOfRangeDetection")}</label>
                        </div>
                      </div>
                      <div className="col-md-4">
                        <div className="form-check">
                          <input
                            className="form-check-input"
                            type="checkbox"
                            checked={formData.frozen_data_detection}
                            onChange={(e) =>
                              setFormData({
                                ...formData,
                                frozen_data_detection: e.target.checked,
                              })
                            }
                          />
                          <label className="form-check-label">{t("tags.frozenDataDetection")}</label>
                        </div>
                      </div>

                      {/* Información adicional */}
                      <div className="col-12">
                        <h6 className="border-bottom pb-2">{t("tags.additionalInformation")}</h6>
                      </div>
                      <div className="col-md-6">
                        <label className="form-label">{t("tags.segment")}</label>
                        <input
                          type="text"
                          className="form-control"
                          value={formData.segment}
                          onChange={(e) =>
                            setFormData({ ...formData, segment: e.target.value })
                          }
                        />
                      </div>
                      <div className="col-md-6">
                        <label className="form-label">{t("tags.manufacturer")}</label>
                        <input
                          type="text"
                          className="form-control"
                          value={formData.manufacturer}
                          onChange={(e) =>
                            setFormData({ ...formData, manufacturer: e.target.value })
                          }
                        />
                      </div>
                    </div>
                  </div>
                  <div className="modal-footer" style={{ flexShrink: 0 }}>
                    <button
                      type="button"
                      className="btn btn-secondary"
                      onClick={() => {
                        setShowCreateModal(false);
                        setError(null);
                        setAvailableUnits([]);
                        setOpcuaNodes([]);
                      }}
                      disabled={creating}
                    >
                      {t("common.cancel")}
                    </button>
                    <Button type="submit" variant="success" loading={creating}>
                      {t("tags.createTag")}
                    </Button>
                  </div>
                </form>
              </div>
            </div>
          </div>
        )}

        {/* Modal para editar tag */}
        {showEditModal && editingTag && (
          <div
            className="modal fade show"
            style={{ display: "block", backgroundColor: "rgba(0,0,0,0.5)" }}
            tabIndex={-1}
            role="dialog"
          >
            <div className="modal-dialog modal-lg modal-dialog-scrollable" role="document" style={{ maxHeight: "90vh" }}>
              <div className="modal-content" style={{ maxHeight: "90vh", display: "flex", flexDirection: "column" }}>
                <div className="modal-header" style={{ flexShrink: 0 }}>
                  <h5 className="modal-title">{t("tags.editTagTitle", { name: editingTag.name })}</h5>
                  <button
                    type="button"
                    className="btn-close"
                    onClick={() => {
                      setShowEditModal(false);
                      setEditingTag(null);
                      setError(null);
                      setAvailableUnits([]);
                      setOpcuaNodes([]);
                    }}
                    aria-label="Close"
                  ></button>
                </div>
                <form onSubmit={handleUpdateTag} style={{ display: "flex", flexDirection: "column", flex: 1, minHeight: 0 }}>
                  <div className="modal-body" style={{ overflowY: "auto", flex: 1, minHeight: 0 }}>
                    {error && (
                      <div className="alert alert-danger" role="alert">
                        {error}
                      </div>
                    )}

                    <div className="row g-3">
                      {/* Campos requeridos */}
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
                          {t("tables.variable")} <span className="text-danger">*</span>
                        </label>
                        <select
                          className="form-select"
                          required
                          value={formData.variable}
                          onChange={(e) =>
                            setFormData({ ...formData, variable: e.target.value, unit: "", display_unit: "" })
                          }
                          disabled={loadingVariables}
                        >
                          <option value="">{t("tags.selectVariable")}</option>
                          {variables.map((v) => (
                            <option key={v} value={v}>
                              {v}
                            </option>
                          ))}
                        </select>
                        {loadingVariables && (
                          <small className="text-muted">{t("tags.loadingVariables")}</small>
                        )}
                      </div>
                      <div className="col-md-6">
                        <label className="form-label">
                          {t("tags.unit")} <span className="text-danger">*</span>
                        </label>
                        <select
                          className="form-select"
                          required
                          value={formData.unit}
                          onChange={(e) =>
                            setFormData({ ...formData, unit: e.target.value })
                          }
                          disabled={!formData.variable || loadingUnits || availableUnits.length === 0}
                        >
                          <option value="">
                            {!formData.variable
                              ? t("tags.selectVariableFirst")
                              : loadingUnits
                              ? t("tags.loadingUnits")
                              : availableUnits.length === 0
                              ? t("tags.noUnitsAvailable")
                              : t("tags.selectUnit")}
                          </option>
                          {availableUnits.map((u) => (
                            <option key={u} value={u}>
                              {u}
                            </option>
                          ))}
                        </select>
                      </div>
                      <div className="col-md-6">
                        <label className="form-label">{t("tables.dataType")}</label>
                        <select
                          className="form-select"
                          value={formData.data_type}
                          onChange={(e) =>
                            setFormData({ ...formData, data_type: e.target.value })
                          }
                        >
                          <option value="float">float</option>
                          <option value="int">int</option>
                          <option value="bool">bool</option>
                          <option value="str">str</option>
                        </select>
                      </div>

                      {/* Campos opcionales básicos */}
                      <div className="col-md-6">
                        <label className="form-label">{t("tables.displayName")}</label>
                        <input
                          type="text"
                          className="form-control"
                          value={formData.display_name}
                          onChange={(e) =>
                            setFormData({ ...formData, display_name: e.target.value })
                          }
                        />
                      </div>
                      <div className="col-md-6">
                        <label className="form-label">{t("tables.displayUnit")}</label>
                        <select
                          className="form-select"
                          value={formData.display_unit}
                          onChange={(e) =>
                            setFormData({ ...formData, display_unit: e.target.value })
                          }
                          disabled={!formData.variable || loadingUnits || availableUnits.length === 0}
                        >
                          <option value="">
                            {!formData.variable
                              ? t("tags.selectVariableFirst")
                              : loadingUnits
                              ? t("tags.loadingUnits")
                              : availableUnits.length === 0
                              ? t("tags.noUnitsAvailable")
                              : t("tags.selectUnitOptional")}
                          </option>
                          {availableUnits.map((u) => (
                            <option key={u} value={u}>
                              {u}
                            </option>
                          ))}
                        </select>
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

                      {/* OPC UA */}
                      <div className="col-12">
                        <h6 className="border-bottom pb-2">{t("tags.opcuaConfiguration")}</h6>
                      </div>
                      <div className="col-md-6">
                        <label className="form-label">{t("tags.opcuaClient")}</label>
                        <select
                          className="form-select"
                          value={
                            Object.keys(opcuaClientAddresses).find(
                              (name) => opcuaClientAddresses[name] === formData.opcua_address
                            ) || ""
                          }
                          onChange={(e) => {
                            const selectedClientName = e.target.value;
                            const address = opcuaClientAddresses[selectedClientName] || "";
                            setFormData({
                              ...formData,
                              opcua_address: address,
                              node_namespace: "", // Limpiar namespace al cambiar cliente
                            });
                          }}
                          disabled={loadingClients}
                        >
                          <option value="">
                            {loadingClients ? t("tags.loadingClients") : t("tags.selectOpcuaClient")}
                          </option>
                          {Object.keys(opcuaClientAddresses).map((clientName) => (
                            <option key={clientName} value={clientName}>
                              {clientName} ({opcuaClientAddresses[clientName]})
                            </option>
                          ))}
                        </select>
                      </div>
                      <div className="col-md-6">
                        <label className="form-label">{t("tables.nodeNamespace")}</label>
                        <input
                          type="text"
                          className="form-control form-control-sm mb-1"
                          placeholder={t("common.filter")}
                          value={opcuaNodeFilter}
                          onChange={(e) => setOpcuaNodeFilter(e.target.value)}
                          disabled={!formData.opcua_address || loadingNodes || opcuaNodes.length === 0}
                        />
                        <select
                          className="form-select"
                          value={formData.node_namespace}
                          onChange={(e) =>
                            setFormData({ ...formData, node_namespace: e.target.value })
                          }
                          disabled={
                            !formData.opcua_address || loadingNodes || opcuaNodes.length === 0
                          }
                        >
                          <option value="">
                            {!formData.opcua_address
                              ? t("tags.selectOpcuaClientFirst")
                              : loadingNodes
                              ? t("tags.loadingNodes")
                              : opcuaNodes.length === 0
                              ? t("tags.noNodesAvailable")
                              : t("tags.selectNode")}
                          </option>
                          {filteredOpcuaNodes.map((node) => (
                            <option key={node.namespace} value={node.namespace}>
                              {node.displayName || node.namespace}
                            </option>
                          ))}
                        </select>
                      </div>

                      {/* Polling y Deadband */}
                      <div className="col-12">
                        <h6 className="border-bottom pb-2">{t("tags.pollingConfiguration")}</h6>
                      </div>
                      <div className="col-md-6">
                        <label className="form-label">{t("tables.scanTime")}</label>
                        <input
                          type="number"
                          className="form-control"
                          min="0"
                          value={formData.scan_time}
                          onChange={(e) =>
                            setFormData({ ...formData, scan_time: e.target.value })
                          }
                        />
                      </div>
                      <div className="col-md-6">
                        <label className="form-label">{t("tables.deadBand")}</label>
                        <input
                          type="number"
                          className="form-control"
                          step="0.01"
                          value={formData.dead_band}
                          onChange={(e) =>
                            setFormData({ ...formData, dead_band: e.target.value })
                          }
                        />
                      </div>

                      {/* Filtros */}
                      <div className="col-12">
                        <h6 className="border-bottom pb-2">{t("tags.filters")}</h6>
                      </div>
                      <div className="col-md-6">
                        <div className="form-check">
                          <input
                            className="form-check-input"
                            type="checkbox"
                            checked={formData.process_filter}
                            onChange={(e) =>
                              setFormData({
                                ...formData,
                                process_filter: e.target.checked,
                              })
                            }
                          />
                          <label className="form-check-label">{t("tags.processFilter")}</label>
                        </div>
                      </div>
                      <div className="col-md-6">
                        <div className="form-check">
                          <input
                            className="form-check-input"
                            type="checkbox"
                            checked={formData.gaussian_filter}
                            onChange={(e) =>
                              setFormData({
                                ...formData,
                                gaussian_filter: e.target.checked,
                              })
                            }
                          />
                          <label className="form-check-label">{t("tags.gaussianFilter")}</label>
                        </div>
                      </div>
                      {formData.gaussian_filter && (
                        <>
                          <div className="col-md-6">
                            <label className="form-label">{t("tags.gaussianFilterThreshold")}</label>
                            <input
                              type="number"
                              className="form-control"
                              step="0.1"
                              value={formData.gaussian_filter_threshold}
                              onChange={(e) =>
                                setFormData({
                                  ...formData,
                                  gaussian_filter_threshold: e.target.value,
                                })
                              }
                            />
                          </div>
                          <div className="col-md-6">
                            <label className="form-label">{t("tags.gaussianFilterRValue")}</label>
                            <input
                              type="number"
                              className="form-control"
                              step="0.1"
                              value={formData.gaussian_filter_r_value}
                              onChange={(e) =>
                                setFormData({
                                  ...formData,
                                  gaussian_filter_r_value: e.target.value,
                                })
                              }
                            />
                          </div>
                        </>
                      )}

                      {/* Detección */}
                      <div className="col-12">
                        <h6 className="border-bottom pb-2">{t("tags.detection")}</h6>
                      </div>
                      <div className="col-md-4">
                        <div className="form-check">
                          <input
                            className="form-check-input"
                            type="checkbox"
                            checked={formData.outlier_detection}
                            onChange={(e) =>
                              setFormData({
                                ...formData,
                                outlier_detection: e.target.checked,
                              })
                            }
                          />
                          <label className="form-check-label">{t("tags.outlierDetection")}</label>
                        </div>
                      </div>
                      <div className="col-md-4">
                        <div className="form-check">
                          <input
                            className="form-check-input"
                            type="checkbox"
                            checked={formData.out_of_range_detection}
                            onChange={(e) =>
                              setFormData({
                                ...formData,
                                out_of_range_detection: e.target.checked,
                              })
                            }
                          />
                          <label className="form-check-label">{t("tags.outOfRangeDetection")}</label>
                        </div>
                      </div>
                      <div className="col-md-4">
                        <div className="form-check">
                          <input
                            className="form-check-input"
                            type="checkbox"
                            checked={formData.frozen_data_detection}
                            onChange={(e) =>
                              setFormData({
                                ...formData,
                                frozen_data_detection: e.target.checked,
                              })
                            }
                          />
                          <label className="form-check-label">{t("tags.frozenDataDetection")}</label>
                        </div>
                      </div>

                      {/* Información adicional */}
                      <div className="col-12">
                        <h6 className="border-bottom pb-2">{t("tags.additionalInformation")}</h6>
                      </div>
                      <div className="col-md-6">
                        <label className="form-label">{t("tags.segment")}</label>
                        <input
                          type="text"
                          className="form-control"
                          value={formData.segment}
                          onChange={(e) =>
                            setFormData({ ...formData, segment: e.target.value })
                          }
                        />
                      </div>
                      <div className="col-md-6">
                        <label className="form-label">{t("tags.manufacturer")}</label>
                        <input
                          type="text"
                          className="form-control"
                          value={formData.manufacturer}
                          onChange={(e) =>
                            setFormData({ ...formData, manufacturer: e.target.value })
                          }
                        />
                      </div>
                    </div>
                  </div>
                  <div className="modal-footer" style={{ flexShrink: 0 }}>
                    <button
                      type="button"
                      className="btn btn-secondary"
                      onClick={() => {
                        setShowEditModal(false);
                        setEditingTag(null);
                        setError(null);
                        setAvailableUnits([]);
                        setOpcuaNodes([]);
                      }}
                      disabled={updating}
                    >
                      {t("common.cancel")}
                    </button>
                    <Button type="submit" variant="success" loading={updating}>
                      {t("tags.updateTag")}
                    </Button>
                  </div>
                </form>
              </div>
            </div>
          </div>
        )}

        {/* Modal para confirmar eliminación de tag */}
        {showDeleteModal && tagToDelete && (
          <div
            className="modal fade show"
            style={{ display: "block", backgroundColor: "rgba(0,0,0,0.5)" }}
            tabIndex={-1}
            role="dialog"
          >
            <div className="modal-dialog" role="document">
              <div className="modal-content">
                <div className="modal-header">
                  <h5 className="modal-title">{t("tags.confirmDelete")}</h5>
                  <button
                    type="button"
                    className="btn-close"
                    onClick={() => {
                      setShowDeleteModal(false);
                      setTagToDelete(null);
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
                    {t("tags.confirmDeleteMessage", { name: tagToDelete.name })}
                  </p>
                  <p className="text-muted small mb-0">
                    {t("tags.cannotUndo")}
                  </p>
                </div>
                <div className="modal-footer">
                  <button
                    type="button"
                    className="btn btn-secondary"
                    onClick={() => {
                      setShowDeleteModal(false);
                      setTagToDelete(null);
                      setError(null);
                    }}
                    disabled={deleting}
                  >
                    {t("common.cancel")}
                  </button>
                  <Button
                    variant="danger"
                    onClick={confirmDeleteTag}
                    loading={deleting}
                  >
                    {t("common.delete")}
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
