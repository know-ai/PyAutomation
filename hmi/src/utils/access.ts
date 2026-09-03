/** HMI view ids aligned with the backend ACL catalog. */

export const VIEW_IDS = {
  communicationsClients: "hmi:view.communications.clients",
  communicationsServer: "hmi:view.communications.server",
  database: "hmi:view.database",
  tagsDefinitions: "hmi:view.tags.definitions",
  tagsDatalogger: "hmi:view.tags.datalogger",
  tagsTrends: "hmi:view.tags.trends",
  realTimeTrends: "hmi:view.real-time-trends",
  alarmsDefinitions: "hmi:view.alarms.definitions",
  alarmsSummary: "hmi:view.alarms.summary",
  machinesSummary: "hmi:view.machines.summary",
  machinesDetailed: "hmi:view.machines.detailed",
  events: "hmi:view.events",
  operationalLogs: "hmi:view.operational-logs",
  performance: "hmi:view.performance",
  ldsDashboard: "hmi:view.lds-dashboard",
  userManagement: "hmi:view.user-management",
  authz: "hmi:view.authz",
  settings: "hmi:view.settings",
} as const;

/** Client-side HMI capabilities (not routed screens). */
export const CAPABILITY_IDS = {
  csvExport: "hmi:capability.csv-export",
} as const;

export type CapabilityId = (typeof CAPABILITY_IDS)[keyof typeof CAPABILITY_IDS];

export type ViewId = (typeof VIEW_IDS)[keyof typeof VIEW_IDS];

export const VIEW_PATHS: Array<{ view: ViewId; path: string }> = [
  { view: VIEW_IDS.communicationsClients, path: "/communications/clients" },
  { view: VIEW_IDS.communicationsServer, path: "/communications/server" },
  { view: VIEW_IDS.database, path: "/database" },
  { view: VIEW_IDS.tagsDefinitions, path: "/tags/definitions" },
  { view: VIEW_IDS.tagsDatalogger, path: "/tags/datalogger" },
  { view: VIEW_IDS.tagsTrends, path: "/tags/trends" },
  { view: VIEW_IDS.realTimeTrends, path: "/real-time-trends" },
  { view: VIEW_IDS.alarmsDefinitions, path: "/alarms/definitions" },
  { view: VIEW_IDS.alarmsSummary, path: "/alarms/summary" },
  { view: VIEW_IDS.machinesSummary, path: "/machines/summary" },
  { view: VIEW_IDS.machinesDetailed, path: "/machines/detailed" },
  { view: VIEW_IDS.events, path: "/events" },
  { view: VIEW_IDS.operationalLogs, path: "/operational-logs" },
  { view: VIEW_IDS.performance, path: "/performance" },
  { view: VIEW_IDS.ldsDashboard, path: "/lds-dashboard" },
  { view: VIEW_IDS.userManagement, path: "/user-management" },
  { view: VIEW_IDS.authz, path: "/user-management/access" },
  { view: VIEW_IDS.settings, path: "/settings" },
];

export type AuthzActionsMap = Record<string, string[]>;

export function hasAction(
  map: AuthzActionsMap | undefined,
  resourceKey: string,
  action: "view" | "use" = "view"
): boolean {
  return Boolean(map?.[resourceKey]?.includes(action));
}

export function hasRestFragment(
  rest: AuthzActionsMap | undefined,
  fragment: string,
  action: "view" | "use" = "use"
): boolean {
  if (!rest) return false;
  return Object.entries(rest).some(([key, acts]) => key.includes(fragment) && acts.includes(action));
}

export function viewForPath(path: string): ViewId | null {
  const normalized = path.replace(/\/+$/, "") || "/";
  const ranked = [...VIEW_PATHS].sort((a, b) => b.path.length - a.path.length);
  for (const item of ranked) {
    if (normalized === item.path || normalized.startsWith(`${item.path}/`)) {
      return item.view;
    }
  }
  if (normalized === "/communications") return VIEW_IDS.communicationsClients;
  if (normalized === "/tags") return VIEW_IDS.tagsDefinitions;
  if (normalized === "/alarms") return VIEW_IDS.alarmsDefinitions;
  if (normalized === "/machines") return VIEW_IDS.machinesSummary;
  return null;
}

export function firstAllowedPath(
  views: AuthzActionsMap | undefined,
  isSystem: boolean
): string {
  if (isSystem) return "/user-management";
  for (const item of VIEW_PATHS) {
    if (hasAction(views, item.view, "view")) return item.path;
  }
  return "/no-access";
}
