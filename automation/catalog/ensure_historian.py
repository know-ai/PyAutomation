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
    (e.g. role missing and cannot be created, or link is mid-reconnect).
    """
    from ..dbmodels.users import Users
    from ..utils.db_io import is_stale_historian_handle

    username = getattr(user, "username", None)
    if not username:
        return None
    try:
        existing = Users.read_by_username(username=username)
        if existing is not None:
            return existing
    except Exception as exc:
        if is_stale_historian_handle(exc):
            _LOGGER.debug(
                "ensure_historian_user skipped (stale link) user=%s",
                username,
                exc_info=True,
            )
            return None
        _LOGGER.debug("ensure_historian_user read failed user=%s", username, exc_info=True)
        return None
    role_obj = getattr(user, "role", None)
    role_name = getattr(role_obj, "name", None) or "sudo"
    role_level = getattr(role_obj, "level", None)
    if role_level is None:
        role_level = 0 if str(role_name).upper() == "SUDO" else 256
    try:
        ensure_historian_role(role_name, int(role_level))
    except Exception:
        _LOGGER.debug("ensure_historian_role failed name=%s", role_name, exc_info=True)
    try:
        created, message = Users.create(user)
        if created is not None:
            return created
        # Username/email race: re-read
        existing = Users.read_by_username(username=username)
        if existing is not None:
            return existing
        _LOGGER.debug("ensure_historian_user create failed user=%s msg=%s", username, message)
    except Exception as exc:
        if is_stale_historian_handle(exc):
            _LOGGER.debug(
                "ensure_historian_user create skipped (stale link) user=%s",
                username,
                exc_info=True,
            )
            return None
        _LOGGER.debug("ensure_historian_user failed user=%s", username, exc_info=True)
    try:
        return Users.read_by_username(username=username)
    except Exception:
        return None


def resolve_historian_user_row(user):
    """Resolve remote ``Users`` FK for history writes. Never raises.

    Prefer an existing remote row; only then ensure/create. Stale sockets
    (``connection already closed``) return None so the SAF outbox can keep
    PENDING without aborting the caller.
    """
    from ..dbmodels.users import Users
    from ..utils.db_io import is_stale_historian_handle

    if user is None:
        return None
    username = getattr(user, "username", None)
    if not username:
        return None
    try:
        row = Users.read_by_username(username=username)
        if row is not None:
            return row
    except Exception as exc:
        if is_stale_historian_handle(exc):
            return None
        _LOGGER.debug("resolve_historian_user_row read failed user=%s", username, exc_info=True)
        return None
    return ensure_historian_user(user)
