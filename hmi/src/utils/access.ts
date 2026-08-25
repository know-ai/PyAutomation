/** Coarse HMI access helpers (not industrial RBAC). */

export const OPS_ADMIN_ROLES = ["admin", "supervisor", "sudo"] as const;

export type OpsAdminRole = (typeof OPS_ADMIN_ROLES)[number];

export function normalizeRoleName(role?: string | null): string {
  return String(role || "").trim().toLowerCase();
}

/** Node performance, settings, and user management (non-system sessions). */
export function canViewOpsAdmin(role?: string | null): boolean {
  const normalized = normalizeRoleName(role);
  return (OPS_ADMIN_ROLES as readonly string[]).includes(normalized);
}

/** Alias kept for existing performance imports. */
export function canViewPerformance(role?: string | null): boolean {
  const normalized = normalizeRoleName(role);
  return Boolean(normalized) && normalized !== "guest";
}

/** Restart workers, force SAF/catalog sync, rebuild derived tags. */
export function canControlOps(role?: string | null): boolean {
  return canViewOpsAdmin(role);
}

/** Empty SAF queue / clean catalog orphans (admin/sudo). */
export function canDestroyOps(role?: string | null): boolean {
  const normalized = normalizeRoleName(role);
  return normalized === "admin" || normalized === "sudo";
}

export function canViewSettings(role?: string | null): boolean {
  return canViewOpsAdmin(role);
}

export function canViewUserManagement(role?: string | null): boolean {
  return canViewOpsAdmin(role);
}
