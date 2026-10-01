import api from "./api";
import { DEFAULT_SUMMARY_COLUMNS } from "../utils/machinesSummaryColumns";

export async function getMachinesSummaryColumns(): Promise<string[]> {
  const { data } = await api.get("/settings/workspace/machines-summary");
  const columns = data?.columns;
  if (!Array.isArray(columns)) return [...DEFAULT_SUMMARY_COLUMNS];
  return columns.filter((item: unknown): item is string => typeof item === "string");
}

export async function putMachinesSummaryColumns(columns: string[]): Promise<string[]> {
  const { data } = await api.put("/settings/workspace/machines-summary", { columns });
  const saved = data?.columns;
  if (!Array.isArray(saved)) return columns;
  return saved.filter((item: unknown): item is string => typeof item === "string");
}
