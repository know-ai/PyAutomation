import api from "./api";

export type AuthzActionsMap = Record<string, string[]>;

export type AuthzMe = {
  views: AuthzActionsMap;
  rest: AuthzActionsMap;
  username?: string;
  role?: string;
  is_system?: boolean;
};

export type AuthzGrant = {
  subject_type: string;
  subject_id: string;
  resource_key: string;
  action: string;
  effect: string;
};

export type AuthzCatalog = {
  hmi: Record<string, Array<{ resource_key: string; path?: string; kind: string; actions: string[] }>>;
  rest: Record<string, Array<{ resource_key: string; kind: string; actions: string[] }>>;
  actions: string[];
  effects: string[];
};

export async function getAuthzMe(): Promise<AuthzMe> {
  const { data } = await api.get("/authz/me");
  return {
    views: data?.views || {},
    rest: data?.rest || {},
    username: data?.username,
    role: data?.role,
    is_system: Boolean(data?.is_system),
  };
}

export async function getAuthzCatalog(): Promise<AuthzCatalog> {
  const { data } = await api.get("/authz/catalog");
  return data;
}

export async function getAuthzGrants(subjectType: string, subjectId: string): Promise<AuthzGrant[]> {
  const { data } = await api.get("/authz/grants", {
    params: { subject_type: subjectType, subject_id: subjectId },
  });
  return Array.isArray(data?.data) ? data.data : [];
}

export async function putAuthzGrants(
  subjectType: string,
  subjectId: string,
  grants: Array<{ resource_key: string; action: string; effect: string }>
): Promise<void> {
  await api.put("/authz/grants", {
    subject_type: subjectType,
    subject_id: subjectId,
    grants,
  });
}

export async function previewAuthz(subjectType: string, subjectId: string): Promise<AuthzMe> {
  const { data } = await api.post("/authz/preview", {
    subject_type: subjectType,
    subject_id: subjectId,
  });
  return {
    views: data?.views || {},
    rest: data?.rest || {},
  };
}
