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
  try {
    const { data } = await api.get(`/opcua/clients/tree/${encodeURIComponent(clientName)}`);
    
    // Debug: log para ver qué estructura recibimos
    console.log("Raw tree data:", data);
    
    // El backend retorna una tupla [objeto, 200] que axios recibe como array
    // Necesitamos extraer el primer elemento si es una tupla
    let treeData = data;
    if (Array.isArray(data) && data.length === 2 && typeof data[1] === "number") {
      // Es una tupla [objeto, código_http]
      treeData = data[0];
      console.log("Extracted from tuple:", treeData);
    }
    
    // Validar que treeData sea un objeto válido
    if (!treeData || typeof treeData !== "object" || Array.isArray(treeData)) {
      console.warn("Invalid tree data (not an object):", treeData);
      return [];
    }
    
    // El endpoint retorna { Objects: [...] } según el backend
    // PRIORIDAD: Verificar Objects primero antes de otras estructuras
    if (treeData.Objects && Array.isArray(treeData.Objects) && treeData.Objects.length > 0) {
      console.log("Found Objects array with", treeData.Objects.length, "items");
      const normalized = treeData.Objects.map(normalizeTreeNode);
      console.log("Normalized Objects:", normalized);
      return normalized;
    }
    
    // Si es un objeto simple con name/namespace o title/key (nodo único)
    if (treeData.name || treeData.title) {
      return [normalizeTreeNode(treeData)];
    }
    
    console.warn("No valid tree structure found in data:", treeData);
    return [];
  } catch (error) {
    console.error("Error fetching tree:", error);
    throw error;
  }
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


