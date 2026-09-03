# -*- coding: utf-8 -*-
"""Blueprint before_request: public allowlist, else token + ACL."""
from __future__ import annotations

from flask import request

from ..utils.system_user import is_system_username, system_user_path_allowed
from .catalog import default_action, rest_key_from_request
from .engine import evaluate

_PUBLIC_EXACT = frozenset(
    {
        ("POST", "/api/users/login"),
        ("POST", "/api/users/signup"),
        ("GET", "/api/health/ping"),
        ("GET", "/api/healthcheck/"),
        ("GET", "/api/health/liveness"),
        ("GET", "/api/health/readiness"),
        ("GET", "/api/health/db"),
        ("GET", "/api/health/saf"),
        ("GET", "/api/health/system"),
        ("GET", "/api/system/timezone"),
    }
)
_PUBLIC_PREFIXES = ()
_AUTHENTICATED_ALWAYS = frozenset(
    {
        ("POST", "/api/users/logout"),
        ("POST", "/api/users/change_password"),
        ("GET", "/api/authz/me"),
        ("GET", "/api/users/credentials_are_valid"),
    }
)


def _normalize_path(path: str) -> str:
    if not path:
        return "/"
    normalized = "/" + str(path).lstrip("/")
    if len(normalized) > 1:
        normalized = normalized.rstrip("/")
    return normalized or "/"


def _is_public(method: str, path: str) -> bool:
    method_u = str(method or "").upper()
    exact = _normalize_path(path)
    if (method_u, exact) in _PUBLIC_EXACT:
        return True
    if (method_u, path) in _PUBLIC_EXACT:
        return True
    for prefix in _PUBLIC_PREFIXES:
        if exact == prefix.rstrip("/") or exact.startswith(prefix.rstrip("/") + "/") or path.startswith(prefix):
            return True
    return False


def _is_session_always(method: str, path: str) -> bool:
    method_u = str(method or "").upper()
    exact = _normalize_path(path)
    return (method_u, exact) in _AUTHENTICATED_ALWAYS


def _extract_token() -> str | None:
    if "X-API-KEY" in request.headers:
        return request.headers["X-API-KEY"]
    if "Authorization" in request.headers:
        return request.headers["Authorization"].split("Token ")[-1]
    return None


def enforce_api_authz():
    if request.method == "OPTIONS":
        return None
    path = request.path or ""
    try:
        from ..extensions.docs_auth import is_docs_path

        if is_docs_path(path):
            return None
    except Exception:
        pass
    if _is_public(request.method, path):
        return None
    from ..extensions.api import Api

    token = _extract_token()
    user, err, status = Api._resolve_session_user(token or "")
    if err is not None:
        return err, status
    if user is None:
        return {"message": "Invalid token", "code": "SESSION_INVALID"}, 401
    if is_system_username(getattr(user, "username", None)):
        if not system_user_path_allowed(path):
            return {
                "message": "System user is restricted to user management",
                "code": "SYSTEM_USER_RESTRICTED",
            }, 403
        return None
    if _is_session_always(request.method, path):
        return None
    resource_key = rest_key_from_request()
    action = default_action(request.method)
    if not resource_key or not evaluate(user, resource_key, action):
        return {
            "message": "Forbidden",
            "code": "AUTHZ_DENIED",
            "resource": resource_key,
            "action": action,
        }, 403
    return None
