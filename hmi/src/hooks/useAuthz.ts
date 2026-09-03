import { useAppSelector } from "./useAppSelector";
import { hasAction, hasRestFragment, CAPABILITY_IDS, type ViewId } from "../utils/access";
import { isSystemUser } from "../utils/systemUser";

export function useAuthz() {
  const views = useAppSelector((s) => s.authz.views);
  const rest = useAppSelector((s) => s.authz.rest);
  const status = useAppSelector((s) => s.authz.status);
  const user = useAppSelector((s) => s.auth.user);
  const system = isSystemUser(user);

  const canView = (viewId: ViewId | string) => {
    if (system && (viewId === "hmi:view.user-management" || viewId === "hmi:view.authz")) return true;
    return hasAction(views, viewId, "view");
  };
  const canUse = (viewId: ViewId | string) => {
    if (system && (viewId === "hmi:view.user-management" || viewId === "hmi:view.authz")) return true;
    return hasAction(views, viewId, "use");
  };
  const canRest = (fragment: string, action: "view" | "use" = "use") =>
    system ? fragment.startsWith("/api/users") || fragment.includes("/api/authz") : hasRestFragment(rest, fragment, action);
  const canExportCsv = () => hasAction(views, CAPABILITY_IDS.csvExport, "use");

  return { views, rest, status, canView, canUse, canRest, canExportCsv, isSystem: system };
}
