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

    def test_idle_socket_of_a_living_worker_is_returned_before_the_server_kills_it(self):
        """CA-DB-ET-4: un worker lento vivo no debe donar un backend ``idle``.

        ``NtpMonitorWorker`` revisa cada hora; con el socket tomado, el
        ``idle_session_timeout`` del servidor lo cierra por detrás y el
        siguiente ciclo corre sobre un handle muerto.
        """
        import time

        from ..utils.db_connections import REGISTRY, idle_socket_budget_s

        db = self._database()
        stop = threading.Event()
        ready = threading.Event()

        def slow_worker():
            db.execute_sql("SELECT 1")
            ready.set()
            stop.wait(30)

        worker = threading.Thread(target=slow_worker, name="NtpMonitorWorker")
        worker.start()
        self.assertTrue(ready.wait(10))
        self.assertEqual(self._backends(), 1)

        budget = idle_socket_budget_s()
        for entry in REGISTRY._index.values():
            entry.last_used = time.monotonic() - (budget + 60.0)

        # El dueño sigue vivo, así que reap_abandoned no lo ve: este es el caso
        # que sólo el presupuesto de inactividad puede cerrar.
        self.assertEqual(REGISTRY.reap_abandoned(), 0)
        self.assertEqual(REGISTRY.reap_idle(budget), 1)
        self.assertEqual(self._backends(), 0)
        stop.set()
        worker.join(10)

    def test_resident_worker_keeps_its_socket(self):
        """CA-DB-ET-5: el reaper de inactividad nunca toca a un residente."""
        import time

        from ..utils.db_connections import REGISTRY, idle_socket_budget_s

        db = self._database()
        stop = threading.Event()
        ready = threading.Event()

        def resident():
            db.execute_sql("SELECT 1")
            ready.set()
            stop.wait(30)

        worker = threading.Thread(target=resident, name="LoggerWorker")
        worker.start()
        self.assertTrue(ready.wait(10))

        for entry in REGISTRY._index.values():
            entry.last_used = time.monotonic() - 4000.0
        self.assertEqual(REGISTRY.reap_idle(idle_socket_budget_s()), 0)
        self.assertEqual(self._backends(), 1)
        stop.set()
        worker.join(10)

    def test_a_query_reprieves_the_socket_from_the_idle_reaper(self):
        """CA-DB-ET-6: ``execute_sql`` sella ``last_used``; lo que se usa no se cosecha."""
        import time

        from ..utils.db_connections import REGISTRY, idle_socket_budget_s

        db = self._database()
        db.execute_sql("SELECT 1")
        for entry in REGISTRY._index.values():
            entry.last_used = time.monotonic() - 4000.0

        db.execute_sql("SELECT 1")

        self.assertEqual(REGISTRY.reap_idle(idle_socket_budget_s()), 0)
        self.assertEqual(self._backends(), 1)

    def test_pooled_thread_reports_a_stable_application_name(self):
        """CA-DB-ET-7: ``pg_stat_activity`` nombra el subsistema, no ``Dummy-9``."""
        import psycopg2

        from ..utils.db_connections import historian_application_name, historian_role_scope

        seen: dict[str, str] = {}

        def pooled():
            threading.current_thread().name = "Dummy-9"
            seen["plain"] = historian_application_name()
            with historian_role_scope("CatalogReplicator"):
                seen["scoped"] = historian_application_name()

        worker = threading.Thread(target=pooled)
        worker.start()
        worker.join()

        self.assertNotIn("Dummy", seen["plain"])
        self.assertTrue(seen["scoped"].endswith("CatalogReplicator"))

        conn = psycopg2.connect(
            dbname=self.name, application_name=seen["scoped"], **self.cfg
        )
        try:
            with conn.cursor() as cursor:
                cursor.execute("SELECT current_setting('application_name')")
                self.assertEqual(cursor.fetchone()[0], seen["scoped"])
        finally:
            conn.close()

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
