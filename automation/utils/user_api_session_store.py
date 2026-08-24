# -*- coding: utf-8 -*-
"""Registro de tokens API/HMI por edge cuando multi-edge está activo.

Con historiador compartido, ``Users.token`` solo puede guardar un valor global.
Esta tabla permite una sesión activa por usuario **y por nodo**, de modo que el
login en Linea1 no invalide el socket de Linea2.

Cada edge también espeja sesiones activas en el catálogo SQLite local para que
Socket.IO y la API sigan autenticando cuando PostgreSQL está caído.
"""
from __future__ import annotations

import logging
from typing import Optional

from ..dbmodels.user_api_sessions import UserApiSession, utc_now

_LOGGER = logging.getLogger("pyautomation.user_api_sessions")


def multi_edge_sessions_enabled() -> bool:
    """True when API/HMI sessions are tracked per edge in ``user_api_sessions``."""
    try:
        from ..node_scope import get_node_scope

        return bool(get_node_scope().enabled)
    except Exception:
        return False


def _multi_edge_enabled() -> bool:
    return multi_edge_sessions_enabled()


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


def _mirror_local_session(*, token: str, username: str, node_id: str, area: str) -> bool:
    """Persist active token in edge-local catalog.db (survives historian outage)."""
    try:
        from ..catalog.local_provider import LocalCatalogProvider

        provider = LocalCatalogProvider()
        for row in provider.read_all("user_api_sessions"):
            if (
                row.get("username") == username
                and row.get("node_id") == node_id
                and row.get("token") != token
            ):
                try:
                    provider.delete("user_api_sessions", str(row.get("token") or row.get("_pk")))
                except Exception:
                    pass
        provider.upsert(
            "user_api_sessions",
            {
                "token": token,
                "username": username,
                "node_id": node_id,
                "area": area,
            },
            node_id=node_id,
        )
        return True
    except Exception:
        _LOGGER.debug("local user_api_sessions mirror failed", exc_info=True)
        return False


def _lookup_local_username(token: str) -> Optional[str]:
    token = (token or "").strip()
    if not token:
        return None
    try:
        from ..catalog.local_provider import LocalCatalogProvider

        provider = LocalCatalogProvider()
        row = provider.find_one("user_api_sessions", field="token", value=token)
        if row and row.get("username"):
            return str(row["username"])
        user_row = provider.find_one("users", field="token", value=token)
        if user_row and user_row.get("username"):
            return str(user_row["username"])
    except Exception:
        _LOGGER.debug("local session lookup failed", exc_info=True)
    return None


def _revoke_local_session(token: str) -> None:
    token = (token or "").strip()
    if not token:
        return
    try:
        from ..catalog.local_provider import LocalCatalogProvider

        LocalCatalogProvider().delete("user_api_sessions", token)
    except Exception:
        _LOGGER.debug("local user_api_sessions revoke failed", exc_info=True)


def register_api_session(*, token: str, username: str) -> bool:
    """Persiste el token del edge actual; revoca otros del mismo user+node."""
    token = (token or "").strip()
    username = (username or "").strip()
    if not token or not username:
        return False
    node_id, area = _node_identity()
    local_ok = _mirror_local_session(
        token=token, username=username, node_id=node_id, area=area
    )
    pg_ok = False
    if not _multi_edge_enabled():
        return local_ok
    db = _get_db()
    if db is None:
        return local_ok
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
        pg_ok = True
    except Exception:
        _LOGGER.debug("user_api_sessions register failed", exc_info=True)
    finally:
        try:
            from .hmi_session_store import _close_historian_socket

            _close_historian_socket()
        except Exception:
            pass
    return local_ok or pg_ok


def list_api_sessions() -> list[tuple[str, str]]:
    """Return ``(token, username)`` pairs for all edges (session rebind after DB reconnect)."""
    pairs: list[tuple[str, str]] = []
    seen: set[str] = set()
    if _multi_edge_enabled():
        db = _get_db()
        if db is not None:
            try:
                for row in UserApiSession.select(
                    UserApiSession.token, UserApiSession.username
                ):
                    token = str(row.token)
                    if token not in seen:
                        pairs.append((token, str(row.username)))
                        seen.add(token)
            except Exception:
                _LOGGER.debug("user_api_sessions list failed", exc_info=True)
            finally:
                try:
                    from .hmi_session_store import _close_historian_socket

                    _close_historian_socket()
                except Exception:
                    pass
    try:
        from ..catalog.local_provider import LocalCatalogProvider

        for row in LocalCatalogProvider().read_all("user_api_sessions"):
            token = str(row.get("token") or "")
            username = str(row.get("username") or "")
            if token and token not in seen:
                pairs.append((token, username))
                seen.add(token)
    except Exception:
        pass
    return pairs


def lookup_username(token: str) -> Optional[str]:
    """Devuelve el username asociado al token (historiador o catálogo local)."""
    token = (token or "").strip()
    if not token:
        return None
    db = _get_db()
    if db is not None:
        try:
            row = UserApiSession.get_or_none(UserApiSession.token == token)
            if row:
                return row.username
        except Exception:
            _LOGGER.debug("user_api_sessions lookup failed", exc_info=True)
        finally:
            try:
                from .hmi_session_store import _close_historian_socket

                _close_historian_socket()
            except Exception:
                pass
    return _lookup_local_username(token)


def revoke_api_session(token: str) -> None:
    """Elimina un token de la tabla (logout)."""
    token = (token or "").strip()
    if not token:
        return
    _revoke_local_session(token)
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


def activate_user_from_offline_token(token: str):
    """Restore in-memory user from local session registry when historian is down."""
    username = _lookup_local_username(token)
    if not username:
        return None
    try:
        from ..catalog.hydrate import fill_roles_from_local, fill_users_from_local
        from ..modules.users.users import Users

        users = Users()
        fill_roles_from_local()
        fill_users_from_local()
        mem = users.get_by_username(username=username)
        if mem is None:
            return None
        carrier = type("_SessionRow", (), {"username": username})()
        return users.activate_session_from_db_record(carrier, token=token)
    except Exception:
        _LOGGER.debug("offline session activate failed", exc_info=True)
        return None
