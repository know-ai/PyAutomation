import api from "./api";

export type Machine = {
  state: string;
  actions: string[];
  manufacturer: string | null;
  segment: string | null;
  identifier: string;
  criticity: number;
  priority: number;
  description: string;
  classification: string;
  name: string;
  machine_interval: number;
  buffer_size: number;
  buffer_roll_type: string;
  [key: string]: any;
};

export type MachinesResponse = {
  data: Machine[];
};

/**
 * Obtiene todas las máquinas de estado
 */
export const getMachines = async (): Promise<Machine[]> => {
  const { data } = await api.get("/machines/");
  return data?.data ?? [];
};

/**
 * Obtiene información detallada de una máquina por nombre
 */
export const getMachineByName = async (machineName: string): Promise<any> => {
  const { data } = await api.get(`/machines/${encodeURIComponent(machineName)}`);
  return data?.data;
};

/**
 * Actualiza el intervalo de ejecución de una máquina
 */
export const updateMachineInterval = async (
  machineName: string,
  interval: number
): Promise<{ message: string; data: Machine }> => {
  const { data } = await api.put(`/machines/${encodeURIComponent(machineName)}`, {
    interval,
  });
  return data;
};

/**
 * Ejecuta una transición de estado en una máquina
 */
export const transitionMachine = async (
  machineName: string,
  to: string
): Promise<{ message: string; data: Machine }> => {
  const { data } = await api.put(`/machines/${encodeURIComponent(machineName)}/transition`, {
    to,
  });
  return data;
};

/**
 * Suscribe un tag de campo a una variable interna de la máquina
 */
export const subscribeMachineTag = async (
  machineName: string,
  fieldTag: string,
  internalTag: string
): Promise<{ message: string; data: Machine }> => {
  const { data } = await api.post(
    `/machines/${encodeURIComponent(machineName)}/subscribe`,
    {
      field_tag: fieldTag,
      internal_tag: internalTag,
    }
  );
  return data;
};

/**
 * Desuscribe un tag previamente suscrito de la máquina
 */
export const unsubscribeMachineTag = async (
  machineName: string,
  tagName: string
): Promise<{ message: string; data: Machine }> => {
  const { data } = await api.post(
    `/machines/${encodeURIComponent(machineName)}/unsubscribe`,
    {
      tag_name: tagName,
    }
  );
  return data;
};

