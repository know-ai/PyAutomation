import api from "./api";

export type WorkerState = "alive" | "inactive" | "error" | "restarting" | string;

export type WorkerStatus = {
  name?: string;
  state?: WorkerState;
  last_cycle_utc?: string | null;
};

export type OpsActionResult = {
  ok?: boolean;
  message?: string;
  replicated?: number;
  dropped?: number;
  ensured?: number;
  removed?: number;
  accepted?: boolean;
  worker?: string;
  WORKERS?: Record<string, WorkerStatus>;
};

export async function restartWorker(name: string, reason?: string): Promise<OpsActionResult> {
  const { data } = await api.post(
    "/admin/workers/restart",
    { name, reason },
    { params: { name }, timeout: 20000 }
  );
  return data as OpsActionResult;
}

export async function retrySaf(reason?: string): Promise<OpsActionResult> {
  const { data } = await api.post("/admin/saf/retry", { reason }, { timeout: 20000 });
  return data as OpsActionResult;
}

export async function resetSaf(reason?: string): Promise<OpsActionResult> {
  const { data } = await api.post("/admin/saf/reset", { confirm: true, reason }, { timeout: 20000 });
  return data as OpsActionResult;
}

export async function syncCatalog(reason?: string): Promise<OpsActionResult> {
  const { data } = await api.post("/admin/catalog/sync", { reason }, { timeout: 20000 });
  return data as OpsActionResult;
}

export async function cleanCatalogOrphans(ageMinutes: number, reason?: string): Promise<OpsActionResult> {
  const { data } = await api.post(
    "/admin/catalog/clean-orphans",
    { age_minutes: ageMinutes, reason },
    { timeout: 20000 }
  );
  return data as OpsActionResult;
}

export async function rebuildDerivedTags(reason?: string): Promise<OpsActionResult> {
  const { data } = await api.post("/admin/tags/rebuild-derived", { reason }, { timeout: 30000 });
  return data as OpsActionResult;
}
