# -*- coding: utf-8 -*-
"""Listen for cross-edge cache invalidation (PG NOTIFY + Redis Pub/Sub).

One dedicated connection LISTENs both user and ACL channels so we do not
spend a second historian slot (idle budget). Redis Pub/Sub is the local
sidecar (intra-edge workers). PostgreSQL NOTIFY is the cross-edge bus.
"""
from __future__ import annotations

import logging
import select
import time

from .worker import BaseWorker
from ..authz.invalidate import (
    PG_CHANNEL as AUTHZ_PG_CHANNEL,
    REDIS_CHANNEL as AUTHZ_REDIS_CHANNEL,
    apply_authz_invalidate,
    parse_authz_payload,
)
from ..authz.store import PERIODIC_RELOAD_S, maybe_periodic_reload
from ..catalog.user_cache import (
    PG_CHANNEL,
    REDIS_CHANNEL,
    apply_user_invalidate,
    parse_invalidate_payload,
)

_LOGGER = logging.getLogger("pyautomation.user_cache")
_POLL_S = 0.5
_RECONNECT_S = 5.0


class UserInvalidateWorker(BaseWorker):
    """Dedicated connection: never shares the Socket.IO / request pool."""

    def __init__(self):
        super().__init__()
        self.name = "UserInvalidateWorker"
        self.daemon = True
        self._pg_conn = None
        self._redis_pubsub = None
        self._authz_periodic_mono = time.monotonic()

    def stop(self) -> None:
        super().stop()
        self._close_pg()
        self._close_redis()

    def run(self) -> None:
        while not self.stop_event.is_set():
            try:
                self._ensure_pg()
                self._ensure_redis()
                self._drain_pg()
                self._drain_redis()
                self._maybe_authz_heartbeat()
            except Exception:
                _LOGGER.debug("user invalidate worker tick failed", exc_info=True)
                self._close_pg()
                self._close_redis()
                self.stop_event.wait(_RECONNECT_S)
                continue
            self.stop_event.wait(_POLL_S)

    def _maybe_authz_heartbeat(self) -> None:
        now = time.monotonic()
        if (now - self._authz_periodic_mono) < PERIODIC_RELOAD_S:
            return
        self._authz_periodic_mono = now
        try:
            # The reload is minutes apart and is the only Peewee work this
            # worker does; the LISTEN socket below is a separate, raw handle.
            with self.historian_cycle():
                maybe_periodic_reload()
        except Exception:
            _LOGGER.debug("authz periodic reload skipped", exc_info=True)

    def _ensure_pg(self) -> None:
        if self._pg_conn is not None:
            return
        try:
            from .. import PyAutomation

            app = PyAutomation()
            cfg = app.get_db_config() or {}
            dbtype = str(cfg.get("dbtype") or "").lower()
            if dbtype not in ("postgresql", "postgres"):
                return
            import psycopg2
            from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT

            from ..utils.db_connections import historian_application_name

            # A LISTEN socket is idle by design: it must stay identifiable in
            # pg_stat_activity and must not inherit idle_session_timeout.
            conn = psycopg2.connect(
                host=cfg.get("host") or "127.0.0.1",
                port=int(cfg.get("port") or 5432),
                user=cfg.get("user") or cfg.get("username") or "postgres",
                password=cfg.get("password") or "",
                dbname=cfg.get("name") or cfg.get("dbname") or "app_db",
                connect_timeout=3,
                application_name=historian_application_name("UserInvalidateWorker"),
                keepalives=1,
                keepalives_idle=30,
                keepalives_interval=10,
                keepalives_count=3,
            )
            conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
            cur = conn.cursor()
            cur.execute(f"LISTEN {PG_CHANNEL};")
            cur.execute(f"LISTEN {AUTHZ_PG_CHANNEL};")
            cur.close()
            self._pg_conn = conn
            _LOGGER.info(
                "listening for invalidation on PG channels %s %s",
                PG_CHANNEL,
                AUTHZ_PG_CHANNEL,
            )
        except Exception:
            self._pg_conn = None
            _LOGGER.debug("user invalidate PG LISTEN unavailable", exc_info=True)

    def _ensure_redis(self) -> None:
        if self._redis_pubsub is not None:
            return
        try:
            from ..utils.redis_client import get_redis

            client = get_redis()
            if client is None:
                return
            pubsub = client.pubsub(ignore_subscribe_messages=True)
            pubsub.subscribe(REDIS_CHANNEL, AUTHZ_REDIS_CHANNEL)
            self._redis_pubsub = pubsub
        except Exception:
            self._redis_pubsub = None
            _LOGGER.debug("user invalidate Redis subscribe unavailable", exc_info=True)

    def _drain_pg(self) -> None:
        conn = self._pg_conn
        if conn is None:
            return
        try:
            ready, _, _ = select.select([conn], [], [], 0)
            if not ready:
                return
            conn.poll()
            while conn.notifies:
                notify = conn.notifies.pop(0)
                channel = str(getattr(notify, "channel", "") or "")
                payload = getattr(notify, "payload", None)
                if channel == AUTHZ_PG_CHANNEL:
                    version, origin = parse_authz_payload(payload)
                    apply_authz_invalidate(version=version, origin=origin, reason="pg_notify")
                    continue
                username, origin = parse_invalidate_payload(payload)
                if username:
                    apply_user_invalidate(username=username, origin=origin)
        except Exception:
            _LOGGER.debug("user invalidate PG drain failed", exc_info=True)
            self._close_pg()

    def _drain_redis(self) -> None:
        pubsub = self._redis_pubsub
        if pubsub is None:
            return
        try:
            deadline = time.monotonic() + 0.05
            while time.monotonic() < deadline:
                message = pubsub.get_message(timeout=0.01)
                if not message:
                    break
                if message.get("type") != "message":
                    continue
                channel = str(message.get("channel") or "")
                data = message.get("data")
                if channel == AUTHZ_REDIS_CHANNEL:
                    version, origin = parse_authz_payload(data)
                    apply_authz_invalidate(version=version, origin=origin, reason="redis")
                    continue
                username, origin = parse_invalidate_payload(data)
                if username:
                    apply_user_invalidate(username=username, origin=origin)
        except Exception:
            _LOGGER.debug("user invalidate Redis drain failed", exc_info=True)
            self._close_redis()

    def _close_pg(self) -> None:
        conn = self._pg_conn
        self._pg_conn = None
        if conn is None:
            return
        try:
            conn.close()
        except Exception:
            pass

    def _close_redis(self) -> None:
        pubsub = self._redis_pubsub
        self._redis_pubsub = None
        if pubsub is None:
            return
        try:
            pubsub.close()
        except Exception:
            pass
