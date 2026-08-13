/** Screens that cannot render without the remote historian. */
export const REMOTE_DB_DEPENDENT_PATHS = [
  "/tags/datalogger",
  "/tags/trends",
  "/alarms/summary",
  "/events",
  "/operational-logs",
  "/user-management",
] as const;

export function isRemoteDbDependentPath(pathname: string): boolean {
  return REMOTE_DB_DEPENDENT_PATHS.some(
    (path) => pathname === path || pathname.startsWith(`${path}/`)
  );
}
