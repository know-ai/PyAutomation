import api from "./api";

export type GeospatialPoint = {
  id: number;
  segment_name: string;
  kp: number;
  latitude: number;
  longitude: number;
  elevation: number | null;
};

export type GeospatialPointInput = {
  segment_name: string;
  kp: number;
  latitude: number;
  longitude: number;
};

export type GeospatialImportResult = {
  created: number;
  updated: number;
  skipped: number;
  errors: string[];
  processed: number;
  success: boolean;
};

const BASE = "/linear-referencing-geospatial";

function asNumber(value: unknown): number {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : Number.NaN;
}

function normalizePoint(raw: Record<string, unknown>): GeospatialPoint {
  const elevation = raw.elevation;
  return {
    id: asNumber(raw.id),
    segment_name: String(raw.segment_name ?? raw.segment ?? ""),
    kp: asNumber(raw.kp),
    latitude: asNumber(raw.latitude),
    longitude: asNumber(raw.longitude),
    elevation: elevation == null || elevation === "" ? null : asNumber(elevation),
  };
}

export async function listGeospatialPoints(segmentName?: string): Promise<GeospatialPoint[]> {
  const { data } = await api.get(`${BASE}/`, {
    params: segmentName ? { segment_name: segmentName } : undefined,
  });
  const rows = Array.isArray(data?.data) ? data.data : [];
  return rows.map((row: Record<string, unknown>) => normalizePoint(row));
}

export async function createGeospatialPoint(payload: GeospatialPointInput): Promise<GeospatialPoint> {
  const { data } = await api.post(`${BASE}/add`, payload);
  return normalizePoint(data?.data ?? {});
}

export async function updateGeospatialPoint(
  id: number,
  payload: GeospatialPointInput,
): Promise<GeospatialPoint> {
  const { data } = await api.put(`${BASE}/${id}`, payload);
  return normalizePoint(data?.data ?? {});
}

export async function deleteGeospatialPoint(id: number): Promise<void> {
  await api.delete(`${BASE}/${id}`);
}

export async function importGeospatialCsv(file: File): Promise<GeospatialImportResult> {
  const form = new FormData();
  form.append("file", file);
  form.append("update_existing", "true");
  const { data } = await api.post(`${BASE}/bulk_import`, form, {
    headers: { "Content-Type": "multipart/form-data" },
  });
  const body = data?.data ?? {};
  return {
    created: Number(body.created ?? 0),
    updated: Number(body.updated ?? 0),
    skipped: Number(body.skipped ?? 0),
    errors: Array.isArray(body.errors) ? body.errors.map(String) : [],
    processed: Number(body.processed ?? 0),
    success: Boolean(body.success),
  };
}
