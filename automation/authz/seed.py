# -*- coding: utf-8 -*-
"""Default ACL matrix by role. Idempotent: never overwrites existing grants."""
from __future__ import annotations

import logging
from typing import Any

from .catalog import ACTIONS, HMI_VIEW_KEYS, all_resource_keys
from . import store

_LOGGER = logging.getLogger("pyautomation")

# Built-in roles with an explicit matrix in default_allows(). Any other role
# created at runtime inherits the baseline (guest — lowest default privilege).
BUILTIN_SEED_ROLES = frozenset(
    {"integrator", "sudo", "admin", "supervisor", "operator", "auditor", "guest"}
)
BASELINE_ROLE = "guest"

# HMI view sets (inheritance: guest ⊂ auditor ⊂ operator ⊂ supervisor ⊂ admin).
# Only ``view`` is seeded for built-in roles; screen actions use REST grants.
_GUEST_HMI = frozenset(
    {
        "hmi:view.real-time-trends",
        "hmi:view.machines.summary",
        "hmi:view.machines.detailed",
    }
)
_AUDITOR_HMI = _GUEST_HMI | frozenset(
    {
        "hmi:view.alarms.summary",
        "hmi:view.events",
        "hmi:view.operational-logs",
        "hmi:view.tags.datalogger",
        "hmi:view.tags.trends",
    }
)
_OPERATOR_HMI = _AUDITOR_HMI | frozenset(
    {
        "hmi:view.alarms.definitions",
        "hmi:view.tags.definitions",
        "hmi:view.tags.datalogger",
        "hmi:view.tags.trends",
    }
)
_SUPERVISOR_HMI = _OPERATOR_HMI | frozenset(
    {
        "hmi:view.communications.clients",
        "hmi:view.communications.server",
        "hmi:view.performance",
    }
)
_ADMIN_HMI = _SUPERVISOR_HMI | frozenset({"hmi:view.settings"})

_HMI_VIEWS_BY_ROLE: dict[str, frozenset[str]] = {
    "guest": _GUEST_HMI,
    "auditor": _AUDITOR_HMI,
    "operator": _OPERATOR_HMI,
    "supervisor": _SUPERVISOR_HMI,
    "admin": _ADMIN_HMI,
}
# HMI screens where supervisor/admin may POST/PUT/DELETE via view REST bundles.
_HMI_WRITE_VIEWS_BY_ROLE: dict[str, frozenset[str]] = {
    "supervisor": frozenset(
        {
            "hmi:view.tags.definitions",
            "hmi:view.communications.clients",
            "hmi:view.communications.server",
            "hmi:view.alarms.definitions",
            "hmi:view.machines.detailed",
            "hmi:view.performance",
        }
    ),
    "admin": frozenset(
        {
            "hmi:view.tags.definitions",
            "hmi:view.communications.clients",
            "hmi:view.communications.server",
            "hmi:view.alarms.definitions",
            "hmi:view.machines.detailed",
            "hmi:view.performance",
        }
    ),
}

_CSV_EXPORT_CAPABILITY = "hmi:capability.csv-export"
_CSV_EXPORT_ROLES = frozenset({"auditor", "supervisor", "admin", "integrator"})

_ADMIN_REST_DENY_PREFIXES = (
    "/api/users",
    "/api/authz",
    "/api/database/config",
    "/api/database/connect",
)

_OPERATOR_ALARM_USE_FRAGMENTS = (
    "/acknowledge",
    "/acknowledge_all",
    "/shelve/",
    "/unshelve/",
)


def _rest_parts(resource_key: str) -> tuple[str, str]:
    if not resource_key.startswith("rest:"):
        return "", ""
    body = resource_key[5:]
    method, _, path = body.partition(" ")
    return method.upper(), path


def _path_is(path: str, *prefixes: str) -> bool:
    normalized = str(path or "").rstrip("/")
    for prefix in prefixes:
        base = str(prefix or "").rstrip("/")
        if not base:
            continue
        if normalized == base or normalized.startswith(base + "/") or normalized.startswith(base + "<"):
            return True
    return False


def _path_denied_for_admin(path: str) -> bool:
    for prefix in _ADMIN_REST_DENY_PREFIXES:
        if _path_is(path, prefix):
            return True
    if path.startswith("/api/authz") and not path.rstrip("/").endswith("/me"):
        return True
    return False


def _rest_is_read(method: str, action: str) -> bool:
    return action == "view" or str(method or "").upper() in {"GET", "HEAD"}


def _guest_rest_allows(method: str, path: str, action: str) -> bool:
    if not _rest_is_read(method, action):
        return False
    return _path_is(
        path,
        "/api/machines",
        "/api/tags",
        "/api/history",
        "/api/hmi",
        "/api/linear-referencing-geospatial",
    )


def _auditor_rest_allows(method: str, path: str, action: str) -> bool:
    if _guest_rest_allows(method, path, action):
        return True
    if not _rest_is_read(method, action):
        return False
    return _path_is(path, "/api/alarms", "/api/events", "/api/logs")


def _operator_rest_allows(method: str, path: str, action: str) -> bool:
    if _auditor_rest_allows(method, path, action):
        return True
    if _path_is(path, "/api/alarms") and action == "use":
        return any(fragment in path for fragment in _OPERATOR_ALARM_USE_FRAGMENTS)
    return False


def _supervisor_rest_allows(method: str, path: str, action: str) -> bool:
    if _operator_rest_allows(method, path, action):
        return True
    if _path_is(path, "/api/opcua"):
        return True
    if _path_is(path, "/api/settings/performance", "/api/admin"):
        return _rest_is_read(method, action)
    return False


def _admin_rest_allows(method: str, path: str, action: str) -> bool:
    if _path_denied_for_admin(path):
        return False
    if _supervisor_rest_allows(method, path, action):
        return True
    if _path_is(path, "/api/settings"):
        return True
    return False


def _default_allows_hmi(role: str, resource_key: str, action: str) -> bool:
    if role == "integrator":
        return True
    if resource_key == _CSV_EXPORT_CAPABILITY:
        return role in _CSV_EXPORT_ROLES and action == "use"
    views = _HMI_VIEWS_BY_ROLE.get(role, frozenset())
    if resource_key not in views:
        return False
    if action == "view":
        return True
    if action == "use":
        return resource_key in _HMI_WRITE_VIEWS_BY_ROLE.get(role, frozenset())
    return False


def _default_allows_rest(role: str, method: str, path: str, action: str) -> bool:
    if role == "integrator":
        return True
    if role == "guest":
        return _guest_rest_allows(method, path, action)
    if role == "auditor":
        return _auditor_rest_allows(method, path, action)
    if role == "operator":
        return _operator_rest_allows(method, path, action)
    if role == "supervisor":
        return _supervisor_rest_allows(method, path, action)
    if role == "admin":
        return _admin_rest_allows(method, path, action)
    return False


def default_allows(role_name: str, resource_key: str, action: str) -> bool:
    """True when the seed matrix grants allow for this role/key/action."""
    role = str(role_name or "").strip().lower()
    action = str(action or "").strip().lower()
    if role == "integrator":
        return True
    if role == "sudo":
        return False
    if role not in BUILTIN_SEED_ROLES:
        return default_allows(BASELINE_ROLE, resource_key, action)
    if resource_key.startswith("hmi:"):
        return _default_allows_hmi(role, resource_key, action)

    method, path = _rest_parts(resource_key)
    if not path:
        return False
    return _default_allows_rest(role, method, path, action)


def _persist_row(row: dict) -> None:
    try:
        from ..dbmodels.authz import AuthzGrant

        existing = AuthzGrant.get_or_none(
            (AuthzGrant.subject_type == row["subject_type"])
            & (AuthzGrant.subject_id == row["subject_id"])
            & (AuthzGrant.resource_key == row["resource_key"])
            & (AuthzGrant.action == row["action"])
        )
        if existing is None:
            AuthzGrant.create(**row)
        else:
            if existing.effect != row["effect"]:
                return
    except Exception:
        _LOGGER.debug("authz historian persist skipped", exc_info=True)
    try:
        from ..catalog.local_provider import LocalCatalogProvider
        from ..catalog.versions import edge_node_id, now_ms

        LocalCatalogProvider().upsert(
            "authz_grants",
            row,
            node_id=edge_node_id(),
            version=now_ms(),
        )
    except Exception:
        _LOGGER.debug("authz local persist skipped", exc_info=True)


def _role_rows() -> list[dict]:
    rows: list[dict] = []
    try:
        from ..dbmodels.users import Roles

        for role in Roles.select().iterator():
            rows.append(
                {
                    "name": str(role.name or "").lower(),
                    "identifier": str(role.identifier or ""),
                }
            )
        if rows:
            return rows
    except Exception:
        _LOGGER.debug("authz roles from historian skipped", exc_info=True)
    try:
        from ..catalog.local_provider import LocalCatalogProvider

        for row in LocalCatalogProvider().read_all("roles"):
            rows.append(
                {
                    "name": str(row.get("name") or "").lower(),
                    "identifier": str(row.get("identifier") or ""),
                }
            )
    except Exception:
        _LOGGER.debug("authz roles from local catalog skipped", exc_info=True)
    if rows:
        return rows
    try:
        from ..modules.users.roles import roles as cvt_roles

        for role in cvt_roles.roles.values():
            rows.append(
                {
                    "name": str(getattr(role, "name", "") or "").lower(),
                    "identifier": str(getattr(role, "identifier", "") or ""),
                }
            )
    except Exception:
        pass
    return rows


def _existing_tuple_set() -> set[tuple[str, str, str, str]]:
    existing: set[tuple[str, str, str, str]] = set()
    for (stype, sid, key, action), _effect in store.snapshot().items():
        existing.add((stype, sid, key, action))
    try:
        from ..dbmodels.authz import AuthzGrant

        for row in AuthzGrant.select().iterator():
            existing.add(
                (
                    str(row.subject_type).lower(),
                    str(row.subject_id).lower(),
                    str(row.resource_key),
                    str(row.action).lower(),
                )
            )
    except Exception:
        pass
    try:
        from ..catalog.local_provider import LocalCatalogProvider

        for row in LocalCatalogProvider().read_all("authz_grants"):
            existing.add(
                (
                    str(row.get("subject_type") or "").lower(),
                    str(row.get("subject_id") or "").lower(),
                    str(row.get("resource_key") or ""),
                    str(row.get("action") or "").lower(),
                )
            )
    except Exception:
        pass
    return existing


def _baseline_role_identifier() -> str | None:
    try:
        from ..modules.users.roles import roles as cvt_roles

        role = cvt_roles.get_by_name(name=BASELINE_ROLE)
        if role is not None:
            return str(getattr(role, "identifier", "") or "") or None
    except Exception:
        pass
    try:
        from ..dbmodels.users import Roles

        row = Roles.read_by_name(BASELINE_ROLE)
        if row is not None:
            return str(row.identifier or "") or None
    except Exception:
        pass
    for role in _role_rows():
        if str(role.get("name") or "").lower() == BASELINE_ROLE:
            return str(role.get("identifier") or "") or None
    return None


def _clone_baseline_grants(target_identifier: str, *, persist: bool = True) -> int:
    """Copy ACL rows from the guest role onto a newly created role."""
    source_id = _baseline_role_identifier()
    if not source_id or not target_identifier:
        return 0
    from .grants import list_grants

    existing = _existing_tuple_set()
    created = 0
    for row in list_grants("role", source_id):
        resource_key = str(row.get("resource_key") or "")
        action = str(row.get("action") or "").lower()
        effect = str(row.get("effect") or "").lower()
        if not resource_key or effect not in {"allow", "deny"}:
            continue
        tuple_key = ("role", str(target_identifier).lower(), resource_key, action)
        if tuple_key in existing:
            continue
        store.put_grant("role", target_identifier, resource_key, action, effect)
        if persist:
            _persist_row(
                {
                    "subject_type": "role",
                    "subject_id": target_identifier,
                    "resource_key": resource_key,
                    "action": action,
                    "effect": effect,
                }
            )
        existing.add(tuple_key)
        created += 1
    return created


def _seed_matrix_grants_for_role(
    role_name: str,
    role_identifier: str,
    flask_app: Any | None,
    *,
    persist: bool = True,
    template_role: str | None = None,
) -> int:
    """Insert missing allow rows for one role using the seed matrix."""
    put_fn = store.put_grant
    keys = all_resource_keys(flask_app)
    if not keys:
        keys = list(HMI_VIEW_KEYS)
    existing = _existing_tuple_set()
    template = str(template_role or role_name or "").strip().lower()
    created = 0
    for resource_key in keys:
        for action in ACTIONS:
            tuple_key = ("role", str(role_identifier).lower(), resource_key, action)
            if tuple_key in existing:
                continue
            if not default_allows(template, resource_key, action):
                continue
            row = {
                "subject_type": "role",
                "subject_id": role_identifier,
                "resource_key": resource_key,
                "effect": "allow",
                "action": action,
            }
            put_fn("role", role_identifier, resource_key, action, "allow")
            if persist:
                _persist_row(row)
            existing.add(tuple_key)
            created += 1
    return created


def seed_grants_for_new_role(
    role_name: str,
    role_identifier: str,
    flask_app: Any | None = None,
    *,
    persist: bool = True,
) -> int:
    """Baseline ACL for a dynamically created role (clone guest + matrix gap-fill)."""
    from .bootstrap import resolve_flask_app

    app = resolve_flask_app(flask_app)
    created = _clone_baseline_grants(role_identifier, persist=persist)
    created += _seed_matrix_grants_for_role(
        role_name,
        role_identifier,
        app,
        persist=persist,
        template_role=BASELINE_ROLE,
    )
    if created and persist:
        try:
            from .store import reload_cache

            reload_cache(reason="new_role")
        except Exception:
            _LOGGER.debug("authz reload after new role skipped", exc_info=True)
        _LOGGER.info(
            "authz grants seeded for new role name=%s identifier=%s count=%s",
            role_name,
            role_identifier,
            created,
        )
    return created


def seed_default_grants(
    flask_app: Any | None = None,
    *,
    persist: bool = True,
    put=None,
) -> int:
    """Insert missing allow rows for the default matrix. Does not overwrite."""
    put_fn = put or store.put_grant
    keys = all_resource_keys(flask_app)
    if not keys:
        keys = list(HMI_VIEW_KEYS)
    existing = _existing_tuple_set()
    created = 0
    for role in _role_rows():
        identifier = role.get("identifier") or ""
        name = role.get("name") or ""
        if not identifier or not name:
            continue
        for resource_key in keys:
            for action in ACTIONS:
                tuple_key = ("role", identifier.lower(), resource_key, action)
                if tuple_key in existing:
                    continue
                if not default_allows(name, resource_key, action):
                    continue
                row = {
                    "subject_type": "role",
                    "subject_id": identifier,
                    "resource_key": resource_key,
                    "effect": "allow",
                    "action": action,
                }
                put_fn("role", identifier, resource_key, action, "allow")
                if persist:
                    _persist_row(row)
                existing.add(tuple_key)
                created += 1
    if created:
        _LOGGER.info("authz default grants seeded count=%s", created)
    return created


def seed_historian_grants(flask_app: Any | None = None) -> int:
    return seed_default_grants(flask_app, persist=True)
