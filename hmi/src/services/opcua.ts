import api from "./api";

export type OpcUaClient = {
  name: string;
  host?: string;
  port?: number;
  server_url?: string;
  is_opened?: boolean;
  client_id?: string;
};

export type OpcUaTreeNode = {
  name?: string;
  title?: string;
  namespace?: string;
  key?: string;
  NodeClass?: string;
  children?: OpcUaTreeNode[];
  has_children?: boolean;
  value?: any;
};

export type OpcUaTreeFetchOptions = {
  mode?: "generic" | "legacy";
  max_depth?: number;
  max_nodes?: number;
  include_properties?: boolean;
  include_property_values?: boolean;
  /**
   * Timeout por request (ms). Por defecto, el árbol puede tardar más que el timeout global del API (15s).
   */
  timeout_ms?: number;
  /**
   * Si true, y el modo generic retorna vacío o falla, intenta automáticamente legacy.
   */
  fallback_to_legacy?: boolean;
};

export type OpcUaNodeValue = {
  namespace: string;
  value: any;
  source_timestamp?: string | null;
  status_code?: string | null;
};

export type OpcUaNodeAttribute = {
  Namespace?: string;
  namespace?: string;
  DisplayName?: string;
  displayName?: string;
  display_name?: string;
  Value?: any;
  value?: any;
  DataType?: string;
  data_type?: string;
  Description?: string;
  description?: string;
  SourceTimestamp?: string;
  source_timestamp?: string;
  ServerTimestamp?: string;
  StatusCode?: string;
  status_code?: string;
  DataValue?: {
    Value?: any;
    SourceTimestamp?: string;
    ServerTimestamp?: string;
    StatusCode?: string;
  };
  [key: string]: any; // Permitir propiedades adicionales
};

/**
 * Lista todos los clientes OPC UA configurados
 */
export const listClients = async (): Promise<OpcUaClient[]> => {
  const { data } = await api.get("/opcua/clients/");
  // El endpoint retorna un objeto con las claves siendo los nombres de los clientes
  if (typeof data === "object" && data !== null && !Array.isArray(data)) {
    return Object.entries(data).map(([name, client]: [string, any]) => ({
      name,
      ...client,
    }));
  }
  return Array.isArray(data) ? data : [];
};

/**
 * Normaliza un nodo del árbol OPC UA a la estructura esperada
 */
const normalizeTreeNode = (node: any): OpcUaTreeNode => {
  if (!node || typeof node !== "object") {
    return { name: "Invalid Node", namespace: "", NodeClass: "" };
  }
  
  const normalized: OpcUaTreeNode = {
    name: node.name || node.title || "Unnamed",
    namespace: node.namespace || node.key || "",
    NodeClass: node.NodeClass || node.nodeClass || "",
    has_children: typeof node.has_children === "boolean" ? node.has_children : undefined,
    value: node.value,
    children: node.children && Array.isArray(node.children) && node.children.length > 0
      ? node.children.map((child: any) => normalizeTreeNode(child))
      : undefined,
  };
  
  return normalized;
};

/**
 * Obtiene el árbol de nodos de un cliente OPC UA
 */
export const getClientTree = async (clientName: string): Promise<OpcUaTreeNode[]> => {
  return getClientTreeWithOptions(clientName);
};

/**
 * Obtiene el árbol de nodos de un cliente OPC UA con opciones de browse.
 * Importante: para servidores grandes, usar max_depth/max_nodes para evitar congelar la UI.
 */
export const getClientTreeWithOptions = async (
  clientName: string,
  options: OpcUaTreeFetchOptions = {}
): Promise<OpcUaTreeNode[]> => {
  try {
    const mode = options.mode ?? "generic";
    const params = new URLSearchParams();
    params.set("mode", mode);
    if (typeof options.max_depth === "number") params.set("max_depth", String(options.max_depth));
    if (typeof options.max_nodes === "number") params.set("max_nodes", String(options.max_nodes));
    if (typeof options.include_properties === "boolean") params.set("include_properties", String(options.include_properties));
    if (typeof options.include_property_values === "boolean") params.set("include_property_values", String(options.include_property_values));

    const qs = params.toString();
    const url = `/opcua/clients/tree/${encodeURIComponent(clientName)}${qs ? `?${qs}` : ""}`;

    const { data } = await api.get(url, { timeout: options.timeout_ms ?? 60_000 });
    
    // El backend retorna una tupla [objeto, 200] que axios recibe como array
    // Necesitamos extraer el primer elemento si es una tupla
    let treeData = data;
    if (Array.isArray(data) && data.length === 2 && typeof data[1] === "number") {
      // Es una tupla [objeto, código_http]
      treeData = data[0];
    }
    
    // Validar que treeData sea un objeto válido
    if (!treeData || typeof treeData !== "object" || Array.isArray(treeData)) {
      console.warn("Invalid tree data (not an object):", treeData);
      return [];
    }
    
    // El endpoint retorna { Objects: [...] } según el backend
    // PRIORIDAD: Verificar Objects primero antes de otras estructuras
    if (treeData.Objects && Array.isArray(treeData.Objects) && treeData.Objects.length > 0) {
      const normalized = treeData.Objects.map(normalizeTreeNode);
      return normalized;
    }
    
    // Si es un objeto simple con name/namespace o title/key (nodo único)
    if (treeData.name || treeData.title) {
      return [normalizeTreeNode(treeData)];
    }
    
    // Si generic no devolvió nada útil, intentar legacy como fallback (si está habilitado)
    const shouldFallback = options.fallback_to_legacy !== false && mode === "generic";
    if (shouldFallback) {
      console.warn("No valid tree structure found (generic). Falling back to legacy. Data:", treeData);
      return await getClientTreeWithOptions(clientName, { ...options, mode: "legacy", fallback_to_legacy: false });
    }

    console.warn("No valid tree structure found in data:", treeData);
    return [];
  } catch (error) {
    // fallback a legacy si falla el modo generic
    const mode = options.mode ?? "generic";
    const shouldFallback = options.fallback_to_legacy !== false && mode === "generic";
    if (shouldFallback) {
      console.warn("Error fetching tree (generic). Falling back to legacy.", error);
      return await getClientTreeWithOptions(clientName, { ...options, mode: "legacy", fallback_to_legacy: false });
    }
    console.error("Error fetching tree:", error);
    throw error;
  }
};

/**
 * Obtiene los hijos directos de un nodo (lazy-loading) para expandir ramas profundas.
 */
export const getClientTreeChildrenWithOptions = async (
  clientName: string,
  nodeId: string,
  options: OpcUaTreeFetchOptions & { max_nodes?: number } = {}
): Promise<OpcUaTreeNode[]> => {
  const mode = options.mode ?? "generic";
  const params = new URLSearchParams();
  params.set("mode", mode);
  params.set("node_id", nodeId);
  if (typeof options.max_nodes === "number") params.set("max_nodes", String(options.max_nodes));
  if (typeof options.include_properties === "boolean") params.set("include_properties", String(options.include_properties));
  if (typeof options.include_property_values === "boolean") params.set("include_property_values", String(options.include_property_values));
  if (typeof options.fallback_to_legacy === "boolean") params.set("fallback_to_legacy", String(options.fallback_to_legacy));

  const qs = params.toString();
  const url = `/opcua/clients/tree_children/${encodeURIComponent(clientName)}?${qs}`;
  const { data } = await api.get(url, { timeout: options.timeout_ms ?? 60_000 });

  let payload = data;
  if (Array.isArray(data) && data.length === 2 && typeof data[1] === "number") {
    payload = data[0];
  }

  const children = payload?.children;
  if (Array.isArray(children)) {
    return children.map(normalizeTreeNode);
  }
  return [];
};

/**
 * Agrega un nuevo cliente OPC UA
 */
export const addClient = async (client: { name: string; host: string; port: number }) => {
  const { data } = await api.post("/opcua/clients/add", {
    client_name: client.name,
    host: client.host,  
    port: client.port,
  });
  return data;
};

/**
 * Remueve un cliente OPC UA
 */
export const removeClient = async (clientName: string) => {
  const { data } = await api.delete(
    `/opcua/clients/remove/${encodeURIComponent(clientName)}`
  );
  return data;
};

/**
 * Actualiza la configuración de un cliente OPC UA
 * Todos los parámetros excepto oldClientName son opcionales
 */
export const updateClient = async (
  oldClientName: string,
  newClientName?: string,
  host?: string,
  port?: number
) => {
  const payload: any = {};
  if (newClientName !== undefined && newClientName !== null && newClientName !== "") {
    payload.new_client_name = newClientName;
  }
  if (host !== undefined && host !== null && host !== "") {
    payload.host = host;
  }
  if (port !== undefined && port !== null && port > 0) {
    payload.port = port;
  }
  
  const { data } = await api.put(
    `/opcua/clients/update/${encodeURIComponent(oldClientName)}`,
    payload
  );
  return data;
};

/**
 * Obtiene los valores de múltiples nodos OPC UA
 */
export const getNodeValues = async (
  clientName: string,
  namespaces: string[]
): Promise<OpcUaNodeValue[]> => {
  const { data } = await api.post(`/opcua/clients/values/${encodeURIComponent(clientName)}`, {
    namespaces,
  });
  
  // El endpoint retorna { data: [...] } donde cada elemento puede ser un objeto con Namespace y Value
  const values = data?.data ?? [];
  
  return values.map((item: any, index: number) => {
    // Normalizar la estructura de respuesta
    if (typeof item === "object" && item !== null) {
      // Si el item tiene Namespace y Value (estructura del backend)
      if (item.Namespace !== undefined) {
        return {
          namespace: item.Namespace || "",
          value: item.Value ?? null,
          source_timestamp: item.SourceTimestamp ?? null,
          status_code: item.StatusCode ?? null,
        };
      }
      // Si tiene namespace y value (estructura normalizada)
      return {
        namespace: item.namespace || "",
        value: item.value ?? null,
        source_timestamp: item.source_timestamp ?? null,
        status_code: item.status_code ?? null,
      };
    }
    // Si es un valor primitivo, necesitamos el namespace del array original
    // En este caso, usamos el índice para mapear con el namespace correspondiente
    return {
      namespace: namespaces[index] || "",
      value: item,
      source_timestamp: null,
      status_code: null,
    };
  });
};

/**
 * Obtiene los atributos de múltiples nodos OPC UA
 */
export const getNodeAttributes = async (
  clientName: string,
  namespaces: string[]
): Promise<OpcUaNodeAttribute[]> => {
  const { data } = await api.post(
    `/opcua/clients/attrs/${encodeURIComponent(clientName)}`,
    {
      namespaces,
    }
  );
  
  // El endpoint retorna { data: [...] } con los atributos serializados
  return data?.data ?? [];
};

// OPC UA Server types
export type OpcUaServerAttribute = {
  name: string;
  namespace: string;
  access_type: "Read" | "Write" | "ReadWrite";
};

export type OpcUaServerAttributesResponse = {
  data: OpcUaServerAttribute[];
};

/**
 * Obtiene todos los atributos del OPC UA Server
 */
export const getOpcUaServerAttributes = async (): Promise<OpcUaServerAttribute[]> => {
  const { data } = await api.get("/opcua/server/attrs");
  return data?.data ?? [];
};

/**
 * Actualiza el tipo de acceso de un nodo del OPC UA Server
 */
export const updateOpcUaServerAccessType = async (
  namespace: string,
  access_type: "Read" | "Write" | "ReadWrite",
  name?: string
): Promise<{ message: string; namespace: string; access_type: string }> => {
  const { data } = await api.put("/opcua/server/attrs/update", {
    namespace,
    access_type,
    name,
  });
  return data;
};


