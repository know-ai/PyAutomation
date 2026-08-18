# -*- coding: utf-8 -*-
"""Eternal Connections Directive — one Database instance, counted sockets, closed requests.

Peewee stores the TCP socket in ``threading.local`` (greenlet-local under gevent).
A single ``PostgresqlDatabase`` object can still open N sockets: one per greenlet
or native thread that calls ``connect()`` / ``execute_sql()`` and never ``close()``.

Running Peewee ``connect()`` / ``SELECT 1`` on the gevent hub threadpool is the
worst case: each pool thread gets its own Peewee local and never returns it.
Probes must use a throwaway ``psycopg2`` connection that is closed in ``finally``.
"""
from __future__ import annotations

import logging
import os
import hashlib
import threading
from contextlib import contextmanager
from typing import Any, Iterator

from peewee import MySQLDatabase, OperationalError, PostgresqlDatabase

from .db_io import apply_remote_db_kwargs, connect_timeout_s, probe_timeout_s, run_uncooperative_db_call

_LOGGER = logging.getLogger("pyautomation")
APPLICATION_NAME = "PyAutomationIO"
APPLICATION_NAME_PREFIX = "PyAutomationIO"
DEFAULT_CONNECTIONS_ALERT = 6
_CONNECT_GATE = threading.local()


def historian_connect_forced() -> bool:
    """True while ``set_db`` / reconnect is allowed to call libpq on purpose."""
    return bool(getattr(_CONNECT_GATE, "forced", False))


@contextmanager
def force_historian_connect() -> Iterator[None]:
    """Permit ``Tracked*._connect`` even during the dead-peer cooldown."""
    _CONNECT_GATE.forced = True
    try:
        yield
    finally:
        _CONNECT_GATE.forced = False


def _historian_known_dead() -> bool:
    """True when this process already failed the bound historian link.

    A missing handle (first boot, no previous connection) is not "known dead":
    ``set_db`` must still be allowed to try. A leftover Peewee object with
    ``_db_live is False`` must not open libpq from the CVT / LDS hot path.
    """
    try:
        from automation import PyAutomation

        app = PyAutomation()
    except Exception:
        return False
    if historian_connect_forced():
        return False
    return bool(getattr(app, "_db", None) is not None) and not bool(
        getattr(app, "_db_live", True)
    )


def is_acquisition_cycle() -> bool:
    """True on state-machine scheduler threads (``SM-*`` / StateMachineWorker)."""
    name = threading.current_thread().name or ""
    return name.startswith("SM-") or name in {
        "StateMachineWorker",
        "AsyncStateMachineWorker",
    }


def _mark_app_historian_dead() -> None:
    from .db_io import mark_remote_db_dead

    mark_remote_db_dead()
    try:
        from automation import PyAutomation

        PyAutomation()._db_live = False
    except Exception:
        pass


def _reject_connect_during_outage() -> None:
    from .db_io import probe_is_cooling_down

    if historian_connect_forced():
        return
    if probe_is_cooling_down() or _historian_known_dead():
        raise OperationalError("historian unreachable; connect skipped")
    if is_acquisition_cycle():
        live = False
        try:
            from automation import PyAutomation

            live = bool(getattr(PyAutomation(), "_db_live", False))
        except Exception:
            live = False
        if not live:
            raise OperationalError("historian unreachable; connect skipped")


def _open_tracked_connection(database) -> Any:
    """libpq/MySQL connect. Failures arm the outage gate so the hub is not retried."""
    params = getattr(database, "connect_params", None)
    if isinstance(params, dict):
        params["application_name"] = historian_application_name()
    try:
        conn = super(type(database), database)._connect()
    except Exception:
        _mark_app_historian_dead()
        raise
    REGISTRY.register(conn, owner=database)
    return conn


def historian_application_name(role: str | None = None) -> str:
    """libpq application_name for this greenlet. Max 63 chars (PostgreSQL)."""
    from ..node_scope import current_node_scope

    def safe(value: str) -> str:
        return "".join(
            ch if ch.isalnum() or ch in "._-" else "_" for ch in value
        ) or "unknown"

    scope = current_node_scope()
    if not scope.enabled:
        return (
            f"{APPLICATION_NAME_PREFIX}:{safe(role)}"
            if role
            else APPLICATION_NAME_PREFIX
        )
    node_id = scope.node_id
    role_name = safe(role or threading.current_thread().name or "unknown")
    # Las conexiones previas a la validación de adquisición conservan el
    # identificador legacy; una identidad configurada siempre usa node + rol.
    name = (
        f"{APPLICATION_NAME_PREFIX}:{safe(node_id)}:{role_name}"
        if node_id
        else f"{APPLICATION_NAME_PREFIX}:unconfigured:{role_name}"
    )
    if len(name) <= 63:
        return name
    digest = hashlib.sha256(name.encode("utf-8")).hexdigest()[:8]
    return f"{name[:54]}-{digest}"


class ConnectionRegistry:
    """Live-socket census keyed by Database instance.

    ``close_all`` on the *previous* handle must not kill sockets that belong
    to the *candidate* opened during reconnect.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._by_owner: dict[int, dict[int, Any]] = {}
        self._instance_id: int | None = None

    def bind_instance(self, database: Any) -> None:
        with self._lock:
            self._instance_id = id(database)

    def register(self, conn: Any, owner: Any | None = None) -> None:
        oid = id(owner) if owner is not None else 0
        with self._lock:
            self._by_owner.setdefault(oid, {})[id(conn)] = conn

    def unregister(self, conn: Any, owner: Any | None = None) -> None:
        with self._lock:
            if owner is not None:
                bucket = self._by_owner.get(id(owner))
                if not bucket:
                    return
                bucket.pop(id(conn), None)
                if not bucket:
                    self._by_owner.pop(id(owner), None)
                return
            for oid, bucket in list(self._by_owner.items()):
                if id(conn) in bucket:
                    bucket.pop(id(conn), None)
                    if not bucket:
                        self._by_owner.pop(oid, None)
                    return

    def count(self) -> int:
        with self._lock:
            return sum(len(bucket) for bucket in self._by_owner.values())

    def instance_id(self) -> int | None:
        with self._lock:
            return self._instance_id

    def close_tracked(self, owner: Any | None = None) -> int:
        with self._lock:
            if owner is None:
                items: list[tuple[int, Any]] = []
                for bucket in self._by_owner.values():
                    items.extend(bucket.items())
                self._by_owner.clear()
            else:
                items = list(self._by_owner.pop(id(owner), {}).items())
        closed = 0
        for _key, conn in items:
            try:
                conn.close()
                closed += 1
            except Exception:
                _LOGGER.debug("tracked historian connection close skipped", exc_info=True)
        return closed

    def close_tracked_except(self, owner: Any, keep: Any | None = None) -> int:
        """Close sockets of ``owner`` except ``keep`` (this greenlet's handle)."""
        keep_id = id(keep) if keep is not None else None
        with self._lock:
            bucket = self._by_owner.get(id(owner), {})
            items = [(key, conn) for key, conn in list(bucket.items()) if key != keep_id]
            for key, _conn in items:
                bucket.pop(key, None)
            if not bucket:
                self._by_owner.pop(id(owner), None)
        closed = 0
        for _key, conn in items:
            try:
                conn.close()
                closed += 1
            except Exception:
                _LOGGER.debug("foreign historian connection close skipped", exc_info=True)
        return closed


REGISTRY = ConnectionRegistry()


def gunicorn_worker_count() -> int:
    for key in ("AUTOMATION_GUNICORN_WORKERS", "WEB_CONCURRENCY"):
        raw = os.environ.get(key)
        if not raw:
            continue
        try:
            return max(1, int(raw))
        except (TypeError, ValueError):
            continue
    return 1


def connections_expected_max() -> int:
    """Idle ceiling: (workers * 2) + 2. One worker → 4 (LoggerWorker + burst)."""
    return gunicorn_worker_count() * 2 + 2


def connections_alert_threshold() -> int:
    raw = os.environ.get("AUTOMATION_DB_CONNECTIONS_ALERT")
    if raw:
        try:
            return max(1, min(int(raw), 256))
        except (TypeError, ValueError):
            pass
    return max(DEFAULT_CONNECTIONS_ALERT, connections_expected_max())


def snapshot_connection_metrics(db: Any | None = None) -> dict[str, Any]:
    client_count = REGISTRY.count()
    expected = connections_expected_max()
    threshold = connections_alert_threshold()
    active = count_active_backends(db)
    named = count_named_backends(db)
    observed = active if active is not None else client_count
    return {
        "DB_CONNECTIONS_COUNT": client_count,
        "DB_ACTIVE_CONNECTIONS": observed,
        "DB_NAMED_CONNECTIONS": named,
        "DB_CONNECTIONS_EXPECTED_MAX": expected,
        "DB_CONNECTIONS_ALERT": observed > threshold,
        "DB_CONNECTIONS_ALERT_THRESHOLD": threshold,
        "DB_INSTANCE_ID": REGISTRY.instance_id(),
        "DB_APPLICATION_NAME": historian_application_name(),
    }


class TrackedPostgresqlDatabase(PostgresqlDatabase):
    """PostgresqlDatabase that registers every libpq socket it opens."""

    def _connect(self):
        _reject_connect_during_outage()
        return _open_tracked_connection(self)

    def _close(self, conn):
        REGISTRY.unregister(conn, owner=self)
        return super()._close(conn)

    def close_all(self):
        try:
            if not self.is_closed():
                self.close()
        except Exception:
            _LOGGER.debug("current-greenlet historian close skipped", exc_info=True)
        REGISTRY.close_tracked(owner=self)


class TrackedMySQLDatabase(MySQLDatabase):
    def _connect(self):
        _reject_connect_during_outage()
        return _open_tracked_connection(self)

    def _close(self, conn):
        REGISTRY.unregister(conn, owner=self)
        return super()._close(conn)

    def close_all(self):
        try:
            if not self.is_closed():
                self.close()
        except Exception:
            _LOGGER.debug("current-greenlet historian close skipped", exc_info=True)
        REGISTRY.close_tracked(owner=self)


def bind_historian_proxy(database: Any) -> None:
    """Point the single Peewee Proxy used by every model at ``database``."""
    from ..dbmodels.core import proxy

    proxy.initialize(database)


def ensure_bound_connection(db: Any) -> None:
    """``SELECT 1`` on this greenlet's Peewee socket. Reopen if half-dead.

    A throwaway ``psycopg2`` ping can succeed while the bound handle is
    already closed (``connection already closed``). Reconnect must prove
    the handle the models will use, not a disposable client.
    """
    if db is None:
        raise RuntimeError("no historian handle")
    try:
        if hasattr(db, "is_closed") and db.is_closed():
            db.connect(reuse_if_open=True)
        db.execute_sql("SELECT 1")
        return
    except Exception:
        _LOGGER.debug("bound historian socket stale; reconnecting", exc_info=True)
    try:
        if hasattr(db, "close"):
            db.close()
    except Exception:
        pass
    db.connect(reuse_if_open=True)
    db.execute_sql("SELECT 1")


@contextmanager
def ephemeral_historian(db: Any | None) -> Iterator[None]:
    """Run Peewee work and close this greenlet's socket unless it is LoggerWorker."""
    try:
        yield
    finally:
        if not keep_historian_socket():
            close_current_greenlet_connection(db)


def close_current_greenlet_connection(db: Any | None) -> None:
    """Close the Peewee socket for *this* greenlet/thread only. Safe in Flask teardown."""
    if db is None:
        return
    try:
        closed = getattr(db, "is_closed", None)
        if callable(closed) and closed():
            return
        if hasattr(db, "close"):
            db.close()
    except Exception:
        _LOGGER.debug("request-scoped historian close skipped", exc_info=True)


def install_request_connection_teardown(flask_app) -> None:
    if flask_app is None or getattr(flask_app, "_pya_db_teardown", False):
        return

    @flask_app.teardown_appcontext
    def _pya_close_historian(_exc):
        try:
            from .. import PyAutomation

            close_current_greenlet_connection(getattr(PyAutomation(), "_db", None))
        except Exception:
            _LOGGER.debug("teardown historian close skipped", exc_info=True)

    flask_app._pya_db_teardown = True

    @flask_app.teardown_request
    def _pya_close_historian_request(_exc):
        try:
            from .. import PyAutomation

            close_current_greenlet_connection(getattr(PyAutomation(), "_db", None))
        except Exception:
            _LOGGER.debug("request historian close skipped", exc_info=True)


def _is_remote_peewee(db: Any) -> bool:
    params = getattr(db, "connect_params", None)
    database = getattr(db, "database", None)
    name = type(db).__name__.lower()
    if not isinstance(params, dict) or not isinstance(database, str):
        return False
    if "sqlite" in name:
        return False
    return True


def ping_throwaway(db: Any, timeout_s: float | None = None) -> None:
    """Open a disposable client socket, ``SELECT 1``, close. Never touches Peewee locals.

    The threadpool function must not raise: gevent logs those as ERROR even
    when the hub already handled a timeout. Outage is expected, not a crash.
    """
    params = dict(getattr(db, "connect_params", {}) or {})
    database = getattr(db, "database", None)
    if not database:
        raise RuntimeError("historian DSN missing")
    kind = type(db).__name__.lower()
    budget = int(timeout_s or min(connect_timeout_s(), probe_timeout_s() + 3))
    params = apply_remote_db_kwargs(
        "mysql" if "mysql" in kind else "postgresql",
        params,
    )
    params["connect_timeout"] = min(int(params.get("connect_timeout") or budget), budget)
    params["application_name"] = historian_application_name("probe")

    def _ping() -> bool:
        try:
            if "mysql" in kind:
                _ping_mysql(database, params)
            else:
                _ping_postgres(database, params)
            return True
        except Exception:
            return False

    ok = run_uncooperative_db_call(_ping, timeout_s=float(budget) + 1.0)
    if not ok:
        raise RuntimeError("historian probe failed")


def _ping_postgres(database: str, params: dict[str, Any]) -> None:
    import psycopg2

    allowed = {
        "host",
        "port",
        "user",
        "password",
        "connect_timeout",
        "keepalives",
        "keepalives_idle",
        "keepalives_interval",
        "keepalives_count",
        "sslmode",
        "options",
        "application_name",
    }
    kwargs = {key: params[key] for key in allowed if key in params and params[key] is not None}
    conn = psycopg2.connect(dbname=database, **kwargs)
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT 1")
    finally:
        conn.close()


def _ping_mysql(database: str, params: dict[str, Any]) -> None:
    import pymysql

    conn = pymysql.connect(
        db=database,
        host=params.get("host"),
        port=int(params.get("port") or 3306),
        user=params.get("user"),
        password=params.get("password"),
        connect_timeout=int(params.get("connect_timeout") or connect_timeout_s()),
        read_timeout=int(params.get("read_timeout") or connect_timeout_s()),
        write_timeout=int(params.get("write_timeout") or connect_timeout_s()),
    )
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT 1")
    finally:
        conn.close()


def keep_historian_socket() -> bool:
    """True for the long-lived replication worker that owns the idle socket."""
    name = threading.current_thread().name or ""
    return name in {"LoggerWorker", "SafJournalFlusher"} or name.startswith("LoggerWorker")


def count_active_backends(db: Any | None) -> int | None:
    """Backends in pg_stat_activity for this database, excluding the probe itself."""
    return _count_pg_activity(db, named_only=False)


def count_named_backends(db: Any | None) -> int | None:
    """Backends whose application_name is PyAutomationIO, excluding the probe."""
    return _count_pg_activity(db, named_only=True)


def close_foreign_historian_sockets(db: Any | None) -> int:
    """Drop sockets opened on ``db`` by other greenlets. Keep this greenlet's."""
    if db is None:
        return 0
    keep = None
    try:
        if hasattr(db, "is_closed") and not db.is_closed():
            keep = db.connection()
    except Exception:
        keep = None
    return REGISTRY.close_tracked_except(db, keep=keep)


def _count_pg_activity(db: Any | None, *, named_only: bool) -> int | None:
    from .db_io import probe_is_cooling_down

    if db is None or not _is_remote_peewee(db):
        return None
    if probe_is_cooling_down():
        return None
    params = dict(getattr(db, "connect_params", {}) or {})
    database = getattr(db, "database", None)
    if not database:
        return None
    budget = connect_timeout_s()
    params = apply_remote_db_kwargs("postgresql", params)
    params["application_name"] = historian_application_name("probe")

    def _query() -> int | None:
        import psycopg2

        allowed = {
            "host",
            "port",
            "user",
            "password",
            "connect_timeout",
            "keepalives",
            "keepalives_idle",
            "keepalives_interval",
            "keepalives_count",
            "sslmode",
            "options",
            "application_name",
        }
        kwargs = {key: params[key] for key in allowed if key in params and params[key] is not None}
        try:
            conn = psycopg2.connect(dbname=database, **kwargs)
        except Exception:
            return None
        try:
            with conn.cursor() as cursor:
                if named_only:
                    cursor.execute(
                        "SELECT count(*) FROM pg_stat_activity "
                        "WHERE datname = current_database() "
                        "AND backend_type = 'client backend' "
                        "AND application_name LIKE %s "
                        "AND pid <> pg_backend_pid()",
                        (APPLICATION_NAME_PREFIX + "%",),
                    )
                else:
                    cursor.execute(
                        "SELECT count(*) FROM pg_stat_activity "
                        "WHERE datname = current_database() AND pid <> pg_backend_pid() "
                        "AND backend_type = 'client backend'"
                    )
                row = cursor.fetchone()
                return int(row[0] if row else 0)
        except Exception:
            return None
        finally:
            try:
                conn.close()
            except Exception:
                pass

    try:
        counted = run_uncooperative_db_call(_query, timeout_s=float(budget) + 1.0)
        return int(counted) if counted is not None else None
    except Exception:
        _LOGGER.debug("pg_stat_activity census skipped", exc_info=True)
        return None


def probe_configured_historian(timeout_s: float | None = None) -> None:
    """Throwaway ping from ``db_config.json`` when Peewee has no handle yet."""
    from automation import PyAutomation

    cfg = PyAutomation().get_db_config() or {}
    kind = str(cfg.get("dbtype") or "").strip().lower()
    if kind not in {"postgresql", "postgres", "mysql"}:
        raise RuntimeError("no remote historian DSN")
    params = apply_remote_db_kwargs(
        "mysql" if kind == "mysql" else "postgresql",
        {
            key: cfg[key]
            for key in ("host", "port", "user", "password")
            if key in cfg and cfg[key] is not None
        },
    )
    handle = type("DSN", (), {"connect_params": params, "database": cfg.get("name")})()
    ping_throwaway(handle, timeout_s=timeout_s)


def probe_database(db: Any, timeout_s: float | None = None) -> None:
    """Reachability probe that cannot leak Peewee sockets onto the hub threadpool."""
    if db is None:
        probe_configured_historian(timeout_s=timeout_s)
        return
    if _is_remote_peewee(db):
        ping_throwaway(db, timeout_s=timeout_s)
        return
    db.execute_sql("SELECT 1;")
