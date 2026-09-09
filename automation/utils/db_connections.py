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
import time
import weakref
from contextlib import contextmanager
from typing import Any, Iterator

from peewee import MySQLDatabase, OperationalError, PostgresqlDatabase

from .db_io import apply_remote_db_kwargs, connect_timeout_s, probe_timeout_s, run_uncooperative_db_call

_LOGGER = logging.getLogger("pyautomation")
APPLICATION_NAME = "PyAutomationIO"
APPLICATION_NAME_PREFIX = "PyAutomationIO"
DEFAULT_CONNECTIONS_ALERT = 6
DEFAULT_CONNECTIONS_HARD_MAX = 12
DEFAULT_LEAK_DETECTION_S = 900.0
_CONNECT_GATE = threading.local()
_TXN_LOCK = threading.Lock()
_TXN_COMMITS = 0


def note_local_commit() -> None:
    """Count a commit on this process's tracked historian sockets (per-edge Txn/min)."""
    global _TXN_COMMITS
    with _TXN_LOCK:
        _TXN_COMMITS += 1


def local_txn_commit_count() -> int:
    with _TXN_LOCK:
        return _TXN_COMMITS


def reset_local_txn_commit_count() -> None:
    global _TXN_COMMITS
    with _TXN_LOCK:
        _TXN_COMMITS = 0


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


def _enforce_connection_ceiling(role: str) -> None:
    """Fail fast instead of walking the server to ``too many clients already``.

    A process that already holds the ceiling is leaking, not busy: the steady
    state is LoggerWorker + SafJournalFlusher + a handful of ephemeral sockets.
    Reap first (a dead greenlet cannot close its own socket), then refuse.
    """
    ceiling = connections_hard_max()
    if REGISTRY.count() < ceiling:
        return
    REGISTRY.reap_abandoned()
    live = REGISTRY.count()
    if live < ceiling:
        return
    _LOGGER.error(
        "Historian socket ceiling reached (%s/%s); refusing connect for role=%s. Census: %s",
        live,
        ceiling,
        role,
        REGISTRY.census(),
    )
    raise OperationalError(
        f"historian socket ceiling reached ({live}/{ceiling}); connect refused"
    )


def _open_tracked_connection(database) -> Any:
    """libpq/MySQL connect. Failures arm the outage gate so the hub is not retried."""
    role = historian_application_name()
    _enforce_connection_ceiling(role)
    params = getattr(database, "connect_params", None)
    if isinstance(params, dict):
        params["application_name"] = role
    try:
        conn = super(type(database), database)._connect()
    except Exception:
        _mark_app_historian_dead()
        raise
    REGISTRY.register(conn, owner=database, role=role)
    _warn_on_socket_growth(role)
    return conn


def _warn_on_socket_growth(role: str) -> None:
    """``leak-detection-threshold``: name the sockets before the server runs out."""
    live = REGISTRY.count()
    if live <= connections_alert_threshold():
        return
    leaked = REGISTRY.leaked(leak_detection_s())
    _LOGGER.warning(
        "Historian sockets above alert threshold: live=%s threshold=%s opened_by=%s long_lived=%s",
        live,
        connections_alert_threshold(),
        role,
        leaked or "none",
    )


def _safe_application_token(value: str) -> str:
    return "".join(ch if ch.isalnum() or ch in "._-" else "_" for ch in value) or "unknown"


def historian_node_name_prefix() -> str:
    """``application_name`` prefix that identifies this edge in ``pg_stat_activity``."""
    from ..node_scope import current_node_scope

    scope = current_node_scope()
    if scope.enabled and scope.node_id:
        return f"{APPLICATION_NAME_PREFIX}:{_safe_application_token(scope.node_id)}"
    return APPLICATION_NAME_PREFIX


def historian_application_name(role: str | None = None) -> str:
    """libpq application_name for this greenlet. Max 63 chars (PostgreSQL)."""
    from ..node_scope import current_node_scope

    def safe(value: str) -> str:
        return _safe_application_token(value)

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


class _TrackedSocket:
    """Weak handle on one libpq socket plus the identity of the greenlet that opened it.

    The census must **observe** sockets, never own them. A strong reference here
    keeps the psycopg2 object alive after its greenlet dies, so libpq never
    finalizes and PostgreSQL keeps an ``idle`` backend forever. That turns a
    self-healing miss into a permanent leak (planta: ~100 backends en 6 días).
    """

    __slots__ = ("_ref", "_strong", "role", "thread_ref", "thread_name", "opened_at")

    def __init__(self, conn: Any, role: str, on_dead) -> None:
        try:
            self._ref = weakref.ref(conn, on_dead)
            self._strong = None
        except TypeError:
            # Driver handle that refuses weak references. Keep the census exact:
            # such a socket depends on close()/reap, never on the collector.
            self._ref = None
            self._strong = conn
        self.role = role
        thread = threading.current_thread()
        self.thread_name = thread.name or "unknown"
        try:
            self.thread_ref = weakref.ref(thread)
        except TypeError:
            self.thread_ref = None
        self.opened_at = time.monotonic()

    def ref(self) -> Any:
        return self._strong if self._ref is None else self._ref()

    def release(self) -> None:
        self._strong = None

    def alive(self) -> bool:
        return self.ref() is not None

    def owner_is_gone(self) -> bool:
        """True when the greenlet/thread that opened the socket can no longer close it."""
        if self.thread_ref is None:
            return False
        thread = self.thread_ref()
        if thread is None:
            return True
        return not bool(getattr(thread, "is_alive", lambda: True)())

    def age_s(self) -> float:
        return max(0.0, time.monotonic() - self.opened_at)


class ConnectionRegistry:
    """Live-socket census keyed by Database instance.

    ``close_all`` on the *previous* handle must not kill sockets that belong
    to the *candidate* opened during reconnect.

    Entries are weak: a socket dropped by a dead greenlet leaves the census on
    its own. ``reap_abandoned`` closes them deterministically instead of waiting
    for the garbage collector.
    """

    def __init__(self) -> None:
        # Reentrant: a weakref callback can fire while this thread holds the lock.
        self._lock = threading.RLock()
        self._by_owner: dict[int, dict[int, _TrackedSocket]] = {}
        self._instance_id: int | None = None
        self._reaped = 0

    def bind_instance(self, database: Any) -> None:
        with self._lock:
            self._instance_id = id(database)

    def _forget(self, oid: int, key: int) -> None:
        with self._lock:
            bucket = self._by_owner.get(oid)
            if bucket is None:
                return
            entry = bucket.pop(key, None)
            if entry is not None:
                entry.release()
            if not bucket:
                self._by_owner.pop(oid, None)

    def register(self, conn: Any, owner: Any | None = None, role: str | None = None) -> None:
        oid = id(owner) if owner is not None else 0
        key = id(conn)

        def _on_dead(_ref, oid=oid, key=key) -> None:
            self._forget(oid, key)

        entry = _TrackedSocket(conn, role or historian_application_name(), _on_dead)
        with self._lock:
            self._by_owner.setdefault(oid, {})[key] = entry

    def unregister(self, conn: Any, owner: Any | None = None) -> None:
        key = id(conn)
        with self._lock:
            if owner is not None:
                self._forget(id(owner), key)
                return
            for oid, bucket in list(self._by_owner.items()):
                if key in bucket:
                    self._forget(oid, key)
                    return

    def _live_entries(self) -> list[tuple[int, int, _TrackedSocket]]:
        with self._lock:
            out: list[tuple[int, int, _TrackedSocket]] = []
            for oid, bucket in list(self._by_owner.items()):
                for key, entry in list(bucket.items()):
                    if entry.alive():
                        out.append((oid, key, entry))
                    else:
                        self._forget(oid, key)
            return out

    def count(self) -> int:
        return len(self._live_entries())

    def reaped_count(self) -> int:
        with self._lock:
            return self._reaped

    def instance_id(self) -> int | None:
        with self._lock:
            return self._instance_id

    def census(self) -> list[dict[str, Any]]:
        """Per-socket census for logs and ``/api/health``. Never exposes the socket."""
        return [
            {
                "role": entry.role,
                "thread": entry.thread_name,
                "age_s": round(entry.age_s(), 1),
                "owner_gone": entry.owner_is_gone(),
            }
            for _oid, _key, entry in self._live_entries()
        ]

    def reap_abandoned(self) -> int:
        """Close sockets whose greenlet died without ``close()``. Returns how many."""
        doomed: list[tuple[int, int, _TrackedSocket]] = []
        for oid, key, entry in self._live_entries():
            if entry.owner_is_gone():
                doomed.append((oid, key, entry))
        closed = 0
        for oid, key, entry in doomed:
            conn = entry.ref()
            self._forget(oid, key)
            if conn is None:
                continue
            try:
                conn.close()
                closed += 1
                _LOGGER.warning(
                    "Reaped abandoned historian socket role=%s thread=%s age_s=%.1f",
                    entry.role,
                    entry.thread_name,
                    entry.age_s(),
                )
            except Exception:
                _LOGGER.debug("abandoned historian socket close skipped", exc_info=True)
        if closed:
            with self._lock:
                self._reaped += closed
        return closed

    def leaked(self, older_than_s: float) -> list[dict[str, Any]]:
        """Sockets older than the leak threshold, newest last (``leak-detection-threshold``)."""
        rows = [row for row in self.census() if row["age_s"] >= float(older_than_s)]
        rows.sort(key=lambda row: row["age_s"])
        return rows

    def _drain(self, items: list[tuple[int, int, _TrackedSocket]], what: str) -> int:
        closed = 0
        for oid, key, entry in items:
            conn = entry.ref()
            self._forget(oid, key)
            if conn is None:
                continue
            try:
                conn.close()
                closed += 1
            except Exception:
                _LOGGER.debug("%s close skipped", what, exc_info=True)
        return closed

    def close_tracked(self, owner: Any | None = None) -> int:
        oid_filter = None if owner is None else id(owner)
        items = [
            (oid, key, entry)
            for oid, key, entry in self._live_entries()
            if oid_filter is None or oid == oid_filter
        ]
        return self._drain(items, "tracked historian connection")

    def close_tracked_except(self, owner: Any, keep: Any | None = None) -> int:
        """Close sockets of ``owner`` except ``keep`` (this greenlet's handle)."""
        keep_id = id(keep) if keep is not None else None
        oid_filter = id(owner)
        items = [
            (oid, key, entry)
            for oid, key, entry in self._live_entries()
            if oid == oid_filter and key != keep_id
        ]
        return self._drain(items, "foreign historian connection")


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


def connections_hard_max() -> int:
    """Sockets this process may ever hold. Beyond it, ``connect()`` fails fast.

    Equivalent to ``maximum-pool-size`` without reintroducing a pool: the ceiling
    is per process, so N edges × M gunicorn workers stay inside ``max_connections``.
    """
    raw = os.environ.get("AUTOMATION_DB_CONNECTIONS_MAX")
    if raw:
        try:
            return max(2, min(int(raw), 256))
        except (TypeError, ValueError):
            pass
    return max(DEFAULT_CONNECTIONS_HARD_MAX, connections_alert_threshold() * 2)


def leak_detection_s() -> float:
    """Age above which a socket is reported by name. Env: AUTOMATION_DB_LEAK_DETECTION_S."""
    raw = os.environ.get("AUTOMATION_DB_LEAK_DETECTION_S")
    try:
        value = float(raw) if raw not in (None, "") else DEFAULT_LEAK_DETECTION_S
    except (TypeError, ValueError):
        value = DEFAULT_LEAK_DETECTION_S
    return max(5.0, value)


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
        "DB_CONNECTIONS_MAX": connections_hard_max(),
        "DB_CONNECTIONS_REAPED": REGISTRY.reaped_count(),
        "DB_CONNECTIONS_LEAKED": len(REGISTRY.leaked(leak_detection_s())),
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

    def commit(self):
        super().commit()
        note_local_commit()

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

    def commit(self):
        super().commit()
        note_local_commit()

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
        _rollback_open_transaction(db)
        if hasattr(db, "close"):
            db.close()
    except Exception:
        _LOGGER.debug("request-scoped historian close skipped", exc_info=True)


def _rollback_open_transaction(db: Any) -> None:
    """Peewee refuses to ``close()`` inside a transaction; the socket would survive.

    Teardown swallows that error, so an aborted ``atomic()`` used to leave the
    greenlet's backend ``idle in transaction`` for good. Unwind before closing.
    """
    in_txn = getattr(db, "in_transaction", None)
    if not callable(in_txn):
        return
    try:
        if not in_txn():
            return
    except Exception:
        return
    try:
        db.rollback()
        _LOGGER.warning(
            "Historian socket closed with an open transaction; rolled back first (role=%s)",
            historian_application_name(),
        )
    except Exception:
        _LOGGER.debug("historian rollback before close skipped", exc_info=True)


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
    """Client backends of **this edge** on the current database (excludes the probe)."""
    return _count_pg_activity(db, named_only=False)


def count_named_backends(db: Any | None) -> int | None:
    """This edge's ``PyAutomationIO:<node>:%`` backends, excluding the probe."""
    return _count_pg_activity(db, named_only=True)


def query_pg_txn_counters(db: Any | None) -> tuple[int, int] | None:
    """Throwaway ``pg_stat_database`` commit/rollback counters. Never uses Peewee pool."""
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

    def _query() -> tuple[int, int] | None:
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
        conn = None
        try:
            conn = psycopg2.connect(dbname=database, **kwargs)
            with conn.cursor() as cursor:
                cursor.execute(
                    "SELECT xact_commit, xact_rollback FROM pg_stat_database "
                    "WHERE datname = current_database()"
                )
                row = cursor.fetchone()
                if not row:
                    return None
                return int(row[0] or 0), int(row[1] or 0)
        except Exception:
            return None
        finally:
            if conn is not None:
                try:
                    conn.close()
                except Exception:
                    pass

    try:
        counted = run_uncooperative_db_call(_query, timeout_s=float(budget) + 1.0)
        if not counted:
            return None
        return int(counted[0]), int(counted[1])
    except Exception:
        _LOGGER.debug("pg_stat_database census skipped", exc_info=True)
        return None


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
                prefix = historian_node_name_prefix() + "%"
                if named_only:
                    cursor.execute(
                        "SELECT count(*) FROM pg_stat_activity "
                        "WHERE datname = current_database() "
                        "AND backend_type = 'client backend' "
                        "AND application_name LIKE %s "
                        "AND pid <> pg_backend_pid()",
                        (prefix,),
                    )
                else:
                    cursor.execute(
                        "SELECT count(*) FROM pg_stat_activity "
                        "WHERE datname = current_database() "
                        "AND backend_type = 'client backend' "
                        "AND pid <> pg_backend_pid() "
                        "AND ("
                        "  application_name LIKE %s "
                        "  OR ("
                        "    client_addr IS NOT NULL "
                        "    AND client_addr IN ("
                        "      SELECT DISTINCT client_addr FROM pg_stat_activity "
                        "      WHERE datname = current_database() "
                        "        AND application_name LIKE %s "
                        "        AND client_addr IS NOT NULL"
                        "    )"
                        "  )"
                        ")",
                        (prefix, prefix),
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
