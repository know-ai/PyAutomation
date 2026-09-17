# -*- coding: utf-8 -*-
"""Fail-closed ACL evaluator.

Precedence: deny user > allow user > deny role > allow role > deny.
"""
from __future__ import annotations

from . import store
from .catalog import (
    ACTIONS,
    HMI_VIEW_KEYS,
    SYSTEM_HMI_VIEWS,
    all_resource_keys,
    rest_action_from_key,
)
from .view_bundles import views_implying_rest


def _user_id(user) -> str | None:
    identifier = getattr(user, "identifier", None)
    if identifier:
        return str(identifier)
    return None


def _role_id(user) -> str | None:
    role = getattr(user, "role", None)
    if role is None:
        return None
    identifier = getattr(role, "identifier", None)
    if identifier:
        return str(identifier)
    return None


def _role_name(user) -> str:
    role = getattr(user, "role", None)
    if role is None:
        return ""
    return str(getattr(role, "name", "") or "").strip().lower()


def _is_integrator(user) -> bool:
    return _role_name(user) == "integrator"


def _direct_grant(user, resource_key: str, action: str) -> bool | None:
    """Explicit allow/deny from store. None = no explicit grant."""
    action_norm = str(action or "").strip().lower()
    user_effect = store.lookup("user", _user_id(user), resource_key, action_norm)
    if user_effect == "deny":
        return False
    if user_effect == "allow":
        return True
    role_effect = store.lookup("role", _role_id(user), resource_key, action_norm)
    if role_effect == "deny":
        return False
    if role_effect == "allow":
        return True
    return None


def _implied_by_view_bundle(user, resource_key: str, rest_action: str) -> bool:
    if not str(resource_key or "").startswith("rest:"):
        return False
    body = resource_key[5:]
    method, _, path = body.partition(" ")
    if not path:
        return False
    for view_key, hmi_action in views_implying_rest(method, path, rest_action):
        grant = _direct_grant(user, view_key, hmi_action)
        if grant is True:
            return True
    return False


def evaluate(user, resource_key: str, action: str) -> bool:
    if user is None or not resource_key:
        return False
    action_norm = str(action or "").strip().lower()
    if action_norm not in ACTIONS:
        return False
    # Integrator is all-allow at runtime. Seed rows can lag behind new HMI
    # views (e.g. view missing while use exists) and the sidebar only checks view.
    if _is_integrator(user):
        return True
    direct = _direct_grant(user, resource_key, action_norm)
    if direct is True:
        return True
    if direct is False:
        return False
    if _implied_by_view_bundle(user, resource_key, action_norm):
        return True
    return False


def _pack_views(keys: list[str], user) -> dict[str, list[str]]:
    packed: dict[str, list[str]] = {}
    for key in keys:
        allowed = [action for action in ACTIONS if evaluate(user, key, action)]
        if allowed:
            packed[key] = allowed
    return packed


def _pack_rest(keys: list[str], user) -> dict[str, bool]:
    """REST: one boolean per resource (true = can invoke that METHOD+path)."""
    packed: dict[str, bool] = {}
    for key in keys:
        packed[key] = bool(evaluate(user, key, rest_action_from_key(key)))
    return packed


def permissions_for(user, flask_app=None) -> dict:
    """Effective permissions.

    ``views`` keep ``view``/``use`` lists (embedded HMI menu and mutate).
    ``rest`` is ``resource_key → bool`` (invoke that METHOD+path or not).
    """
    if user is None:
        return {"views": {}, "rest": {}}
    from ..utils.system_user import is_system_username

    if is_system_username(getattr(user, "username", None)):
        views = {key: list(ACTIONS) for key in SYSTEM_HMI_VIEWS}
        return {"views": views, "rest": {}}
    keys = all_resource_keys(flask_app)
    rest_keys = [key for key in keys if str(key).startswith("rest:")]
    if _is_integrator(user):
        views = {
            key: list(ACTIONS)
            for key in keys
            if key in HMI_VIEW_KEYS or str(key).startswith("hmi:")
        }
        return {"views": views, "rest": {key: True for key in rest_keys}}
    views = _pack_views(
        [key for key in keys if key in HMI_VIEW_KEYS or key.startswith("hmi:")],
        user,
    )
    return {"views": views, "rest": _pack_rest(rest_keys, user)}
