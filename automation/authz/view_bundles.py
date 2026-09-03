# -*- coding: utf-8 -*-
"""REST endpoints implied by HMI view grants.

Granting ``view`` on an HMI screen allows all *read* endpoints the screen needs
(including POST filter/query). Granting ``use`` on the screen allows *write*
endpoints. Explicit REST deny/allow grants still take precedence (see engine).
"""
from __future__ import annotations

from typing import Iterable

# (HTTP method, path prefix/exact — same rules as seed._path_is)
RestEntry = tuple[str, str]
ViewBundle = dict[str, list[RestEntry]]

_SHARED_AREA_READ: list[RestEntry] = [
    ("GET", "/api/system/nodes"),
    ("GET", "/api/tags/catalog"),
]
_SHARED_TIMEZONE: list[RestEntry] = [
    ("GET", "/api/system/timezone"),
]

VIEW_REST_BUNDLES: dict[str, ViewBundle] = {
    "hmi:view.events": {
        "read": [
            ("POST", "/api/events/filter_by"),
            ("GET", "/api/events"),
            ("GET", "/api/users"),
            *_SHARED_AREA_READ,
            *_SHARED_TIMEZONE,
        ],
        "write": [
            ("POST", "/api/logs/add"),
        ],
    },
    "hmi:view.operational-logs": {
        "read": [
            ("POST", "/api/logs/filter_by"),
            ("GET", "/api/logs"),
            ("GET", "/api/users"),
            ("GET", "/api/alarms"),
            *_SHARED_AREA_READ,
            *_SHARED_TIMEZONE,
        ],
        "write": [
            ("POST", "/api/logs/add"),
        ],
    },
    "hmi:view.alarms.summary": {
        "read": [
            ("POST", "/api/alarms/summary/filter_by"),
            ("GET", "/api/alarms/summary"),
            *_SHARED_AREA_READ,
            *_SHARED_TIMEZONE,
        ],
        "write": [
            ("POST", "/api/logs/add"),
        ],
    },
    "hmi:view.alarms.definitions": {
        "read": [
            ("GET", "/api/alarms"),
            ("GET", "/api/tags"),
            ("GET", "/api/health/system"),
        ],
        "write": [
            ("POST", "/api/alarms/add"),
            ("POST", "/api/alarms/update"),
            ("DELETE", "/api/alarms/delete"),
            ("POST", "/api/alarms/shelve"),
            ("POST", "/api/alarms/acknowledge"),
            ("POST", "/api/alarms/acknowledge_all"),
            ("POST", "/api/alarms/unshelve"),
        ],
    },
    "hmi:view.tags.definitions": {
        "read": [
            ("GET", "/api/tags"),
            ("GET", "/api/opcua/clients"),
            ("GET", "/api/opcua/clients/tree"),
            ("GET", "/api/opcua/clients/tree_children"),
            ("GET", "/api/opcua/clients/variables"),
            ("POST", "/api/opcua/clients/attrs"),
            ("GET", "/api/health/system"),
        ],
        "write": [
            ("POST", "/api/tags/add"),
            ("POST", "/api/tags/update"),
            ("DELETE", "/api/tags/delete"),
            ("POST", "/api/tags/write_value"),
        ],
    },
    "hmi:view.tags.datalogger": {
        "read": [
            ("GET", "/api/tags/catalog"),
            ("POST", "/api/tags/get_tabular_data"),
            *_SHARED_AREA_READ,
            *_SHARED_TIMEZONE,
        ],
        "write": [],
    },
    "hmi:view.tags.trends": {
        "read": [
            ("GET", "/api/tags/catalog"),
            ("POST", "/api/tags/query_trends"),
            *_SHARED_AREA_READ,
            *_SHARED_TIMEZONE,
        ],
        "write": [],
    },
    "hmi:view.real-time-trends": {
        "read": [
            ("GET", "/api/settings/workspace/realtime-trends"),
            ("POST", "/api/tags/list"),
        ],
        "write": [
            ("PUT", "/api/settings/workspace/realtime-trends"),
        ],
    },
    "hmi:view.machines.summary": {
        "read": [
            ("GET", "/api/machines"),
        ],
        "write": [
            ("PUT", "/api/machines"),
        ],
    },
    "hmi:view.machines.detailed": {
        "read": [
            ("GET", "/api/machines"),
            ("POST", "/api/tags/list"),
            ("GET", "/api/health/node"),
            ("GET", "/api/health/system"),
        ],
        "write": [
            ("PUT", "/api/machines"),
            ("POST", "/api/machines"),
        ],
    },
    "hmi:view.communications.clients": {
        "read": [
            ("GET", "/api/opcua/clients"),
            ("GET", "/api/opcua/clients/tree"),
            ("GET", "/api/opcua/clients/tree_children"),
            ("GET", "/api/opcua/clients/variables"),
            ("POST", "/api/opcua/clients/values"),
            ("POST", "/api/opcua/clients/attrs"),
        ],
        "write": [
            ("POST", "/api/opcua/clients/add"),
            ("PUT", "/api/opcua/clients/update"),
            ("DELETE", "/api/opcua/clients/remove"),
        ],
    },
    "hmi:view.communications.server": {
        "read": [
            ("GET", "/api/opcua/server/attrs"),
        ],
        "write": [
            ("PUT", "/api/opcua/server/attrs/update"),
        ],
    },
    "hmi:view.performance": {
        "read": [
            ("GET", "/api/health/node"),
            ("GET", "/api/alarms"),
            ("GET", "/api/tags/filter/status"),
        ],
        "write": [
            ("PUT", "/api/settings/performance"),
            ("POST", "/api/admin"),
            ("POST", "/api/alarms/acknowledge"),
            ("POST", "/api/alarms/shelve"),
            ("POST", "/api/alarms/unshelve"),
        ],
    },
    "hmi:view.settings": {
        "read": [
            ("GET", "/api/settings"),
        ],
        "write": [
            ("PUT", "/api/settings"),
            ("POST", "/api/settings/import_config"),
        ],
    },
    "hmi:view.database": {
        "read": [
            ("GET", "/api/database/config"),
            ("GET", "/api/database/connected"),
            ("GET", "/api/health/db"),
        ],
        "write": [
            ("POST", "/api/database/connect"),
            ("POST", "/api/database/disconnect"),
            ("POST", "/api/system/reconnect_db"),
        ],
    },
    "hmi:view.user-management": {
        "read": [
            ("GET", "/api/users"),
            ("GET", "/api/users/roles"),
        ],
        "write": [
            ("POST", "/api/users/change_password"),
            ("POST", "/api/users/reset_password"),
            ("POST", "/api/users/update_role"),
            ("POST", "/api/users/roles/add"),
        ],
    },
    "hmi:view.authz": {
        "read": [
            ("GET", "/api/authz/catalog"),
            ("GET", "/api/users/roles"),
            ("GET", "/api/users"),
            ("POST", "/api/authz/preview"),
        ],
        "write": [
            ("PUT", "/api/authz/grants"),
        ],
    },
    "hmi:view.lds-dashboard": {
        "read": [
            ("GET", "/api/LDS"),
            ("GET", "/api/hmi/extensions"),
        ],
        "write": [
            ("POST", "/api/LDS"),
        ],
    },
}


def _path_is(path: str, *prefixes: str) -> bool:
    normalized = str(path or "").rstrip("/")
    for prefix in prefixes:
        base = str(prefix or "").rstrip("/")
        if not base:
            continue
        if normalized == base or normalized.startswith(base + "/") or normalized.startswith(base + "<"):
            return True
    return False


def endpoint_matches(method: str, path: str, entry: RestEntry) -> bool:
    em, ep = entry
    if str(method or "").upper() != str(em or "").upper():
        return False
    return _path_is(path, ep)


def _entries_matching(method: str, path: str, entries: Iterable[RestEntry]) -> bool:
    return any(endpoint_matches(method, path, entry) for entry in entries)


def views_implying_rest(method: str, path: str, rest_action: str) -> list[tuple[str, str]]:
    """Return (view_key, required_hmi_action) pairs that cover this REST call."""
    method_u = str(method or "").upper()
    action = str(rest_action or "").strip().lower()
    implied: list[tuple[str, str]] = []
    for view_key, bundle in VIEW_REST_BUNDLES.items():
        if _entries_matching(method_u, path, bundle.get("read", [])):
            if action == "view" and method_u in {"GET", "HEAD"}:
                implied.append((view_key, "view"))
            elif action == "use" and method_u not in {"GET", "HEAD"}:
                implied.append((view_key, "view"))
        if action == "use" and _entries_matching(method_u, path, bundle.get("write", [])):
            implied.append((view_key, "use"))
    return implied
