# -*- coding: utf-8 -*-
"""Role-assignment rules: sudo is untouchable; only system assigns integrator."""
from __future__ import annotations

from ..utils.system_user import is_system_username

_SUDO = "sudo"
_INTEGRATOR = "integrator"


def validate_role_assignment(actor, target_user, new_role_name: str):
    """Return None if allowed, else ``(payload, http_status)``."""
    if actor is None:
        return {"message": "Invalid token or user not found"}, 401
    if target_user is None:
        return {"message": "User not found"}, 400

    target_username = getattr(target_user, "username", None)
    if is_system_username(target_username):
        return {"message": "Cannot change the system user role", "code": "AUTHZ_SYSTEM_ROLE_LOCKED"}, 403

    new_name = str(new_role_name or "").strip().lower()
    if new_name == _SUDO:
        return {"message": "Cannot assign sudo", "code": "AUTHZ_SUDO_LOCKED"}, 403

    actor_name = getattr(actor, "username", None)
    if new_name == _INTEGRATOR and not is_system_username(actor_name):
        return {
            "message": "Only the system user can assign integrator",
            "code": "AUTHZ_INTEGRATOR_RESTRICTED",
        }, 403

    actor_role = getattr(actor, "role", None)
    target_role = getattr(target_user, "role", None)
    actor_level = getattr(actor_role, "level", 256) if actor_role is not None else 256
    target_level = getattr(target_role, "level", 256) if target_role is not None else 256
    if target_level < actor_level:
        return {
            "message": f"You cannot change roles of users with role level lower than {actor_level}"
        }, 400
    return None
