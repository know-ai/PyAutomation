# -*- coding: utf-8 -*-
"""Blueprint before_request: public allowlist, else token + ACL."""
from __future__ import annotations

from flask import request

from ..utils.system_user import is_system_username, system_user_path_allowed
from .catalog import (
    default_action,
    is_public_rest,
    is_session_always_rest,
    rest_key_from_request,
)
from .engine import evaluate


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
    if is_public_rest(request.method, path):
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
    if is_session_always_rest(request.method, path):
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


def _extract_token() -> str | None:
    if "X-API-KEY" in request.headers:
        return request.headers["X-API-KEY"]
    if "Authorization" in request.headers:
        return request.headers["Authorization"].split("Token ")[-1]
    return None
