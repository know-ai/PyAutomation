import type { AxiosRequestConfig } from "axios";
import api from "./api";
import type { TagHistoryPoint } from "../store/slices/tagsSlice";

export type BackfillResponse = {
  data: Record<string, TagHistoryPoint[]>;
};

/**
 * GET /history/backfill — raw TagValue samples as ISO UTC (matches on.tag).
 */
export async function getHistoryBackfill(
  tags: string[],
  fromMs: number,
  toMs: number,
  options?: { limit?: number; signal?: AbortSignal }
): Promise<Record<string, TagHistoryPoint[]>> {
  if (tags.length === 0 || !(toMs > fromMs)) {
    return {};
  }
  const config: AxiosRequestConfig = {
    params: {
      tags: tags.join(","),
      from: Math.trunc(fromMs),
      to: Math.trunc(toMs),
      limit: options?.limit ?? 1000,
    },
    signal: options?.signal,
  };
  const { data } = await api.get<BackfillResponse>("/history/backfill", config);
  const payload = data?.data;
  if (!payload || typeof payload !== "object") {
    return {};
  }
  const out: Record<string, TagHistoryPoint[]> = {};
  for (const [name, points] of Object.entries(payload)) {
    if (!Array.isArray(points) || !name) continue;
    const cleaned: TagHistoryPoint[] = [];
    for (const pt of points) {
      if (!pt || typeof pt !== "object") continue;
      const timestamp = typeof pt.timestamp === "string" ? pt.timestamp : "";
      const value = typeof pt.value === "number" ? pt.value : Number(pt.value);
      if (!timestamp || !Number.isFinite(value)) continue;
      cleaned.push({ timestamp, value });
    }
    if (cleaned.length > 0) out[name] = cleaned;
  }
  return out;
}
