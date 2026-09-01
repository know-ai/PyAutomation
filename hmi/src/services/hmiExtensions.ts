import api from "./api";

export type HmiMenuItem = {
  id: string;
  path: string;
  label_key: string;
  icon: string;
  priority: number;
};

export async function listHmiExtensions(): Promise<HmiMenuItem[]> {
  const { data } = await api.get("/hmi/extensions", { timeout: 4000 });
  const items = Array.isArray(data?.items) ? data.items : [];
  return items.filter((row: HmiMenuItem) => row && row.path && row.id);
}
