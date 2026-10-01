# -*- coding: utf-8 -*-
"""HMI view ids and REST resource keys (`rest:{METHOD} {flask_rule}`)."""
from __future__ import annotations

from typing import Any

HMI_VIEWS: tuple[dict[str, str], ...] = (
    {"key": "hmi:view.communications.clients", "group": "communications", "path": "/communications/clients"},
    {"key": "hmi:view.communications.server", "group": "communications", "path": "/communications/server"},
    {"key": "hmi:view.database", "group": "configuration", "path": "/database"},
    {"key": "hmi:view.tags.definitions", "group": "tags", "path": "/tags/definitions"},
    {"key": "hmi:view.tags.datalogger", "group": "tags", "path": "/tags/datalogger"},
    {"key": "hmi:view.tags.trends", "group": "tags", "path": "/tags/trends"},
    {"key": "hmi:view.real-time-trends", "group": "tags", "path": "/real-time-trends"},
    {"key": "hmi:view.alarms.definitions", "group": "alarms", "path": "/alarms/definitions"},
    {"key": "hmi:view.alarms.summary", "group": "alarms", "path": "/alarms/summary"},
    {"key": "hmi:view.machines.summary", "group": "machines", "path": "/machines/summary"},
    {"key": "hmi:view.machines.detailed", "group": "machines", "path": "/machines/detailed"},
    {"key": "hmi:view.events", "group": "audit", "path": "/events"},
    {"key": "hmi:view.operational-logs", "group": "audit", "path": "/operational-logs"},
    {"key": "hmi:view.performance", "group": "ops", "path": "/performance"},
    {"key": "hmi:view.lds-dashboard", "group": "ops", "path": "/lds-dashboard"},
    {"key": "hmi:view.user-management", "group": "administration", "path": "/user-management"},
    {"key": "hmi:view.authz", "group": "administration", "path": "/user-management/access"},
    {"key": "hmi:view.settings", "group": "configuration", "path": "/settings"},
    {"key": "hmi:capability.csv-export", "group": "capabilities", "path": ""},
)

HMI_VIEW_KEYS: tuple[str, ...] = tuple(item["key"] for item in HMI_VIEWS)

HMI_PATH_TO_VIEW: dict[str, str] = {item["path"]: item["key"] for item in HMI_VIEWS}

SYSTEM_HMI_VIEWS: tuple[str, ...] = (
    "hmi:view.user-management",
    "hmi:view.authz",
)

ACTIONS: tuple[str, ...] = ("view", "use")


def canonical_rest_method(method: str) -> str:
    """HEAD is Flask's automatic twin of GET; ACL and catalog use GET."""
    method_u = str(method or "GET").upper()
    if method_u == "HEAD":
        return "GET"
    return method_u or "GET"


def rest_resource_key(method: str, rule: str) -> str:
    normalized_rule = str(rule or "")
    if normalized_rule and not normalized_rule.startswith("/"):
        normalized_rule = "/" + normalized_rule
    if normalized_rule and not normalized_rule.startswith("/api"):
        normalized_rule = "/api" + normalized_rule
    return f"rest:{canonical_rest_method(method)} {normalized_rule}"


def default_action(method: str) -> str:
    return "view" if str(method or "").upper() in {"GET", "HEAD"} else "use"


def rest_action_from_key(resource_key: str) -> str:
    """REST keys encode the verb; ACL uses one action (GET/HEAD=view, else use)."""
    body = str(resource_key or "")
    if body.startswith("rest:"):
        body = body[5:]
    method, _, _ = body.partition(" ")
    return default_action(method)


def rest_key_from_request() -> str | None:
    from flask import request

    rule = ""
    if request.url_rule is not None:
        rule = str(request.url_rule.rule or "")
    if not rule:
        rule = str(request.path or "")
    return rest_resource_key(request.method, rule)


# Paths the middleware never sends through evaluate(). Hidden from the ACL
# catalog so Access Control does not show them as Deny.
PUBLIC_REST_EXACT = frozenset(
    {
        ("POST", "/api/users/login"),
        ("POST", "/api/users/signup"),
        ("POST", "/api/users/credentials_are_valid"),
        ("GET", "/api/health/ping"),
        ("GET", "/api/healthcheck/"),
        ("GET", "/api/health/liveness"),
        ("GET", "/api/health/readiness"),
        ("GET", "/api/health/db"),
        ("GET", "/api/health/saf"),
        ("GET", "/api/health/ready"),
        ("GET", "/api/health/system"),
        ("GET", "/api/health/alarms"),
        ("GET", "/api/system/timezone"),
    }
)
PUBLIC_REST_PREFIXES: tuple[str, ...] = ()
AUTHENTICATED_ALWAYS_REST = frozenset(
    {
        ("POST", "/api/users/logout"),
        ("POST", "/api/users/change_password"),
        ("GET", "/api/authz/me"),
        ("POST", "/api/settings/client-preference"),
    }
)


def normalize_api_path(path: str) -> str:
    if not path:
        return "/"
    normalized = "/" + str(path).lstrip("/")
    if len(normalized) > 1:
        normalized = normalized.rstrip("/")
    return normalized or "/"


def _norm_method_path(method: str, path: str) -> tuple[str, str]:
    method_u = str(method or "").upper()
    if method_u == "HEAD":
        method_u = "GET"
    return method_u, normalize_api_path(path)


_PUBLIC_REST_NORM = frozenset(_norm_method_path(method, path) for method, path in PUBLIC_REST_EXACT)
_AUTHENTICATED_ALWAYS_NORM = frozenset(
    _norm_method_path(method, path) for method, path in AUTHENTICATED_ALWAYS_REST
)


def is_public_rest(method: str, path: str) -> bool:
    pair = _norm_method_path(method, path)
    if pair in _PUBLIC_REST_NORM:
        return True
    method_u, exact = pair
    raw = str(path or "")
    if (method_u, raw) in PUBLIC_REST_EXACT:
        return True
    for prefix in PUBLIC_REST_PREFIXES:
        base = str(prefix or "").rstrip("/")
        if not base:
            continue
        if exact == base or exact.startswith(base + "/") or raw.startswith(prefix):
            return True
    return False


def is_session_always_rest(method: str, path: str) -> bool:
    pair = _norm_method_path(method, path)
    if pair in _AUTHENTICATED_ALWAYS_NORM:
        return True
    method_u = pair[0]
    return (method_u, str(path or "")) in AUTHENTICATED_ALWAYS_REST


def rest_key_is_acl_governed(resource_key: str) -> bool:
    """False for public or session-only REST keys (middleware skips evaluate)."""
    key = str(resource_key or "")
    if not key.startswith("rest:"):
        return True
    method, _, path = key[5:].partition(" ")
    if str(method).upper() in {"OPTIONS", "HEAD"}:
        return False
    if not path:
        return True
    return not (is_public_rest(method, path) or is_session_always_rest(method, path))


def collect_rest_keys(flask_app: Any | None = None) -> list[str]:
    from .app_hooks import extra_rest_keys

    app = flask_app
    if app is None:
        try:
            from flask import current_app

            app = current_app._get_current_object()
        except Exception:
            app = None
    keys: set[str] = set(extra_rest_keys())
    if app is not None:
        try:
            for rule in app.url_map.iter_rules():
                pattern = str(rule.rule or "")
                if "/api/" not in pattern and not pattern.startswith("/api"):
                    continue
                methods = set(rule.methods or ()) - {"OPTIONS", "HEAD"}
                for method in sorted(methods):
                    keys.add(rest_resource_key(method, pattern))
        except Exception:
            pass
    return sorted(key for key in keys if rest_key_is_acl_governed(key))


def all_resource_keys(flask_app: Any | None = None) -> list[str]:
    return list(HMI_VIEW_KEYS) + collect_rest_keys(flask_app)


def catalog_tree(flask_app: Any | None = None) -> dict:
    groups: dict[str, list[dict]] = {}
    for item in HMI_VIEWS:
        groups.setdefault(item["group"], []).append(
            {
                "resource_key": item["key"],
                "path": item["path"],
                "kind": "hmi",
                "actions": list(ACTIONS),
            }
        )
    rest_groups: dict[str, list[dict]] = {}
    for key in collect_rest_keys(flask_app):
        path = key.split(" ", 1)[-1] if " " in key else key
        parts = [p for p in path.split("/") if p]
        bucket = parts[1] if len(parts) > 1 else "other"
        rest_groups.setdefault(bucket, []).append(
            {
                "resource_key": key,
                "kind": "rest",
                "actions": [rest_action_from_key(key)],
            }
        )
    return {
        "hmi": groups,
        "rest": rest_groups,
        "actions": list(ACTIONS),
        "effects": ["allow", "deny", "default"],
    }
