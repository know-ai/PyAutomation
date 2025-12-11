import api from "./api";

export type OpcUaClient = {
  name: string;
  host?: string;
  port?: number;
};

export type OpcUaTreeNode = {
  name: string;
  namespace?: string;
  children?: OpcUaTreeNode[];
};

export type OpcUaNodeValue = {
  namespace: string;
  display_name: string;
  value: any;
  source_timestamp?: string;
  status_code?: string;
};

// Nota: los endpoints pueden ajustarse a los disponibles en el backend.
// Se dejaron rutas convencionales; si difieren, solo actualiza las URLs.

export const listClients = async (): Promise<OpcUaClient[]> => {
  const { data } = await api.get("/opcua/clients");
  return data?.clients ?? data ?? [];
};

export const getClientTree = async (clientName: string): Promise<OpcUaTreeNode[]> => {
  const { data } = await api.get("/opcua/tree", {
    params: { client_name: clientName },
  });
  return data?.tree ?? data ?? [];
};

export const addClient = async (client: { name: string; host: string; port: number }) => {
  const { data } = await api.post("/opcua/clients", client);
  return data;
};

export const removeClient = async (clientName: string) => {
  const { data } = await api.delete(`/opcua/clients/${encodeURIComponent(clientName)}`);
  return data;
};

export const getNodeValues = async (
  clientName: string,
  namespaces: string[]
): Promise<OpcUaNodeValue[]> => {
  const { data } = await api.post("/opcua/nodes/values", {
    client_name: clientName,
    namespaces,
  });
  return data?.values ?? data ?? [];
};


