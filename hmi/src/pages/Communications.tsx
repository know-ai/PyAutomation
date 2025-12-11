import { useEffect, useMemo, useState } from "react";
import { Card } from "../components/Card";
import { Button } from "../components/Button";
import {
  addClient,
  getClientTree,
  getNodeValues,
  listClients,
  removeClient,
  type OpcUaTreeNode,
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
}: {
  node: OpcUaTreeNode;
  client: string;
  onSelect: (client: string, node: OpcUaTreeNode) => void;
}) {
  return (
    <li
      className="nav-item"
      draggable
      onDragStart={(e) => {
        e.dataTransfer.setData(
          "application/opcua-node",
          JSON.stringify({ client, namespace: node.namespace, displayName: node.name })
        );
      }}
      onClick={() => onSelect(client, node)}
    >
      <span className="nav-link d-flex align-items-center gap-2 py-1 px-2">
        <i className="nav-icon bi bi-node-plus" />
        <span>{node.name}</span>
      </span>
      {node.children && node.children.length > 0 && (
        <ul className="nav flex-column ms-3 border-start ps-2">
          {node.children.map((child, idx) => (
            <TreeNode key={`${node.name}-${idx}`} node={child} client={client} onSelect={onSelect} />
          ))}
        </ul>
      )}
    </li>
  );
}

export function Communications() {
  const [clients, setClients] = useState<string[]>([]);
  const [selectedClient, setSelectedClient] = useState<string>("");
  const [tree, setTree] = useState<OpcUaTreeNode[]>([]);
  const [loadingTree, setLoadingTree] = useState(false);
  const [form, setForm] = useState({ name: "", host: "127.0.0.1", port: 4840 });
  const [selectedNodes, setSelectedNodes] = useState<SelectedNode[]>([]);
  const [polling, setPolling] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const namespacesToPoll = useMemo(
    () => selectedNodes.map((n) => n.namespace),
    [selectedNodes]
  );

  const loadClients = async () => {
    try {
      const list = await listClients();
      const names = list.map((c) => c.name);
      setClients(names);
      if (!selectedClient && names.length) setSelectedClient(names[0]);
    } catch (e: any) {
      setError(e?.message || "Error al obtener clientes OPC UA");
    }
  };

  const loadTree = async (clientName: string) => {
    setLoadingTree(true);
    setError(null);
    try {
      const t = await getClientTree(clientName);
      setTree(t || []);
    } catch (e: any) {
      setError(e?.message || "No se pudo obtener el árbol OPC UA");
      setTree([]);
    } finally {
      setLoadingTree(false);
    }
  };

  useEffect(() => {
    loadClients();
  }, []);

  useEffect(() => {
    if (selectedClient) loadTree(selectedClient);
  }, [selectedClient]);

  // Polling de valores cada segundo
  useEffect(() => {
    if (!polling || !selectedClient || namespacesToPoll.length === 0) return;
    const id = setInterval(async () => {
      try {
        const values = await getNodeValues(selectedClient, namespacesToPoll);
        setSelectedNodes((prev) =>
          prev.map((n) => {
            const match = values.find((v) => v.namespace === n.namespace);
            if (!match) return n;
            return {
              ...n,
              lastValue: match.value,
              lastTimestamp: match.source_timestamp,
              status: match.status_code,
            };
          })
        );
      } catch (_e) {
        // silencioso: evitamos spam
      }
    }, 1000);
    return () => clearInterval(id);
  }, [polling, selectedClient, namespacesToPoll]);

  const onDropNode = (e: React.DragEvent<HTMLDivElement>) => {
    const raw = e.dataTransfer.getData("application/opcua-node");
    if (!raw) return;
    try {
      const { client, namespace, displayName } = JSON.parse(raw);
      if (!namespace) return;
      setSelectedNodes((prev) => {
        if (prev.some((p) => p.namespace === namespace)) return prev;
        return [...prev, { client, namespace, displayName }];
      });
    } catch (_e) {
      // ignore
    }
  };

  const handleAddClient = async () => {
    if (!form.name || !form.host || !form.port) return;
    try {
      await addClient({ name: form.name, host: form.host, port: Number(form.port) });
      setForm({ ...form, name: "" });
      await loadClients();
      setSelectedClient(form.name);
    } catch (e: any) {
      setError(e?.message || "No se pudo crear el cliente");
    }
  };

  const handleRemoveClient = async (clientName: string) => {
    try {
      await removeClient(clientName);
      await loadClients();
      if (clientName === selectedClient) {
        setSelectedClient(clients.find((c) => c !== clientName) || "");
        setTree([]);
        setSelectedNodes([]);
      }
    } catch (e: any) {
      setError(e?.message || "No se pudo eliminar el cliente");
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
            >
              <option value="">Seleccione cliente</option>
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
          {loadingTree && <div className="text-muted">Cargando árbol...</div>}
          {!loadingTree && tree.length === 0 && <div className="text-muted">Sin nodos</div>}
          {!loadingTree && tree.length > 0 && (
            <ul className="nav flex-column" style={{ maxHeight: 420, overflow: "auto" }}>
              {tree.map((node, idx) => (
                <TreeNode key={idx} node={node} client={selectedClient} onSelect={() => {}} />
              ))}
            </ul>
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
                onClick={() => setSelectedNodes([])}
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
                        <td className="text-truncate" style={{ maxWidth: 140 }}>
                          {n.namespace}
                        </td>
                        <td>{n.displayName}</td>
                        <td>{n.lastValue ?? <span className="text-muted">-</span>}</td>
                        <td className="text-truncate" style={{ maxWidth: 160 }}>
                          {n.lastTimestamp ?? <span className="text-muted">-</span>}
                        </td>
                        <td>{n.status ?? <span className="text-muted">-</span>}</td>
                        <td>
                          <Button
                            variant="danger"
                            className="btn-sm"
                            onClick={() =>
                              setSelectedNodes((prev) =>
                                prev.filter((p) => p.namespace !== n.namespace)
                              )
                            }
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
