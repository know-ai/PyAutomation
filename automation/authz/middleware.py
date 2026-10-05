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

_CONFIRMATION_OK = object()


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
    confirmed = _confirmed_operator(resource_key, action)
    if confirmed is _CONFIRMATION_OK:
        return None
    if confirmed is not None:
        return confirmed
    if not resource_key or not evaluate(user, resource_key, action):
        return {
            "message": "Forbidden",
            "code": "AUTHZ_DENIED",
            "resource": resource_key,
            "action": action,
        }, 403
    return None


def _confirmed_operator(resource_key: str | None, action: str):
    """When the station policy is on, authorize acknowledge and restart as the confirming operator."""
    try:
        from ..utils.operator_confirmation import (
            action_requires_confirmation,
            consume_confirmation_token,
            policy_enabled,
        )
    except Exception:
        return None
    if not policy_enabled():
        return None
    payload = request.get_json(silent=True) if request.is_json else None
    target_state = None
    if isinstance(payload, dict):
        target_state = payload.get("to")
    if not action_requires_confirmation(request.method, request.path, target_state):
        return None
    token = request.headers.get("X-Operator-Confirmation")
    if not token:
        return {
            "message": "Operator confirmation required",
            "code": "CONFIRMATION_REQUIRED",
        }, 403
    try:
        from .. import server

        secret = server.config.get("AUTOMATION_APP_SECRET_KEY") or ""
    except Exception:
        secret = ""
    username = consume_confirmation_token(
        token,
        method=request.method,
        path=request.path,
        secret=secret,
        target_state=None if target_state is None else str(target_state),
    )
    if not username:
        return {
            "message": "Operator confirmation is invalid",
            "code": "CONFIRMATION_INVALID",
        }, 403
    from ..modules.users.users import Users

    operator = Users().get_by_username(username=username)
    if operator is None or not evaluate(operator, resource_key, action):
        return {
            "message": "Forbidden",
            "code": "AUTHZ_DENIED",
            "resource": resource_key,
            "action": action,
        }, 403
    try:
        from flask import g

        g.confirmed_operator = operator
    except Exception:
        return {
            "message": "Operator confirmation is invalid",
            "code": "CONFIRMATION_INVALID",
        }, 403
    return _CONFIRMATION_OK


def _extract_token() -> str | None:
    if "X-API-KEY" in request.headers:
        return request.headers["X-API-KEY"]
    if "Authorization" in request.headers:
        return request.headers["Authorization"].split("Token ")[-1]
    return None
