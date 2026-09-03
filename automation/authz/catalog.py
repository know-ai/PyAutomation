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


def rest_resource_key(method: str, rule: str) -> str:
    normalized_rule = str(rule or "")
    if normalized_rule and not normalized_rule.startswith("/"):
        normalized_rule = "/" + normalized_rule
    if normalized_rule and not normalized_rule.startswith("/api"):
        normalized_rule = "/api" + normalized_rule
    return f"rest:{str(method or 'GET').upper()} {normalized_rule}"


def default_action(method: str) -> str:
    return "view" if str(method or "").upper() in {"GET", "HEAD"} else "use"


def rest_key_from_request() -> str | None:
    from flask import request

    rule = ""
    if request.url_rule is not None:
        rule = str(request.url_rule.rule or "")
    if not rule:
        rule = str(request.path or "")
    return rest_resource_key(request.method, rule)


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
    if app is None:
        return sorted(keys)
    try:
        for rule in app.url_map.iter_rules():
            pattern = str(rule.rule or "")
            if "/api/" not in pattern and not pattern.startswith("/api"):
                continue
            methods = set(rule.methods or ()) - {"OPTIONS"}
            for method in sorted(methods):
                keys.add(rest_resource_key(method, pattern))
    except Exception:
        return sorted(keys)
    return sorted(keys)


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
                "actions": list(ACTIONS),
            }
        )
    return {
        "hmi": groups,
        "rest": rest_groups,
        "actions": list(ACTIONS),
        "effects": ["allow", "deny", "default"],
    }
