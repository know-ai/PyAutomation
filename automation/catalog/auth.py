# -*- coding: utf-8 -*-
"""Login against the local catalog mirror when the historian is down."""
from __future__ import annotations

import logging
import secrets

from werkzeug.security import check_password_hash, generate_password_hash

from .hydrate import fill_roles_from_local, fill_users_from_local
from .local_provider import LocalCatalogProvider

_LOGGER = logging.getLogger("pyautomation")


def login_local(password: str, username: str = "", email: str = ""):
    """Return (User, message) or (None, message). Always mints a session token."""
    try:
        fill_roles_from_local()
        fill_users_from_local()
        rows = LocalCatalogProvider().read_all("users")
        user_row = None
        for row in rows:
            if username and row.get("username") == username:
                user_row = row
                break
            if email and row.get("email") == email:
                user_row = row
                break
        if user_row is None:
            return None, "Invalid Username or Email"
        hashed = user_row.get("password") or ""
        if not check_password_hash(str(hashed), password) and hashed != password:
            return None, "Invalid credentials"

        from ..modules.users.users import users

        uname = user_row.get("username")
        mem = users.get_by_username(uname) if uname else None
        if mem is None:
            fill_users_from_local()
            mem = users.get_by_username(uname) if uname else None
        if mem is None:
            return None, "Invalid credentials"

        # Mint session token (same shape as Auth.login). Do not require historian.
        token = generate_password_hash(secrets.token_hex(4))
        mem.token = token
        replaced = users._revoke_other_sessions(mem)
        setattr(mem, "_login_replaced_session", replaced)
        users.active_users[token] = mem

        try:
            pk = user_row.get("_pk") or user_row.get("id")
            payload = dict(user_row)
            payload["token"] = token
            if pk is not None:
                payload["_pk"] = pk
            LocalCatalogProvider().upsert(
                "users",
                payload,
                node_id=user_row.get("node_id"),
            )
        except Exception:
            _LOGGER.debug("local catalog token persist skipped", exc_info=True)

        return mem, "Login successful (local catalog)"
    except Exception:
        _LOGGER.debug("local catalog login failed", exc_info=True)
        return None, "Local catalog authentication failed"
