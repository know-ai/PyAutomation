# -*- coding: utf-8 -*-
"""Censo de backends contra un PostgreSQL real. Reproduce el incidente de planta.

No requiere la red de producción: basta un contenedor local.

    docker run -d --name pg-soak -p 32800:5432 \
        -e POSTGRES_PASSWORD=postgres postgres:17-bullseye

    AUTOMATION_TEST_PG_DSN=postgresql://postgres:postgres@127.0.0.1:32800/postgres \
        python -m pytest automation/tests/test_db_connection_soak.py -v

Sin ``AUTOMATION_TEST_PG_DSN`` la suite se salta: los unit tests de
``test_db_io.py`` cubren la misma lógica con dobles.
"""
from __future__ import annotations

import gc
import os
import threading
import unittest
from urllib.parse import unquote, urlparse

DSN_ENV = "AUTOMATION_TEST_PG_DSN"


def _dsn() -> dict | None:
    raw = os.environ.get(DSN_ENV)
    if not raw:
        return None
    parsed = urlparse(raw)
    return {
        "database": (parsed.path or "/postgres").lstrip("/") or "postgres",
        "host": parsed.hostname or "127.0.0.1",
        "port": int(parsed.port or 5432),
        "user": unquote(parsed.username or "postgres"),
        "password": unquote(parsed.password or ""),
    }


@unittest.skipUnless(_dsn(), f"set {DSN_ENV} to run against a live PostgreSQL")
class TestHistorianBackendCensus(unittest.TestCase):
    """CA-DB-ET-1: tras un ciclo de trabajo, PostgreSQL no conserva backends huérfanos."""

    def setUp(self):
        from ..utils.db_connections import REGISTRY

        self.cfg = _dsn()
        self.name = self.cfg.pop("database")
        REGISTRY.close_tracked()
        self.assertEqual(self._backends(), 0, "el servidor ya tenía backends PyAutomationIO")

    def tearDown(self):
        from ..utils.db_connections import REGISTRY

        REGISTRY.close_tracked()

    def _backends(self) -> int:
        import psycopg2

        conn = psycopg2.connect(dbname=self.name, **self.cfg)
        try:
            with conn.cursor() as cursor:
                cursor.execute(
                    "SELECT count(*) FROM pg_stat_activity "
                    "WHERE datname = current_database() "
                    "AND backend_type = 'client backend' "
                    "AND application_name LIKE 'PyAutomationIO%' "
                    "AND pid <> pg_backend_pid()"
                )
                return int(cursor.fetchone()[0])
        finally:
            conn.close()

    def _database(self):
        from ..utils.db_connections import TrackedPostgresqlDatabase

        return TrackedPostgresqlDatabase(self.name, **self.cfg)

    def test_dead_greenlets_do_not_leave_idle_backends(self):
        """Antes del arreglo: 12 hilos efímeros = 12 backends idle permanentes."""
        db = self._database()
        for index in range(12):
            worker = threading.Thread(
                target=lambda: db.execute_sql("SELECT 1"),
                name=f"Ephemeral-{index}",
            )
            worker.start()
            worker.join()
        gc.collect()
        self.assertEqual(self._backends(), 0)

    def test_reaper_closes_socket_pinned_after_its_greenlet_died(self):
        from ..utils.db_connections import REGISTRY

        db = self._database()
        pinned = []

        def work():
            db.execute_sql("SELECT 1")
            pinned.append(db.connection())

        worker = threading.Thread(target=work, name="PinnedWorker")
        worker.start()
        worker.join()
        gc.collect()

        self.assertEqual(self._backends(), 1)
        self.assertEqual(REGISTRY.reap_abandoned(), 1)
        self.assertEqual(self._backends(), 0)

    def test_server_applies_idle_session_guards(self):
        import psycopg2

        from ..utils.db_io import apply_remote_db_kwargs

        params = apply_remote_db_kwargs("postgresql", dict(self.cfg))
        conn = psycopg2.connect(dbname=self.name, **params)
        try:
            with conn.cursor() as cursor:
                cursor.execute(
                    "SELECT current_setting('idle_session_timeout'), "
                    "current_setting('idle_in_transaction_session_timeout')"
                )
                idle, in_txn = cursor.fetchone()
        finally:
            conn.close()
        self.assertEqual(idle, "5min")
        self.assertEqual(in_txn, "1min")


if __name__ == "__main__":
    unittest.main()
