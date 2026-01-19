import { useEffect, useMemo, useState, useCallback } from "react";
import { Card } from "../components/Card";
import { Button } from "../components/Button";
import {
  addClient,
  getClientTree,
  getClientTreeWithOptions,
  getClientTreeChildrenWithOptions,
  getNodeValues,
  getNodeAttributes,
  listClients,
  removeClient,
  updateClient,
  type OpcUaTreeNode,
  type OpcUaNodeValue,
  type OpcUaClient,
} from "../services/opcua";
import { useTranslation } from "../hooks/useTranslation";
import { socketService } from "../services/socket";

type SelectedNode = {
  client: string;
  namespace: string;
  displayName: string;
  lastValue?: any;
  lastTimestamp?: string;
  status?: string;
};

// Función helper para encontrar un nodo en el árbol por namespace
const findNodeByNamespace = (
  node: OpcUaTreeNode,
  namespace: string
): OpcUaTreeNode | null => {
  const nodeNamespace = (node.namespace && node.namespace.trim()) || (node.key && node.key.trim()) || "";
  if (nodeNamespace === namespace) {
    return node;
  }
  if (node.children) {
    for (const child of node.children) {
      const found = findNodeByNamespace(child, namespace);
      if (found) return found;
    }
  }
  return null;
};

function TreeNode({
  node,
  client,
  onSelect,
  onLoadChildren,
  level = 0,
  selectedNodes = [],
  onToggleSelect,
  allTreeNodes = [],
}: {
  node: OpcUaTreeNode;
  client: string;
  onSelect: (client: string, node: OpcUaTreeNode) => void;
  onLoadChildren?: (client: string, nodeId: string) => Promise<void>;
  level?: number;
  selectedNodes?: string[];
  onToggleSelect?: (namespace: string) => void;
  allTreeNodes?: OpcUaTreeNode[];
}) {
  // Para máxima fluidez: no auto-expandir (evita disparar múltiples cargas de hijos).
  // El usuario expande manualmente y ahí hacemos lazy-loading.
  const [isExpanded, setIsExpanded] = useState(false);
  const [isLoadingChildren, setIsLoadingChildren] = useState(false);
  
  // Extraer nombre - priorizar name, luego title, evitar strings vacíos
  const { t } = useTranslation();
  const nodeName = (node.name && node.name.trim()) || (node.title && node.title.trim()) || t("communications.unnamed");
  const nodeNamespace = (node.namespace && node.namespace.trim()) || (node.key && node.key.trim()) || "";
  const nodeClass = node.NodeClass || "";
  const isSelected = selectedNodes.includes(nodeNamespace);
  
  // Debug si el nombre es "Unnamed"
  const unnamedText = t("communications.unnamed");
  if (nodeName === unnamedText && level === 0) {
    console.warn("Root node is Unnamed, raw node:", node);
  }
  const canExpand = Boolean((node.children && node.children.length > 0) || node.has_children);
  const isVariable = nodeClass === "Variable";
  const isObject = nodeClass === "Object" || nodeClass === "ObjectType";
  const isFolder = nodeClass === "Object" && !isVariable;

  // Determinar el icono según el tipo de nodo
  const getIcon = () => {
    if (isVariable) return "bi-circle-fill text-primary";
    if (isObject || isFolder) return "bi-folder-fill text-warning";
    return "bi-file-earmark text-secondary";
  };

  // Solo permitir arrastrar variables
  const isDraggable = isVariable && nodeNamespace;

  return (
    <li className="nav-item" style={{ listStyle: "none" }}>
      <div
        className={`d-flex align-items-center gap-1 py-1 px-2 ${
          isVariable ? "cursor-pointer" : ""
        } ${isSelected ? "bg-light" : ""}`}
        style={{
          paddingLeft: `${level * 16}px`,
          cursor: isVariable ? "grab" : "default",
        }}
        draggable={!!isDraggable}
        onDragStart={(e) => {
          if (isDraggable && nodeNamespace) {
            // Si hay nodos seleccionados y este nodo está seleccionado, arrastrar todos los seleccionados
            // Si no hay selección múltiple o este nodo no está seleccionado, arrastrar solo este
            const shouldDragAll = selectedNodes.length > 0 && isSelected;
            
            const nodesToDrag = shouldDragAll
              ? selectedNodes.map((ns) => {
                  // Buscar el nodo completo en el árbol por namespace
                  let foundNode: OpcUaTreeNode | null = null;
                  for (const rootNode of allTreeNodes) {
                    foundNode = findNodeByNamespace(rootNode, ns);
                    if (foundNode) break;
                  }
                  
                  const displayName = foundNode
                    ? (foundNode.name || foundNode.title || t("communications.unnamed")).trim()
                    : t("communications.unnamed");
                  
                  return { client, namespace: ns, displayName };
                })
              : [{ client, namespace: nodeNamespace, displayName: nodeName }];
            
            e.dataTransfer.setData(
              "application/opcua-nodes",
              JSON.stringify(nodesToDrag)
            );
            // También mantener compatibilidad con el formato anterior
            e.dataTransfer.setData(
              "application/opcua-node",
              JSON.stringify({
                client,
                namespace: nodeNamespace,
                displayName: nodeName,
              })
            );
          }
        }}
        onClick={(e) => {
          // Si es variable y se hace Ctrl+Click o Cmd+Click, toggle selección
          if (isVariable && (e.ctrlKey || e.metaKey) && onToggleSelect) {
            e.stopPropagation();
            onToggleSelect(nodeNamespace);
            return;
          }
          
          // Click normal: expandir/colapsar o seleccionar
          if (canExpand) {
            const nextExpanded = !isExpanded;
            setIsExpanded(nextExpanded);
            if (
              nextExpanded &&
              nodeNamespace &&
              node.has_children &&
              (!node.children || node.children.length === 0) &&
              onLoadChildren
            ) {
              setIsLoadingChildren(true);
              onLoadChildren(client, nodeNamespace).finally(() => setIsLoadingChildren(false));
            }
          }
          if (isVariable && !canExpand) {
            onSelect(client, node);
          }
        }}
        onDoubleClick={() => {
          if (canExpand) {
            const nextExpanded = !isExpanded;
            setIsExpanded(nextExpanded);
            if (
              nextExpanded &&
              nodeNamespace &&
              node.has_children &&
              (!node.children || node.children.length === 0) &&
              onLoadChildren
            ) {
              setIsLoadingChildren(true);
              onLoadChildren(client, nodeNamespace).finally(() => setIsLoadingChildren(false));
            }
          }
        }}
      >
        {canExpand && (
          <i
            className={`bi ${isExpanded ? "bi-chevron-down" : "bi-chevron-right"} text-muted`}
            style={{ fontSize: "0.75rem", width: "16px", cursor: "pointer" }}
            onClick={(e) => {
              e.stopPropagation();
              const nextExpanded = !isExpanded;
              setIsExpanded(nextExpanded);
              if (
                nextExpanded &&
                nodeNamespace &&
                node.has_children &&
                (!node.children || node.children.length === 0) &&
                onLoadChildren
              ) {
                setIsLoadingChildren(true);
                onLoadChildren(client, nodeNamespace).finally(() => setIsLoadingChildren(false));
              }
            }}
          />
        )}
        {!canExpand && <span style={{ width: "16px", display: "inline-block" }} />}
        {isVariable && (
          <input
            type="checkbox"
            checked={isSelected}
            onChange={(e) => {
              e.stopPropagation();
              if (onToggleSelect) {
                onToggleSelect(nodeNamespace);
              }
            }}
            onClick={(e) => e.stopPropagation()}
            style={{ marginRight: "4px", cursor: "pointer" }}
            title={t("communications.ctrlClickForMultiSelect")}
          />
        )}
        <i className={`bi ${getIcon()}`} style={{ fontSize: "0.875rem" }} />
        <span
          className="flex-grow-1"
          style={{
            fontSize: "0.875rem",
            userSelect: "none",
            fontWeight: isVariable ? "normal" : "500",
          }}
          title={nodeNamespace || nodeName}
        >
          {nodeName}
        </span>
        {nodeNamespace && (
          <small
            className="text-muted"
            style={{ fontSize: "0.7rem", fontFamily: "monospace" }}
            title={nodeNamespace}
          >
            {nodeNamespace.length > 20
              ? `${nodeNamespace.substring(0, 20)}...`
              : nodeNamespace}
          </small>
        )}
      </div>
      {canExpand && isExpanded && (
        <ul className="nav flex-column" style={{ listStyle: "none", marginLeft: "8px" }}>
          {isLoadingChildren && (
            <li className="nav-item" style={{ listStyle: "none" }}>
              <div className="px-2 py-1 text-muted" style={{ paddingLeft: `${(level + 1) * 16}px` }}>
                Cargando...
              </div>
            </li>
          )}
          {!isLoadingChildren &&
            (node.children && node.children.length > 0 ? (
              node.children.map((child, idx) => (
                <TreeNode
                  key={`${nodeNamespace || nodeName}-${idx}`}
                  node={child}
                  client={client}
                  onSelect={onSelect}
                  onLoadChildren={onLoadChildren}
                  level={level + 1}
                  selectedNodes={selectedNodes}
                  onToggleSelect={onToggleSelect}
                  allTreeNodes={allTreeNodes}
                />
              ))
            ) : (
              <li className="nav-item" style={{ listStyle: "none" }}>
                <div className="px-2 py-1 text-muted" style={{ paddingLeft: `${(level + 1) * 16}px` }}>
                  (sin hijos)
                </div>
              </li>
            ))}
        </ul>
      )}
    </li>
  );
}

const SELECTED_CLIENT_STORAGE_KEY = "opcua_selected_client";
const SELECTED_NODES_STORAGE_KEY = "opcua_selected_nodes";

// Función helper para guardar nodos seleccionados
const saveSelectedNodes = (nodes: SelectedNode[]) => {
  try {
    localStorage.setItem(SELECTED_NODES_STORAGE_KEY, JSON.stringify(nodes));
  } catch (e) {
    console.warn("No se pudieron guardar los nodos seleccionados:", e);
  }
};

// Función helper para cargar nodos seleccionados
const loadSelectedNodes = (): SelectedNode[] => {
  try {
    const saved = localStorage.getItem(SELECTED_NODES_STORAGE_KEY);
    if (saved) {
      return JSON.parse(saved);
    }
  } catch (e) {
    console.warn("No se pudieron cargar los nodos seleccionados:", e);
  }
  return [];
};

export function Communications() {
  const { t } = useTranslation();
  const [clients, setClients] = useState<OpcUaClient[]>([]);
  const [clientConnectionStatus, setClientConnectionStatus] = useState<Record<string, boolean>>({});
  const [selectedClient, setSelectedClient] = useState<string>(() => {
    // Cargar cliente seleccionado previamente desde localStorage
    try {
      const saved = localStorage.getItem(SELECTED_CLIENT_STORAGE_KEY);
      return saved || "";
    } catch {
      return "";
    }
  });
  const [tree, setTree] = useState<OpcUaTreeNode[]>([]);
  const [loadingTree, setLoadingTree] = useState(false);
  const [loadingClients, setLoadingClients] = useState(false);
  const [form, setForm] = useState({ name: "", host: "127.0.0.1", port: 4840 });
  const [editingClient, setEditingClient] = useState<string | null>(null);
  const [selectedNodes, setSelectedNodes] = useState<SelectedNode[]>(() => {
    // Cargar nodos seleccionados previamente desde localStorage
    return loadSelectedNodes();
  });
  const [selectedTreeNodes, setSelectedTreeNodes] = useState<string[]>([]); // Para selección múltiple en el árbol
  const [polling, setPolling] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const namespacesToPoll = useMemo(
    () => selectedNodes.map((n) => n.namespace),
    [selectedNodes]
  );

  // Calcular estado de conexión del cliente seleccionado
  const selectedClientConnectionStatus = useMemo(() => {
    if (!selectedClient) return false;
    const selectedClientObj = clients.find(c => c.name === selectedClient);
    return selectedClientObj 
      ? (clientConnectionStatus[selectedClient] ?? selectedClientObj.is_opened ?? false)
      : false;
  }, [selectedClient, clients, clientConnectionStatus]);

  // Verificar si el formulario está completo para habilitar el botón Crear/Update
  const isFormComplete = useMemo(() => {
    if (editingClient) {
      // En modo edición, al menos un campo debe estar presente (nombre, host o port)
      return (
        (form.name.trim() !== "" && form.name.trim() !== editingClient) ||
        (form.host.trim() !== "" && form.host.trim() !== "") ||
        (form.port > 0)
      );
    }
    // En modo creación, todos los campos son requeridos
    return (
      form.name.trim() !== "" &&
      form.host.trim() !== "" &&
      form.port > 0
    );
  }, [form.name, form.host, form.port, editingClient]);

  // Función para extraer server_url del mensaje del evento
  const extractServerUrlFromMessage = useCallback((message: string): string | null => {
    if (!message) return null;
    // El mensaje tiene formato "Disconneted from opc.tcp://host:port" o "Conneted to opc.tcp://host:port"
    // (nota: hay typos en el backend - "Disconneted" y "Conneted")
    // También puede venir como "Disconnected from" o "Connected to"
    const match = message.match(/(?:Disconnected?|Conneted?)\s+from\s+(opc\.tcp:\/\/[^\s]+)/i) || 
                  message.match(/(?:Connected?|Conneted?)\s+to\s+(opc\.tcp:\/\/[^\s]+)/i) ||
                  message.match(/(opc\.tcp:\/\/[^\s]+)/i);
    return match ? match[1] : null;
  }, []);

  // Verificar estado de conexión de un cliente específico
  const checkClientConnection = useCallback((clientName: string, clientList?: OpcUaClient[]) => {
    const clientListToUse = clientList || clients;
    const client = clientListToUse.find((c) => c.name === clientName);
    if (client) {
      // Usar is_opened del cliente si está disponible
      setClientConnectionStatus((prev) => ({
        ...prev,
        [clientName]: client.is_opened ?? prev[clientName] ?? false,
      }));
    }
  }, [clients]);

  // Escuchar eventos de conexión/desconexión OPC UA
  useEffect(() => {
    const handleOpcUaDisconnected = (data: { message: string; server_url?: string }) => {
      console.log("OPC UA disconnected event received:", data);
      const serverUrl = data.server_url || extractServerUrlFromMessage(data.message || "");
      console.log("Extracted server_url:", serverUrl);
      
      if (serverUrl) {
        setClientConnectionStatus((prev) => {
          const updated = { ...prev };
          let updatedCount = 0;
          
          // Buscar todos los clientes que coincidan con este server_url
          clients.forEach((client) => {
            if (client.server_url === serverUrl) {
              updated[client.name] = false;
              updatedCount++;
              console.log(`Client ${client.name} marked as disconnected`);
            }
          });
          
          // Si no encontramos ningún cliente, intentar buscar por el server_url extraído del mensaje
          if (updatedCount === 0) {
            console.warn(`OPC UA disconnected event received for unknown server: ${serverUrl}`);
            console.log("Available clients:", clients.map(c => ({ name: c.name, server_url: c.server_url })));
          }
          
          return updated;
        });
      } else {
        console.warn("Could not extract server_url from disconnected event:", data);
      }
    };

    const handleOpcUaConnected = (data: { message: string; server_url?: string }) => {
      console.log("OPC UA connected event received:", data);
      const serverUrl = data.server_url || extractServerUrlFromMessage(data.message || "");
      console.log("Extracted server_url:", serverUrl);
      
      if (serverUrl) {
        setClientConnectionStatus((prev) => {
          const updated = { ...prev };
          let updatedCount = 0;
          
          // Buscar todos los clientes que coincidan con este server_url
          clients.forEach((client) => {
            if (client.server_url === serverUrl) {
              updated[client.name] = true;
              updatedCount++;
              console.log(`Client ${client.name} marked as connected`);
            }
          });
          
          // Si no encontramos ningún cliente, intentar buscar por el server_url extraído del mensaje
          if (updatedCount === 0) {
            console.warn(`OPC UA connected event received for unknown server: ${serverUrl}`);
            console.log("Available clients:", clients.map(c => ({ name: c.name, server_url: c.server_url })));
          }
          
          return updated;
        });
      } else {
        console.warn("Could not extract server_url from connected event:", data);
      }
    };

    // Suscribirse a los eventos
    const cleanupDisconnected = socketService.onOpcUaDisconnected(handleOpcUaDisconnected);
    const cleanupConnected = socketService.onOpcUaConnected(handleOpcUaConnected);

    return () => {
      cleanupDisconnected();
      cleanupConnected();
    };
  }, [clients, extractServerUrlFromMessage]);

  const loadClients = async () => {
    setLoadingClients(true);
    try {
      setError(null);
      const list = await listClients();
      // Normalizar la lista de clientes
      const clientsList: OpcUaClient[] = list.map((c) => {
        if (typeof c === "string") {
          return { name: c, is_opened: false };
        }
        return {
          name: c.name || "",
          host: c.host,
          port: c.port,
          server_url: c.server_url,
          is_opened: c.is_opened ?? false,
          client_id: c.client_id,
        };
      }).filter((c) => c.name);
      
      setClients(clientsList);
      
      // Actualizar estado de conexión basado en is_opened
      const connectionStatus: Record<string, boolean> = {};
      clientsList.forEach((client) => {
        connectionStatus[client.name] = client.is_opened ?? false;
      });
      setClientConnectionStatus(connectionStatus);
      
      // Si hay clientes disponibles
      if (clientsList.length > 0) {
        const names = clientsList.map((c) => c.name);
        // Si hay un cliente guardado y está en la lista, usarlo
        const savedClient = localStorage.getItem(SELECTED_CLIENT_STORAGE_KEY);
        if (savedClient && names.includes(savedClient)) {
          setSelectedClient(savedClient);
          // Verificar estado de conexión del cliente seleccionado
          checkClientConnection(savedClient, clientsList);
        } else if (!selectedClient) {
          // Si no hay cliente seleccionado, usar el primero
          const firstClient = names[0];
          setSelectedClient(firstClient);
          localStorage.setItem(SELECTED_CLIENT_STORAGE_KEY, firstClient);
          // Verificar estado de conexión del primer cliente
          checkClientConnection(firstClient, clientsList);
        }
      } else {
        // Si no hay clientes, limpiar selección
        setSelectedClient("");
        localStorage.removeItem(SELECTED_CLIENT_STORAGE_KEY);
        setClientConnectionStatus({});
      }
    } catch (e: any) {
      const errorMsg = e?.response?.data?.message || e?.message || t("communications.title");
      setError(errorMsg);
      setClients([]);
      setSelectedClient("");
      localStorage.removeItem(SELECTED_CLIENT_STORAGE_KEY);
      setClientConnectionStatus({});
    } finally {
      setLoadingClients(false);
    }
  };

  const loadTree = async (clientName: string) => {
    if (!clientName) {
      setTree([]);
      return;
    }
    setLoadingTree(true);
    setError(null);
    try {
      // Para evitar congelar la UI en servidores con árboles muy grandes,
      // pedimos un árbol acotado y dejamos fallback automático a legacy si es necesario.
      const treeNodes = await getClientTreeWithOptions(clientName, {
        mode: "generic",
        // Para máxima fluidez: cargar SOLO la primera profundidad, y luego lazy-load al expandir.
        max_depth: 1,
        max_nodes: 5000,
        // Para el explorer no necesitamos properties (EURange/etc.) porque no se enlazan como tags.
        include_properties: false,
        include_property_values: false,
        timeout_ms: 60_000,
        fallback_to_legacy: true,
      });
      // Asegurarnos de que sea un array
      const treeArray = Array.isArray(treeNodes) ? treeNodes : treeNodes ? [treeNodes] : [];
      setTree(treeArray);
    } catch (e: any) {
      const errorMsg = e?.response?.data?.message || e?.message || t("communications.explorer");
      setError(errorMsg);
      setTree([]);
    } finally {
      setLoadingTree(false);
    }
  };

  // Lazy-loading: cargar hijos de un nodo al expandir, para soportar árboles profundos sin timeouts.
  const setChildrenForNode = useCallback(
    (targetNamespace: string, children: OpcUaTreeNode[]) => {
      const update = (nodes: OpcUaTreeNode[]): OpcUaTreeNode[] =>
        nodes.map((n) => {
          const ns = (n.namespace && n.namespace.trim()) || (n.key && n.key.trim()) || "";
          if (ns === targetNamespace) {
            return { ...n, children, has_children: children.length > 0 };
          }
          if (n.children && n.children.length > 0) {
            return { ...n, children: update(n.children) };
          }
          return n;
        });
      setTree((prev) => update(prev));
    },
    [setTree]
  );

  const loadChildren = useCallback(
    async (clientName: string, nodeId: string) => {
      if (!clientName || !nodeId) return;
      const children = await getClientTreeChildrenWithOptions(clientName, nodeId, {
        mode: "generic",
        max_nodes: 5000,
        include_properties: true,
        include_property_values: false,
        timeout_ms: 60_000,
        fallback_to_legacy: true,
      });
      setChildrenForNode(nodeId, children);
    },
    [setChildrenForNode]
  );

  // Cargar clientes al montar el componente
  useEffect(() => {
    loadClients();
  }, []);

  // Verificar estado de conexión cuando cambian los clientes
  useEffect(() => {
    clients.forEach((client) => {
      // Inicializar estado de conexión basado en is_opened
      setClientConnectionStatus((prev) => ({
        ...prev,
        [client.name]: client.is_opened ?? prev[client.name] ?? false,
      }));
    });
  }, [clients]);

  // Cargar atributos de los nodos seleccionados cuando se monta el componente o cambia el cliente
  useEffect(() => {
    if (selectedClient && selectedNodes.length > 0) {
      // Verificar que los nodos pertenezcan al cliente actual
      const nodesForClient = selectedNodes.filter((n) => n.client === selectedClient);
      if (nodesForClient.length > 0) {
        const namespaces = nodesForClient.map((n) => n.namespace);
        getNodeAttributes(selectedClient, namespaces)
          .then((attrs) => {
            setSelectedNodes((current) =>
              current.map((n) => {
                if (n.client !== selectedClient) return n;
                const attr = attrs.find(
                  (a: any) => (a.Namespace || a.namespace) === n.namespace
                );
                if (!attr) return n;
                const dataValue = attr.DataValue;
                return {
                  ...n,
                  displayName: attr.DisplayName || attr.displayName || n.displayName,
                  lastValue: attr.Value ?? attr.value ?? undefined,
                  lastTimestamp:
                    dataValue?.SourceTimestamp ||
                    attr.SourceTimestamp ||
                    attr.source_timestamp ||
                    undefined,
                  status:
                    dataValue?.StatusCode ||
                    attr.StatusCode ||
                    attr.status_code ||
                    undefined,
                };
              })
            );
          })
          .catch((err) => {
            console.debug("Error cargando atributos iniciales:", err);
          });
      } else {
        // Si no hay nodos para este cliente, limpiar los que no corresponden
        setSelectedNodes([]);
        saveSelectedNodes([]);
      }
    }
  }, [selectedClient]);

  // Cargar árbol automáticamente cuando se selecciona un cliente
  useEffect(() => {
    if (selectedClient) {
      // Guardar cliente seleccionado en localStorage
      try {
        localStorage.setItem(SELECTED_CLIENT_STORAGE_KEY, selectedClient);
      } catch (e) {
        console.warn("No se pudo guardar el cliente seleccionado:", e);
      }
      // Verificar estado de conexión del cliente seleccionado
      checkClientConnection(selectedClient);
      // Cargar el árbol del cliente seleccionado
      loadTree(selectedClient);
      
      // Filtrar nodos seleccionados para mostrar solo los del cliente actual
      setSelectedNodes((prev) => {
        const filtered = prev.filter((n) => n.client === selectedClient);
        if (filtered.length !== prev.length) {
          // Si se filtraron algunos nodos, guardar la lista filtrada
          saveSelectedNodes(filtered);
        }
        return filtered;
      });
    } else {
      // Si no hay cliente seleccionado, limpiar el árbol
      setTree([]);
    }
  }, [selectedClient, checkClientConnection]);

  // Polling de atributos cada segundo (usando /attrs para obtener timestamp y status)
  useEffect(() => {
    if (!polling || !selectedClient || namespacesToPoll.length === 0) return;
    const id = setInterval(async () => {
      try {
        // Usar /attrs en lugar de /values para obtener información completa (timestamp, status)
        const attributes = await getNodeAttributes(selectedClient, namespacesToPoll);
        setSelectedNodes((prev) => {
          const updated = prev.map((n) => {
            // Solo actualizar nodos del cliente actual
            if (n.client !== selectedClient) return n;
            
            // Buscar el atributo correspondiente por namespace
            const match = attributes.find(
              (attr: any) =>
                (attr.Namespace || attr.namespace) === n.namespace
            );
            if (!match) return n;
            
            // Extraer información de DataValue si existe
            const dataValue = match.DataValue;
            const value = match.Value ?? match.value ?? null;
            const timestamp =
              dataValue?.SourceTimestamp ||
              match.SourceTimestamp ||
              match.source_timestamp ||
              null;
            const status =
              dataValue?.StatusCode ||
              match.StatusCode ||
              match.status_code ||
              null;
            
            return {
              ...n,
              displayName: match.DisplayName || match.displayName || n.displayName,
              lastValue: value,
              lastTimestamp: timestamp ?? undefined,
              status: status ?? undefined,
            };
          });
          
          // Guardar en localStorage después de actualizar
          saveSelectedNodes(updated);
          return updated;
        });
      } catch (_e) {
        // Silencioso: evitamos spam en la consola, pero podríamos mostrar un indicador visual
        console.debug("Error en polling de atributos:", _e);
      }
    }, 1000);
    return () => clearInterval(id);
  }, [polling, selectedClient, namespacesToPoll]);

  const onDropNode = async (e: React.DragEvent<HTMLDivElement>) => {
    // Intentar obtener múltiples nodos primero (selección múltiple)
    let rawNodes = e.dataTransfer.getData("application/opcua-nodes");
    let nodesToAdd: Array<{ client: string; namespace: string; displayName: string }> = [];
    
    if (rawNodes) {
      try {
        nodesToAdd = JSON.parse(rawNodes);
      } catch (_e) {
        // Si falla, intentar con el formato antiguo
      }
    }
    
    // Si no hay múltiples nodos, intentar con el formato antiguo (un solo nodo)
    if (nodesToAdd.length === 0) {
      const raw = e.dataTransfer.getData("application/opcua-node");
      if (raw) {
        try {
          const node = JSON.parse(raw);
          if (node.namespace && node.client) {
            nodesToAdd = [node];
          }
        } catch (_e) {
          console.error("Error al procesar nodo arrastrado:", _e);
          return;
        }
      } else {
        return;
      }
    }
    
    if (nodesToAdd.length === 0) return;
    
    try {
      // Filtrar nodos que ya están en la lista
      setSelectedNodes((prev) => {
        const newNodes = nodesToAdd.filter(
          (n) => !prev.some((p) => p.namespace === n.namespace && p.client === n.client)
        );
        
        if (newNodes.length === 0) return prev;
        
        // Agregar los nuevos nodos inicialmente sin datos
        const newSelectedNodes: SelectedNode[] = newNodes.map((n) => ({
          client: n.client,
          namespace: n.namespace,
          displayName: n.displayName,
        }));
        
        const newList = [...prev, ...newSelectedNodes];
        
        // Guardar inmediatamente en localStorage
        saveSelectedNodes(newList);
        
        // Obtener atributos de todos los nuevos nodos
        const namespaces = newNodes.map((n) => n.namespace);
        const clientName = newNodes[0].client; // Todos deben ser del mismo cliente
        
        getNodeAttributes(clientName, namespaces)
          .then((attrs) => {
            setSelectedNodes((current) => {
              const updated = current.map((n) => {
                // Solo actualizar los nuevos nodos
                if (!newNodes.some((nn) => nn.namespace === n.namespace)) return n;
                
                const attr = attrs.find(
                  (a: any) => (a.Namespace || a.namespace) === n.namespace
                );
                if (!attr) return n;
                
                // Extraer información de DataValue si existe
                const dataValue = attr.DataValue;
                return {
                  ...n,
                  displayName: attr.DisplayName || attr.displayName || n.displayName,
                  lastValue: attr.Value ?? attr.value ?? undefined,
                  lastTimestamp:
                    dataValue?.SourceTimestamp ||
                    attr.SourceTimestamp ||
                    attr.source_timestamp ||
                    undefined,
                  status:
                    dataValue?.StatusCode ||
                    attr.StatusCode ||
                    attr.status_code ||
                    undefined,
                };
              });
              // Guardar después de actualizar con atributos
              saveSelectedNodes(updated);
              return updated;
            });
          })
          .catch((err) => {
            console.debug("Error obteniendo atributos iniciales:", err);
          });
        
        return newList;
      });
      
      // Limpiar selección en el árbol después de arrastrar
      setSelectedTreeNodes([]);
    } catch (_e) {
      console.error("Error al procesar nodos arrastrados:", _e);
    }
  };
  
  const handleToggleTreeNodeSelect = (namespace: string) => {
    setSelectedTreeNodes((prev) => {
      if (prev.includes(namespace)) {
        return prev.filter((n) => n !== namespace);
      } else {
        return [...prev, namespace];
      }
    });
  };

  const handleAddClient = async () => {
    if (!form.name || !form.host || !form.port) {
      setError(t("common.error"));
      return;
    }
    try {
      setError(null);
      const clientName = form.name;
      await addClient({ name: clientName, host: form.host, port: Number(form.port) });
      setForm({ name: "", host: "127.0.0.1", port: 4840 });
      await loadClients();
      // Seleccionar el cliente recién creado
      setSelectedClient(clientName);
      localStorage.setItem(SELECTED_CLIENT_STORAGE_KEY, clientName);
    } catch (e: any) {
      const errorMsg = e?.response?.data?.message || e?.message || t("communications.title");
      setError(errorMsg);
    }
  };

  const handleRemoveClient = async (clientName: string) => {
    if (!clientName) return;
    try {
      setError(null);
      await removeClient(clientName);
      // Si se eliminó el cliente seleccionado, limpiar la selección
      if (clientName === selectedClient) {
        localStorage.removeItem(SELECTED_CLIENT_STORAGE_KEY);
        setSelectedClient("");
        setTree([]);
        // Limpiar solo los nodos de este cliente
        setSelectedNodes((prev) => {
          const updated = prev.filter((n) => n.client !== clientName);
          saveSelectedNodes(updated);
          return updated;
        });
      } else {
        // Si se eliminó otro cliente, solo remover sus nodos
        setSelectedNodes((prev) => {
          const updated = prev.filter((n) => n.client !== clientName);
          saveSelectedNodes(updated);
          return updated;
        });
      }
      await loadClients();
    } catch (e: any) {
      const errorMsg = e?.response?.data?.message || e?.message || t("communications.title");
      setError(errorMsg);
    }
  };

  const handleEditClient = (clientName: string) => {
    const client = clients.find((c) => c.name === clientName);
    if (client) {
      // Extraer host y port del server_url si no están disponibles directamente
      let host = client.host;
      let port = client.port;
      
      // Si no tenemos host/port directos, intentar extraerlos del server_url
      if ((!host || !port) && client.server_url) {
        try {
          // Formato: opc.tcp://host:port
          const urlMatch = client.server_url.match(/opc\.tcp:\/\/([^:]+):(\d+)/);
          if (urlMatch) {
            host = host || urlMatch[1];
            port = port || parseInt(urlMatch[2], 10);
          }
        } catch (e) {
          console.warn("Error parsing server_url:", e);
        }
      }
      
      // Valores por defecto si aún no tenemos host/port
      setForm({
        name: client.name || "",
        host: host || "127.0.0.1",
        port: port || 4840,
      });
      setEditingClient(clientName);
    }
  };

  const handleCancelEdit = () => {
    setEditingClient(null);
    setForm({ name: "", host: "127.0.0.1", port: 4840 });
  };

  const handleUpdateClient = async () => {
    if (!editingClient) {
      setError(t("common.error"));
      return;
    }
    try {
      setError(null);
      // Solo enviar los campos que tienen valores
      const newName = form.name && form.name.trim() !== "" ? form.name : undefined;
      const newHost = form.host && form.host.trim() !== "" ? form.host : undefined;
      const newPort = form.port && form.port > 0 ? Number(form.port) : undefined;
      
      await updateClient(editingClient, newName, newHost, newPort);
      setEditingClient(null);
      setForm({ name: "", host: "127.0.0.1", port: 4840 });
      await loadClients();
      // Si el nombre cambió, actualizar la selección
      const finalName = newName || editingClient;
      if (editingClient !== finalName) {
        // Actualizar nodos seleccionados que usan el cliente antiguo
        setSelectedNodes((prev) => {
          const updated = prev.map((n) => {
            if (n.client === editingClient) {
              return { ...n, client: finalName };
            }
            return n;
          });
          saveSelectedNodes(updated);
          return updated;
        });
        // Si era el cliente seleccionado, cambiar la selección
        if (selectedClient === editingClient) {
          setSelectedClient(finalName);
          localStorage.setItem(SELECTED_CLIENT_STORAGE_KEY, finalName);
        }
      } else {
        // Si solo cambió host/port o no cambió nada, recargar el árbol si estaba seleccionado
        if (selectedClient === finalName) {
          loadTree(finalName);
        }
      }
    } catch (e: any) {
      const errorMsg = e?.response?.data?.message || e?.message || t("communications.title");
      setError(errorMsg);
    }
  };

  return (
    <div className="row">
      <div className="col-lg-4">
        <Card
          title={t("communications.title")}
          footer={
            <div className="d-flex gap-2">
              {editingClient ? (
                <>
                  <Button 
                    variant="primary" 
                    onClick={handleUpdateClient}
                    disabled={!isFormComplete}
                  >
                    {t("common.update")}
                  </Button>
                  <Button
                    variant="secondary"
                    onClick={handleCancelEdit}
                  >
                    {t("common.cancel")}
                  </Button>
                </>
              ) : (
                <>
              <Button 
                variant="primary" 
                onClick={handleAddClient}
                disabled={!isFormComplete}
              >
                {t("communications.create")}
              </Button>
                  {selectedClient && (
                    <Button
                      variant="warning"
                      onClick={() => handleEditClient(selectedClient)}
                    >
                      {t("common.edit")}
                    </Button>
                  )}
              <Button
                variant="danger"
                onClick={() => selectedClient && handleRemoveClient(selectedClient)}
                disabled={!selectedClient}
              >
                {t("communications.remove")}
              </Button>
                </>
              )}
            </div>
          }
        >
          <div className="mb-2">
            <label className="form-label mb-1">{t("communications.selectedClient")}</label>
            <div className="d-flex align-items-center gap-2">
            <select
                className="form-select flex-grow-1"
              value={selectedClient}
              onChange={(e) => setSelectedClient(e.target.value)}
                disabled={loadingClients || editingClient !== null}
            >
              <option value="">{loadingClients ? t("communications.loading") : t("communications.selectClient")}</option>
                {clients.map((client) => {
                  const isConnected = clientConnectionStatus[client.name] ?? client.is_opened ?? false;
                  return (
                    <option key={client.name} value={client.name}>
                      {client.name} {isConnected ? "●" : "○"}
                </option>
                  );
                })}
            </select>
              {selectedClient && (
                <span
                  className="d-inline-block"
                  style={{
                    width: "20px",
                    height: "20px",
                    minWidth: "20px",
                    borderRadius: "50%",
                    backgroundColor: selectedClientConnectionStatus ? "#28a745" : "#dc3545",
                    boxShadow: selectedClientConnectionStatus
                      ? "0 0 12px rgba(40, 167, 69, 0.9), 0 0 6px rgba(40, 167, 69, 0.6), inset 0 2px 4px rgba(255, 255, 255, 0.4), inset 0 -2px 4px rgba(0, 0, 0, 0.3)"
                      : "0 0 12px rgba(220, 53, 69, 0.9), 0 0 6px rgba(220, 53, 69, 0.6), inset 0 2px 4px rgba(255, 255, 255, 0.4), inset 0 -2px 4px rgba(0, 0, 0, 0.3)",
                    border: "2px solid rgba(255, 255, 255, 0.6)",
                    flexShrink: 0,
                    cursor: "default",
                    transition: "all 0.3s ease",
                  }}
                  title={
                    selectedClientConnectionStatus
                      ? (t("communications.clientConnected") || "Client Connected")
                      : (t("communications.clientDisconnected") || "Client Disconnected")
                  }
                />
              )}
          </div>
          </div>
          {editingClient && (
            <div className="alert alert-info mb-2 py-2">
              <small>{t("common.editing")}: <strong>{editingClient}</strong></small>
            </div>
          )}
          <div className="row g-2">
            <div className="col-12 col-md-4">
              <input
                className="form-control"
                placeholder={t("communications.clientName")}
                value={form.name}
                onChange={(e) => setForm((p) => ({ ...p, name: e.target.value }))}
              />
            </div>
            <div className="col-12 col-md-5">
              <input
                className="form-control"
                placeholder={t("communications.host")}
                value={form.host}
                onChange={(e) => setForm((p) => ({ ...p, host: e.target.value }))}
              />
            </div>
            <div className="col-12 col-md-3">
              <input
                className="form-control"
                placeholder={t("communications.port")}
                type="number"
                value={form.port}
                onChange={(e) => setForm((p) => ({ ...p, port: Number(e.target.value) }))}
              />
            </div>
          </div>
          {error && <div className="alert alert-danger mt-2 mb-0 py-2">{error}</div>}
        </Card>

        <Card title={`${t("communications.explorer")} ${selectedClient ? `(${selectedClient})` : ""}`}>
          {!selectedClient && (
            <div className="text-muted">{t("communications.selectClientToView")}</div>
          )}
          {selectedClient && loadingTree && (
            <div className="text-muted">
              <div className="spinner-border spinner-border-sm me-2" role="status">
                <span className="visually-hidden">{t("communications.loading")}</span>
              </div>
              {t("communications.loadingTree")}
            </div>
          )}
          {selectedClient && !loadingTree && tree.length === 0 && (
            <div className="text-muted">{t("communications.noNodesAvailable")}</div>
          )}
          {selectedClient && !loadingTree && tree.length > 0 && (
            <div
              style={{
                maxHeight: 420,
                overflowY: "auto",
                overflowX: "hidden",
                border: "1px solid #dee2e6",
                borderRadius: "0.25rem",
                padding: "0.5rem",
              }}
            >
              <div className="mb-2 d-flex justify-content-between align-items-center">
                <small className="text-muted">
                  {t("communications.ctrlClickForMultiSelect")}
                </small>
                {selectedTreeNodes.length > 0 && (
                  <Button
                    variant="secondary"
                    className="btn-sm"
                    onClick={() => setSelectedTreeNodes([])}
                  >
                    {t("communications.clearSelection")} ({selectedTreeNodes.length})
                  </Button>
                )}
              </div>
              <ul className="nav flex-column mb-0" style={{ listStyle: "none", paddingLeft: 0 }}>
                {tree.map((node, idx) => {
                  // Debug: verificar que el nodo tenga datos
                  if (!node.name && !node.title) {
                    console.warn(`Node ${idx} missing name/title:`, node);
                  }
                  return (
                    <TreeNode
                      key={`root-${node.namespace || node.key || idx}-${idx}`}
                      node={node}
                      client={selectedClient}
                      onSelect={() => {}}
                      onLoadChildren={loadChildren}
                      level={0}
                      selectedNodes={selectedTreeNodes}
                      onToggleSelect={handleToggleTreeNodeSelect}
                      allTreeNodes={tree}
                    />
                  );
                })}
              </ul>
            </div>
          )}
        </Card>
      </div>

      <div className="col-lg-8">
        <Card
          title={t("communications.selectedTags")}
          footer={
            <div className="d-flex justify-content-between align-items-center">
              <div className="form-check">
                <input
                  id="pollingToggle"
                  className="form-check-input"
                  type="checkbox"
                  checked={polling}
                  onChange={(e) => setPolling(e.target.checked)}
                />
                <label className="form-check-label ms-1" htmlFor="pollingToggle">
                  {t("communications.pollingEvery1s")}
                </label>
              </div>
              <Button
                variant="danger"
                onClick={() => {
                  setSelectedNodes([]);
                  saveSelectedNodes([]);
                }}
                disabled={selectedNodes.length === 0}
              >
                {t("common.clear")}
              </Button>
            </div>
          }
        >
          <div
            className="border rounded p-2 mb-3"
            style={{ minHeight: 120 }}
            onDragOver={(e) => e.preventDefault()}
            onDrop={onDropNode}
          >
            <div className="text-muted small mb-2">
              {t("communications.dragNodesToMonitor")}
            </div>
            {selectedNodes.length === 0 && (
              <div className="text-muted">{t("communications.noNodesSelected")}</div>
            )}
            {selectedNodes.length > 0 && (
              <div className="table-responsive">
                <table className="table table-sm align-middle mb-0">
                  <thead>
                    <tr>
                      <th>{t("communications.namespace")}</th>
                      <th>{t("communications.displayName")}</th>
                      <th>{t("communications.value")}</th>
                      <th>{t("communications.timestamp")}</th>
                      <th>{t("communications.status")}</th>
                      <th></th>
                    </tr>
                  </thead>
                  <tbody>
                    {selectedNodes.map((n) => (
                      <tr key={n.namespace}>
                        <td className="text-truncate" style={{ maxWidth: 140 }} title={n.namespace}>
                          {n.namespace}
                        </td>
                        <td>{n.displayName}</td>
                        <td>
                          {n.lastValue !== null && n.lastValue !== undefined ? (
                            <code>{String(n.lastValue)}</code>
                          ) : (
                            <span className="text-muted">-</span>
                          )}
                        </td>
                        <td className="text-truncate" style={{ maxWidth: 160 }} title={n.lastTimestamp || ""}>
                          {n.lastTimestamp ? (
                            <small>{new Date(n.lastTimestamp).toLocaleString()}</small>
                          ) : (
                            <span className="text-muted">-</span>
                          )}
                        </td>
                        <td>
                          {n.status ? (
                            <span className={`badge ${n.status === "Good" ? "bg-success" : "bg-warning"}`}>
                              {n.status}
                            </span>
                          ) : (
                            <span className="text-muted">-</span>
                          )}
                        </td>
                        <td>
                          <Button
                            variant="danger"
                            className="btn-sm"
                            onClick={() => {
                              setSelectedNodes((prev) => {
                                const updated = prev.filter((p) => p.namespace !== n.namespace);
                                saveSelectedNodes(updated);
                                return updated;
                              });
                            }}
                          >
                            {t("communications.remove")}
                          </Button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </Card>
      </div>
    </div>
  );
}
