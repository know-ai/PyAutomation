# -*- coding: utf-8 -*-
"""Listen for cross-edge user cache invalidation (PG NOTIFY + Redis Pub/Sub)."""
from __future__ import annotations

import logging
import select
import time

from .worker import BaseWorker
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
            except Exception:
                _LOGGER.debug("user invalidate worker tick failed", exc_info=True)
                self._close_pg()
                self._close_redis()
                self.stop_event.wait(_RECONNECT_S)
                continue
            self.stop_event.wait(_POLL_S)

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

            conn = psycopg2.connect(
                host=cfg.get("host") or "127.0.0.1",
                port=int(cfg.get("port") or 5432),
                user=cfg.get("user") or cfg.get("username") or "postgres",
                password=cfg.get("password") or "",
                dbname=cfg.get("name") or cfg.get("dbname") or "app_db",
                connect_timeout=3,
            )
            conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
            cur = conn.cursor()
            cur.execute(f"LISTEN {PG_CHANNEL};")
            cur.close()
            self._pg_conn = conn
            _LOGGER.info("listening for user invalidation on PG channel %s", PG_CHANNEL)
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
            pubsub.subscribe(REDIS_CHANNEL)
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
                username, origin = parse_invalidate_payload(getattr(notify, "payload", None))
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
                username, origin = parse_invalidate_payload(message.get("data"))
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
