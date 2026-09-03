import { useCallback, useEffect, useMemo, useState } from "react";
import { Card } from "../components/Card";
import { Button } from "../components/Button";
import { useTranslation } from "../hooks/useTranslation";
import {
  getAuthzCatalog,
  previewAuthz,
  putAuthzGrants,
  type AuthzCatalog,
  type AuthzMe,
} from "../services/authz";
import { getAllRoles, getUsers, type Role, type User } from "../services/users";
import { showToast } from "../utils/toast";

type EffectValue = "allow" | "deny";
type AuthzTab = "hmi" | "rest";

function grantKey(resourceKey: string, action: string) {
  return `${resourceKey}::${action}`;
}

function splitGrantKey(key: string): { resourceKey: string; action: string } | null {
  const sep = key.lastIndexOf("::");
  if (sep <= 0) return null;
  return { resourceKey: key.slice(0, sep), action: key.slice(sep + 2) };
}

function buildDraftFromEffective(catalog: AuthzCatalog, effective: AuthzMe): Record<string, EffectValue> {
  const next: Record<string, EffectValue> = {};
  const isAllowed = (resourceKey: string, action: string) =>
    Boolean(effective.views[resourceKey]?.includes(action) || effective.rest[resourceKey]?.includes(action));

  const visit = (resourceKey: string, actions: string[]) => {
    for (const action of actions) {
      next[grantKey(resourceKey, action)] = isAllowed(resourceKey, action) ? "allow" : "deny";
    }
  };

  for (const items of Object.values(catalog.hmi || {})) {
    for (const item of items) {
      visit(item.resource_key, item.actions?.length ? item.actions : ["view", "use"]);
    }
  }
  for (const items of Object.values(catalog.rest || {})) {
    for (const item of items) {
      visit(item.resource_key, item.actions?.length ? item.actions : ["view", "use"]);
    }
  }
  return next;
}

function formatRestLabel(resourceKey: string): string {
  if (!resourceKey.startsWith("rest:")) return resourceKey;
  const body = resourceKey.slice(5);
  const space = body.indexOf(" ");
  if (space < 0) return body;
  return `${body.slice(0, space)} ${body.slice(space + 1)}`;
}

export function AccessControl() {
  const { t } = useTranslation();
  const [subjectType, setSubjectType] = useState<"role" | "user">("role");
  const [subjectId, setSubjectId] = useState("");
  const [roles, setRoles] = useState<Role[]>([]);
  const [users, setUsers] = useState<User[]>([]);
  const [catalog, setCatalog] = useState<AuthzCatalog | null>(null);
  const [draft, setDraft] = useState<Record<string, EffectValue>>({});
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [activeTab, setActiveTab] = useState<AuthzTab>("hmi");
  const [restSearch, setRestSearch] = useState("");
  const [expandedRestGroups, setExpandedRestGroups] = useState<Set<string>>(() => new Set());

  useEffect(() => {
    void Promise.all([getAuthzCatalog(), getAllRoles(), getUsers(1, 200)])
      .then(([cat, roleList, userResp]) => {
        setCatalog(cat);
        setRoles(Array.isArray(roleList) ? roleList : []);
        setUsers(Array.isArray(userResp?.data) ? userResp.data : []);
      })
      .catch(() => {
        showToast(t("authz.loadError"), "error");
      });
  }, [t]);

  const loadGrants = useCallback(async () => {
    if (!subjectId || !catalog) return;
    setLoading(true);
    try {
      const effective = await previewAuthz(subjectType, subjectId);
      setDraft(buildDraftFromEffective(catalog, effective));
    } catch {
      showToast(t("authz.loadError"), "error");
    } finally {
      setLoading(false);
    }
  }, [catalog, subjectId, subjectType, t]);

  useEffect(() => {
    void loadGrants();
  }, [loadGrants]);

  const setEffect = (resourceKey: string, action: string, effect: EffectValue) => {
    setDraft((prev) => ({ ...prev, [grantKey(resourceKey, action)]: effect }));
  };

  const currentEffect = (resourceKey: string, action: string): EffectValue =>
    draft[grantKey(resourceKey, action)] ?? "deny";

  const handleSave = async () => {
    if (!subjectId) return;
    const payload = Object.entries(draft).flatMap(([key, effect]) => {
      const parsed = splitGrantKey(key);
      if (!parsed) return [];
      return [{ resource_key: parsed.resourceKey, action: parsed.action, effect }];
    });
    setSaving(true);
    try {
      await putAuthzGrants(subjectType, subjectId, payload);
      showToast(t("authz.saved"), "success");
      await loadGrants();
    } catch {
      showToast(t("authz.saveError"), "error");
    } finally {
      setSaving(false);
    }
  };

  const restFilter = restSearch.trim().toLowerCase();

  const filteredRestGroups = useMemo(() => {
    if (!catalog?.rest) return [];
    return Object.entries(catalog.rest)
      .map(([group, items]) => {
        const filtered = items.filter((item) => {
          if (!restFilter) return true;
          const label = formatRestLabel(item.resource_key).toLowerCase();
          return label.includes(restFilter) || item.resource_key.toLowerCase().includes(restFilter);
        });
        return [group, filtered] as const;
      })
      .filter(([, items]) => items.length > 0);
  }, [catalog, restFilter]);

  const isRestGroupExpanded = useCallback(
    (group: string) => {
      if (restFilter) return true;
      return expandedRestGroups.has(group);
    },
    [expandedRestGroups, restFilter]
  );

  const toggleRestGroup = (group: string) => {
    if (restFilter) return;
    setExpandedRestGroups((prev) => {
      const next = new Set(prev);
      if (next.has(group)) next.delete(group);
      else next.add(group);
      return next;
    });
  };

  const renderEffectSelect = (resourceKey: string, action: string) => (
    <select
      className="form-select form-select-sm"
      value={currentEffect(resourceKey, action)}
      onChange={(e) => setEffect(resourceKey, action, e.target.value as EffectValue)}
      disabled={!subjectId || loading}
    >
      <option value="allow">{t("authz.effectAllow")}</option>
      <option value="deny">{t("authz.effectDeny")}</option>
    </select>
  );

  const renderHmiRow = (resourceKey: string, extra?: string) => (
    <tr key={resourceKey}>
      <td>
        <code className="small">{resourceKey}</code>
        {extra ? <div className="text-muted small">{extra}</div> : null}
      </td>
      {(["view", "use"] as const).map((action) => (
        <td key={action}>{renderEffectSelect(resourceKey, action)}</td>
      ))}
    </tr>
  );

  const renderRestRow = (resourceKey: string) => (
    <tr key={resourceKey}>
      <td>
        <code className="small">{formatRestLabel(resourceKey)}</code>
      </td>
      {(["view", "use"] as const).map((action) => (
        <td key={action}>{renderEffectSelect(resourceKey, action)}</td>
      ))}
    </tr>
  );

  return (
    <div className="row g-0 page-fit-viewport">
      <div className="col-12 h-100">
        <Card
          className="page-fit-card"
          headerClassName="overflow-visible"
          bodyClassName="d-flex flex-column"
          title={
            <div className="d-flex align-items-center gap-2 w-100 flex-nowrap authz-access-toolbar">
              <span className="text-nowrap flex-shrink-0">{t("authz.title")}</span>
              <select
                className="form-select form-select-sm flex-shrink-0"
                style={{ width: "auto", minWidth: "6.5rem" }}
                value={subjectType}
                onChange={(e) => {
                  setSubjectType(e.target.value as "role" | "user");
                  setSubjectId("");
                  setDraft({});
                }}
              >
                <option value="role">{t("authz.role")}</option>
                <option value="user">{t("authz.user")}</option>
              </select>
              <select
                className="form-select form-select-sm"
                style={{ minWidth: "11rem", maxWidth: "18rem", flex: "1 1 12rem" }}
                value={subjectId}
                onChange={(e) => setSubjectId(e.target.value)}
              >
                <option value="">{t("authz.selectSubject")}</option>
                {subjectType === "role"
                  ? roles.map((role) => (
                      <option key={role.identifier || role.name} value={role.identifier || role.name}>
                        {role.name}
                      </option>
                    ))
                  : users.map((user) => (
                      <option key={user.identifier || user.username} value={user.identifier || user.username}>
                        {user.username}
                      </option>
                    ))}
              </select>
              <Button
                variant="primary"
                className="btn-sm flex-shrink-0 ms-auto"
                onClick={() => void handleSave()}
                loading={saving}
                disabled={!subjectId}
              >
                {t("common.save")}
              </Button>
            </div>
          }
        >
          <ul className="nav nav-tabs mb-3 flex-shrink-0">
            <li className="nav-item">
              <button
                type="button"
                className={`nav-link ${activeTab === "hmi" ? "active" : ""}`}
                onClick={() => setActiveTab("hmi")}
              >
                {t("authz.tabHmi")}
              </button>
            </li>
            <li className="nav-item">
              <button
                type="button"
                className={`nav-link ${activeTab === "rest" ? "active" : ""}`}
                onClick={() => setActiveTab("rest")}
              >
                {t("authz.tabRest")}
              </button>
            </li>
          </ul>

          {activeTab === "hmi" ? (
            <div className="table-responsive flex-grow-1" style={{ minHeight: 0 }}>
              <table className="table table-sm align-middle">
                <thead>
                  <tr>
                    <th>{t("authz.resource")}</th>
                    <th style={{ width: "8rem" }}>{t("authz.view")}</th>
                    <th style={{ width: "8rem" }}>{t("authz.use")}</th>
                  </tr>
                </thead>
                <tbody>
                  {catalog
                    ? Object.entries(catalog.hmi || {}).flatMap(([group, items]) => [
                        <tr key={`g-${group}`}>
                          <td colSpan={3} className="table-secondary fw-semibold">
                            {group}
                          </td>
                        </tr>,
                        ...items.map((item) => renderHmiRow(item.resource_key, item.path)),
                      ])
                    : null}
                </tbody>
              </table>
            </div>
          ) : (
            <div className="authz-rest-panel d-flex flex-column flex-grow-1" style={{ minHeight: 0 }}>
              <div className="mb-3 flex-shrink-0">
                <input
                  type="search"
                  className="form-control form-control-sm"
                  placeholder={t("authz.searchRest")}
                  value={restSearch}
                  onChange={(e) => setRestSearch(e.target.value)}
                />
              </div>
              <div className="authz-rest-scroll table-responsive flex-grow-1" style={{ minHeight: 0 }}>
                <table className="table table-sm align-middle mb-0">
                  <thead>
                    <tr>
                      <th>{t("authz.endpoint")}</th>
                      <th style={{ width: "8rem" }}>{t("authz.view")}</th>
                      <th style={{ width: "8rem" }}>{t("authz.use")}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {filteredRestGroups.length === 0 ? (
                      <tr>
                        <td colSpan={3} className="text-muted small">
                          {t("authz.noRestMatches")}
                        </td>
                      </tr>
                    ) : (
                      filteredRestGroups.flatMap(([group, items]) => {
                        const expanded = isRestGroupExpanded(group);
                        return [
                          <tr
                            key={`g-rest-${group}`}
                            className="authz-rest-group-header table-secondary"
                            onClick={() => toggleRestGroup(group)}
                            onKeyDown={(e) => {
                              if (e.key === "Enter" || e.key === " ") {
                                e.preventDefault();
                                toggleRestGroup(group);
                              }
                            }}
                            tabIndex={0}
                            role="button"
                            aria-expanded={expanded}
                          >
                            <td colSpan={3} className="fw-semibold">
                              <i
                                className={`bi ${expanded ? "bi-chevron-down" : "bi-chevron-right"} me-2`}
                                aria-hidden
                              />
                              /api/{group}
                              <span className="text-muted small ms-2">
                                ({items.length} {t("authz.endpoints")})
                              </span>
                            </td>
                          </tr>,
                          ...(expanded ? items.map((item) => renderRestRow(item.resource_key)) : []),
                        ];
                      })
                    )}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </Card>
      </div>
    </div>
  );
}
