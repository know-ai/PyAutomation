export const SYSTEM_USERNAME = "system";
export const SYSTEM_HOME_PATH = "/user-management";

export function isSystemUser(user?: { username?: string } | null): boolean {
  return (user?.username || "").trim().toLowerCase() === SYSTEM_USERNAME;
}
