# -*- coding: utf-8 -*-
"""Registro de tokens API/HMI por edge cuando multi-edge está activo.

Con historiador compartido, ``Users.token`` solo puede guardar un valor global.
Esta tabla permite una sesión activa por usuario **y por nodo**, de modo que el
login en Linea1 no invalide el socket de Linea2.
"""
from __future__ import annotations

import logging
from typing import Optional

from ..dbmodels.user_api_sessions import UserApiSession, utc_now

_LOGGER = logging.getLogger("pyautomation.user_api_sessions")


def _multi_edge_enabled() -> bool:
    try:
        from ..node_scope import get_node_scope

        return bool(get_node_scope().enabled)
    except Exception:
        return False


def _node_identity() -> tuple[str, str]:
    try:
        from .hmi_session_store import node_identity

        return node_identity()
    except Exception:
        return "local", "local"


def _get_db():
    try:
        from .hmi_session_store import _get_db as get_db

        return get_db()
    except Exception:
        return None


def register_api_session(*, token: str, username: str) -> bool:
    """Persiste el token del edge actual; revoca otros del mismo user+node."""
    if not _multi_edge_enabled():
        return False
    token = (token or "").strip()
    username = (username or "").strip()
    if not token or not username:
        return False
    db = _get_db()
    if db is None:
        return False
    node_id, area = _node_identity()
    now = utc_now()
    try:
        (
            UserApiSession.delete()
            .where(
                (UserApiSession.username == username)
                & (UserApiSession.node_id == node_id)
                & (UserApiSession.token != token)
            )
            .execute()
        )
        UserApiSession.insert(
            token=token,
            username=username,
            node_id=node_id,
            area=area,
            created_at=now,
        ).on_conflict(
            conflict_target=[UserApiSession.token],
            update={
                UserApiSession.username: username,
                UserApiSession.node_id: node_id,
                UserApiSession.area: area,
                UserApiSession.created_at: now,
            },
        ).execute()
        return True
    except Exception:
        _LOGGER.debug("user_api_sessions register failed", exc_info=True)
        return False
    finally:
        try:
            from .hmi_session_store import _close_historian_socket

            _close_historian_socket()
        except Exception:
            pass


def lookup_username(token: str) -> Optional[str]:
    """Devuelve el username asociado al token en este historiador, o None."""
    if not _multi_edge_enabled():
        return None
    token = (token or "").strip()
    if not token:
        return None
    db = _get_db()
    if db is None:
        return None
    try:
        row = UserApiSession.get_or_none(UserApiSession.token == token)
        return row.username if row else None
    except Exception:
        _LOGGER.debug("user_api_sessions lookup failed", exc_info=True)
        return None
    finally:
        try:
            from .hmi_session_store import _close_historian_socket

            _close_historian_socket()
        except Exception:
            pass


def revoke_api_session(token: str) -> None:
    """Elimina un token de la tabla (logout)."""
    token = (token or "").strip()
    if not token:
        return
    db = _get_db()
    if db is None:
        return
    try:
        UserApiSession.delete().where(UserApiSession.token == token).execute()
    except Exception:
        _LOGGER.debug("user_api_sessions revoke failed", exc_info=True)
    finally:
        try:
            from .hmi_session_store import _close_historian_socket

            _close_historian_socket()
        except Exception:
            pass
