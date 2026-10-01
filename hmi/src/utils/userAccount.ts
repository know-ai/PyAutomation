const ACCOUNT_ADMIN_ROLES = new Set(["integrator", "admin", "administrator"]);

export function actorMaySetUserEnabled(role?: string | null): boolean {
  return ACCOUNT_ADMIN_ROLES.has(String(role || "").trim().toLowerCase());
}

export function actorMayConfigureMachineColumns(role?: string | null): boolean {
  return ACCOUNT_ADMIN_ROLES.has(String(role || "").trim().toLowerCase());
}

export function accountIsEnabled(enabled: boolean | null | undefined): boolean {
  return enabled !== false;
}
