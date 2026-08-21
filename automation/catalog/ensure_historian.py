# -*- coding: utf-8 -*-
"""Ensure historian (PG/MySQL) has users/roles needed for history writes."""
from __future__ import annotations

import logging
import secrets

_LOGGER = logging.getLogger("pyautomation")


def ensure_historian_role(name: str, level: int = 256):
    from ..dbmodels.users import Roles

    role = Roles.read_by_name(name=name)
    if role is not None:
        return role
    try:
        role, _ = Roles.create(
            name=str(name).upper(),
            level=int(level),
            identifier=secrets.token_hex(4),
        )
        return role
    except Exception:
        _LOGGER.debug("ensure_historian_role failed name=%s", name, exc_info=True)
        return Roles.read_by_name(name=name)


def ensure_historian_user(user):
    """Return a ``Users`` Peewee row for ``user``, creating it if needed.

    Never raises. Returns None if the historian cannot accept the user yet
    (e.g. role missing and cannot be created).
    """
    from ..dbmodels.users import Users

    username = getattr(user, "username", None)
    if not username:
        return None
    existing = Users.read_by_username(username=username)
    if existing is not None:
        return existing
    role_obj = getattr(user, "role", None)
    role_name = getattr(role_obj, "name", None) or "sudo"
    role_level = getattr(role_obj, "level", None)
    if role_level is None:
        role_level = 0 if str(role_name).upper() == "SUDO" else 256
    ensure_historian_role(role_name, int(role_level))
    try:
        created, message = Users.create(user)
        if created is not None:
            return created
        # Username/email race: re-read
        existing = Users.read_by_username(username=username)
        if existing is not None:
            return existing
        _LOGGER.debug("ensure_historian_user create failed user=%s msg=%s", username, message)
    except Exception:
        _LOGGER.debug("ensure_historian_user failed user=%s", username, exc_info=True)
    return Users.read_by_username(username=username)
