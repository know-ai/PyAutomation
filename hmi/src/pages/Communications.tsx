import { useEffect, useMemo, useState } from "react";
import { Card } from "../components/Card";
import { Button } from "../components/Button";
import {
  addClient,
  getClientTree,
  getNodeValues,
  getNodeAttributes,
  listClients,
  removeClient,
  type OpcUaTreeNode,
  type OpcUaNodeValue,
} from "../services/opcua";

type SelectedNode = {
  client: string;
  namespace: string;
  displayName: string;
  lastValue?: any;
  lastTimestamp?: string;
  status?: string;
};

function TreeNode({
  node,
  client,
  onSelect,
  level = 0,
}: {
  node: OpcUaTreeNode;
  client: string;
  onSelect: (client: string, node: OpcUaTreeNode) => void;
  level?: number;
}) {
  const [isExpanded, setIsExpanded] = useState(level < 2); // Expandir los primeros 2 niveles por defecto
  
  // Extraer nombre - priorizar name, luego title, evitar strings vacíos
  const nodeName = (node.name && node.name.trim()) || (node.title && node.title.trim()) || "Unnamed";
  const nodeNamespace = (node.namespace && node.namespace.trim()) || (node.key && node.key.trim()) || "";
  const nodeClass = node.NodeClass || "";
  
  // Debug si el nombre es "Unnamed"
  if (nodeName === "Unnamed" && level === 0) {
    console.warn("Root node is Unnamed, raw node:", node);
  }
  const hasChildren = node.children && node.children.length > 0;
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
        }`}
        style={{
          paddingLeft: `${level * 16}px`,
          cursor: isVariable ? "grab" : "default",
        }}
        draggable={!!isDraggable}
        onDragStart={(e) => {
          if (isDraggable && nodeNamespace) {
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
        onClick={() => {
          if (hasChildren) {
            setIsExpanded(!isExpanded);
          }
          if (isVariable) {
            onSelect(client, node);
          }
        }}
        onDoubleClick={() => {
          if (hasChildren) {
            setIsExpanded(!isExpanded);
          }
        }}
      >
        {hasChildren && (
          <i
            className={`bi ${isExpanded ? "bi-chevron-down" : "bi-chevron-right"} text-muted`}
            style={{ fontSize: "0.75rem", width: "16px", cursor: "pointer" }}
            onClick={(e) => {
              e.stopPropagation();
              setIsExpanded(!isExpanded);
            }}
          />
        )}
        {!hasChildren && <span style={{ width: "16px", display: "inline-block" }} />}
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
      {hasChildren && isExpanded && (
        <ul className="nav flex-column" style={{ listStyle: "none", marginLeft: "8px" }}>
          {node.children!.map((child, idx) => (
            <TreeNode
              key={`${nodeNamespace || nodeName}-${idx}`}
              node={child}
              client={client}
              onSelect={onSelect}
              level={level + 1}
            />
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
  const [clients, setClients] = useState<string[]>([]);
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
  const [selectedNodes, setSelectedNodes] = useState<SelectedNode[]>(() => {
    // Cargar nodos seleccionados previamente desde localStorage
    return loadSelectedNodes();
  });
  const [polling, setPolling] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const namespacesToPoll = useMemo(
    () => selectedNodes.map((n) => n.namespace),
    [selectedNodes]
  );

  const loadClients = async () => {
    setLoadingClients(true);
    try {
      setError(null);
      const list = await listClients();
      const names: string[] = list.map((c) => (typeof c === "string" ? c : c.name || "")).filter(Boolean);
      setClients(names);
      
      // Si hay clientes disponibles
      if (names.length > 0) {
        // Si hay un cliente guardado y está en la lista, usarlo
        const savedClient = localStorage.getItem(SELECTED_CLIENT_STORAGE_KEY);
        if (savedClient && names.includes(savedClient)) {
          setSelectedClient(savedClient);
        } else if (!selectedClient) {
          // Si no hay cliente seleccionado, usar el primero
          const firstClient = names[0];
          setSelectedClient(firstClient);
          localStorage.setItem(SELECTED_CLIENT_STORAGE_KEY, firstClient);
        }
      } else {
        // Si no hay clientes, limpiar selección
        setSelectedClient("");
        localStorage.removeItem(SELECTED_CLIENT_STORAGE_KEY);
      }
    } catch (e: any) {
      const errorMsg = e?.response?.data?.message || e?.message || "Error al obtener clientes OPC UA";
      setError(errorMsg);
      setClients([]);
      setSelectedClient("");
      localStorage.removeItem(SELECTED_CLIENT_STORAGE_KEY);
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
      const t = await getClientTree(clientName);
      console.log("Tree loaded:", t);
      // Asegurarnos de que sea un array
      const treeArray = Array.isArray(t) ? t : t ? [t] : [];
      console.log("Tree array to set:", treeArray);
      setTree(treeArray);
    } catch (e: any) {
      const errorMsg = e?.response?.data?.message || e?.message || "No se pudo obtener el árbol OPC UA";
      setError(errorMsg);
      setTree([]);
      console.error("Error loading tree:", e);
    } finally {
      setLoadingTree(false);
    }
  };

  // Cargar clientes al montar el componente
  useEffect(() => {
    loadClients();
  }, []);

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
  }, [selectedClient]);

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
    const raw = e.dataTransfer.getData("application/opcua-node");
    if (!raw) return;
    try {
      const { client, namespace, displayName } = JSON.parse(raw);
      if (!namespace || !client) return;
      
      // Verificar que no esté ya en la lista
      setSelectedNodes((prev) => {
        if (prev.some((p) => p.namespace === namespace)) return prev;
        
        // Agregar el nodo inicialmente sin datos
        const newNode: SelectedNode = { client, namespace, displayName };
        const newList = [...prev, newNode];
        
        // Guardar inmediatamente en localStorage
        saveSelectedNodes(newList);
        
        // Obtener atributos del nodo para tener información completa inicial
        getNodeAttributes(client, [namespace])
          .then((attrs) => {
            if (attrs && attrs.length > 0) {
              const attr = attrs[0];
              // Extraer información de DataValue si existe
              const dataValue = attr.DataValue;
              setSelectedNodes((current) => {
                const updated = current.map((n) =>
                  n.namespace === namespace
                    ? {
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
                      }
                    : n
                );
                // Guardar después de actualizar con atributos
                saveSelectedNodes(updated);
                return updated;
              });
            }
          })
          .catch((err) => {
            console.debug("Error obteniendo atributos iniciales:", err);
          });
        
        return newList;
      });
    } catch (_e) {
      console.error("Error al procesar nodo arrastrado:", _e);
    }
  };

  const handleAddClient = async () => {
    if (!form.name || !form.host || !form.port) {
      setError("Por favor complete todos los campos requeridos");
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
      const errorMsg = e?.response?.data?.message || e?.message || "No se pudo crear el cliente";
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
      const errorMsg = e?.response?.data?.message || e?.message || "No se pudo eliminar el cliente";
      setError(errorMsg);
    }
  };

  return (
    <div className="row">
      <div className="col-lg-4">
        <Card
          title="Clientes OPC UA"
          footer={
            <div className="d-flex gap-2">
              <Button variant="primary" onClick={handleAddClient}>
                Crear
              </Button>
              <Button
                variant="danger"
                onClick={() => selectedClient && handleRemoveClient(selectedClient)}
                disabled={!selectedClient}
              >
                Remover
              </Button>
            </div>
          }
        >
          <div className="mb-2">
            <label className="form-label mb-1">Cliente seleccionado</label>
            <select
              className="form-select"
              value={selectedClient}
              onChange={(e) => setSelectedClient(e.target.value)}
              disabled={loadingClients}
            >
              <option value="">{loadingClients ? "Cargando..." : "Seleccione cliente"}</option>
              {clients.map((c) => (
                <option key={c} value={c}>
                  {c}
                </option>
              ))}
            </select>
          </div>
          <div className="row g-2">
            <div className="col-12 col-md-4">
              <input
                className="form-control"
                placeholder="Nombre"
                value={form.name}
                onChange={(e) => setForm((p) => ({ ...p, name: e.target.value }))}
              />
            </div>
            <div className="col-12 col-md-5">
              <input
                className="form-control"
                placeholder="Host"
                value={form.host}
                onChange={(e) => setForm((p) => ({ ...p, host: e.target.value }))}
              />
            </div>
            <div className="col-12 col-md-3">
              <input
                className="form-control"
                placeholder="Puerto"
                type="number"
                value={form.port}
                onChange={(e) => setForm((p) => ({ ...p, port: Number(e.target.value) }))}
              />
            </div>
          </div>
          {error && <div className="alert alert-danger mt-2 mb-0 py-2">{error}</div>}
        </Card>

        <Card title={`Explorador OPC UA ${selectedClient ? `(${selectedClient})` : ""}`}>
          {!selectedClient && (
            <div className="text-muted">Seleccione un cliente para ver el árbol de nodos</div>
          )}
          {selectedClient && loadingTree && (
            <div className="text-muted">
              <div className="spinner-border spinner-border-sm me-2" role="status">
                <span className="visually-hidden">Cargando...</span>
              </div>
              Cargando árbol...
            </div>
          )}
          {selectedClient && !loadingTree && tree.length === 0 && (
            <div className="text-muted">Sin nodos disponibles</div>
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
                      level={0}
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
          title="Tags seleccionados"
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
                  Polling cada 1s
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
                Limpiar
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
              Arrastra nodos desde el árbol OPC UA para monitorearlos.
            </div>
            {selectedNodes.length === 0 && (
              <div className="text-muted">Sin nodos seleccionados.</div>
            )}
            {selectedNodes.length > 0 && (
              <div className="table-responsive">
                <table className="table table-sm align-middle mb-0">
                  <thead>
                    <tr>
                      <th>Namespace</th>
                      <th>Display Name</th>
                      <th>Valor</th>
                      <th>Timestamp</th>
                      <th>Estado</th>
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
                            Quitar
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
