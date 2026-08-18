# -*- coding: utf-8 -*-
"""Fail-fast historian I/O — unreachable hosts must not freeze the gevent hub."""
from __future__ import annotations

import time
import unittest
from unittest.mock import MagicMock, patch

from ..logger.core import BaseLogger
from ..utils.db_io import (
    apply_remote_db_kwargs,
    connect_timeout_s,
    mark_remote_db_live,
    probe_is_cooling_down,
    run_uncooperative_db_call,
)
from ..utils.db_connections import (
    REGISTRY,
    close_current_greenlet_connection,
    snapshot_connection_metrics,
)


class TestApplyRemoteDbKwargs(unittest.TestCase):
    def test_postgresql_gets_connect_timeout_and_keepalives(self):
        kwargs = apply_remote_db_kwargs("postgresql", {"host": "192.168.1.95", "port": 5432})
        self.assertEqual(kwargs["connect_timeout"], connect_timeout_s())
        self.assertEqual(kwargs["keepalives"], 1)
        self.assertEqual(kwargs["keepalives_idle"], 3)
        self.assertEqual(kwargs["host"], "192.168.1.95")
        self.assertEqual(kwargs["application_name"], "PyAutomationIO")

    def test_does_not_override_explicit_connect_timeout(self):
        kwargs = apply_remote_db_kwargs("postgresql", {"connect_timeout": 9})
        self.assertEqual(kwargs["connect_timeout"], 9)

    def test_mysql_gets_read_and_write_timeouts(self):
        kwargs = apply_remote_db_kwargs("mysql", {})
        self.assertEqual(kwargs["connect_timeout"], connect_timeout_s())
        self.assertEqual(kwargs["read_timeout"], connect_timeout_s())
        self.assertEqual(kwargs["write_timeout"], connect_timeout_s())

    def test_sqlite_unchanged(self):
        kwargs = apply_remote_db_kwargs("sqlite", {"dbfile": "app.db"})
        self.assertEqual(kwargs, {"dbfile": "app.db"})


class TestRunUncooperativeDbCall(unittest.TestCase):
    def test_returns_function_result(self):
        self.assertEqual(run_uncooperative_db_call(lambda: 42, timeout_s=1.0), 42)

    def test_propagates_function_errors(self):
        def boom():
            raise RuntimeError("libpq exploded")

        with self.assertRaises(RuntimeError):
            run_uncooperative_db_call(boom, timeout_s=1.0)

    def test_times_out_before_os_tcp_default(self):
        def hang():
            time.sleep(1.5)

        started = time.monotonic()
        with self.assertRaises(TimeoutError):
            run_uncooperative_db_call(hang, timeout_s=0.15)
        elapsed = time.monotonic() - started
        self.assertLess(elapsed, 0.8)


class TestCheckConnectivityTimeout(unittest.TestCase):
    def setUp(self):
        mark_remote_db_live()
        self.logger = BaseLogger()
        self._prev_db = getattr(self.logger, "_db", None)

    def tearDown(self):
        self.logger._db = self._prev_db
        mark_remote_db_live()

    def test_false_when_no_handle(self):
        self.logger._db = None
        with patch(
            "automation.utils.db_connections.probe_configured_historian",
            side_effect=RuntimeError("no remote historian DSN"),
        ):
            self.assertFalse(self.logger.check_connectivity())

    def test_true_when_no_handle_but_dsn_reachable(self):
        self.logger._db = None
        with patch("automation.utils.db_connections.probe_configured_historian"):
            self.assertTrue(self.logger.check_connectivity())

    def test_true_when_select_one_works(self):
        db = MagicMock()
        self.logger._db = db
        self.assertTrue(self.logger.check_connectivity())
        db.execute_sql.assert_called_with("SELECT 1;")

    def test_false_when_remote_probe_times_out(self):
        db = MagicMock()
        db.connect_params = {"host": "192.168.1.95", "port": 5432}
        db.database = "app_db"
        self.logger._db = db
        with patch(
            "automation.utils.db_connections.ping_throwaway",
            side_effect=TimeoutError("database I/O timed out"),
        ):
            started = time.monotonic()
            self.assertFalse(self.logger.check_connectivity())
            self.assertLess(time.monotonic() - started, 0.8)
        self.assertTrue(probe_is_cooling_down())

    def test_cooldown_skips_stacked_probes(self):
        db = MagicMock()
        db.execute_sql.side_effect = OSError("No route to host")
        self.logger._db = db
        self.assertFalse(self.logger.check_connectivity())
        db.execute_sql.reset_mock()
        self.assertFalse(self.logger.check_connectivity())
        db.execute_sql.assert_not_called()


class TestConnectionRegistry(unittest.TestCase):
    def setUp(self):
        REGISTRY.close_tracked()

    def tearDown(self):
        REGISTRY.close_tracked()

    def test_count_tracks_register_and_unregister(self):
        conn = object()
        REGISTRY.register(conn)
        self.assertEqual(REGISTRY.count(), 1)
        REGISTRY.unregister(conn)
        self.assertEqual(REGISTRY.count(), 0)

    def test_close_tracked_closes_and_zeros_count(self):
        conn = MagicMock()
        REGISTRY.register(conn)
        self.assertEqual(REGISTRY.close_tracked(), 1)
        conn.close.assert_called_once()
        self.assertEqual(REGISTRY.count(), 0)

    def test_snapshot_metrics_alert_when_over_threshold(self):
        for index in range(connections_over_threshold()):
            REGISTRY.register(object())
        snap = snapshot_connection_metrics()
        self.assertGreater(snap["DB_CONNECTIONS_COUNT"], snap["DB_CONNECTIONS_ALERT_THRESHOLD"])
        self.assertTrue(snap["DB_CONNECTIONS_ALERT"])
        self.assertEqual(snap["DB_APPLICATION_NAME"], "PyAutomationIO")
        self.assertEqual(snap["DB_ACTIVE_CONNECTIONS"], snap["DB_CONNECTIONS_COUNT"])
        self.assertEqual(snap["DB_CONNECTIONS_EXPECTED_MAX"], 4)

    def test_close_tracked_except_keeps_current(self):
        owner = object()
        keep = MagicMock()
        stale = MagicMock()
        REGISTRY.register(keep, owner=owner)
        REGISTRY.register(stale, owner=owner)
        self.assertEqual(REGISTRY.close_tracked_except(owner, keep=keep), 1)
        stale.close.assert_called_once()
        keep.close.assert_not_called()
        self.assertEqual(REGISTRY.count(), 1)
        REGISTRY.close_tracked(owner=owner)

    def test_close_tracked_does_not_kill_other_owner(self):
        previous = object()
        candidate = object()
        old_conn = MagicMock()
        new_conn = MagicMock()
        REGISTRY.register(old_conn, owner=previous)
        REGISTRY.register(new_conn, owner=candidate)
        self.assertEqual(REGISTRY.close_tracked(owner=previous), 1)
        old_conn.close.assert_called_once()
        new_conn.close.assert_not_called()
        self.assertEqual(REGISTRY.count(), 1)
        REGISTRY.close_tracked(owner=candidate)

    def test_close_current_greenlet_skips_already_closed(self):
        db = MagicMock()
        db.is_closed.return_value = True
        close_current_greenlet_connection(db)
        db.close.assert_not_called()

    def test_tracked_close_all_is_owner_scoped(self):
        from ..utils.db_connections import TrackedPostgresqlDatabase

        previous = TrackedPostgresqlDatabase(None)
        candidate = TrackedPostgresqlDatabase(None)
        old_conn = MagicMock()
        new_conn = MagicMock()
        REGISTRY.register(old_conn, owner=previous)
        REGISTRY.register(new_conn, owner=candidate)
        previous.close_all()
        old_conn.close.assert_called_once()
        new_conn.close.assert_not_called()
        REGISTRY.close_tracked(owner=candidate)

    def test_ensure_bound_connection_reopens_closed_handle(self):
        from ..utils.db_connections import ensure_bound_connection

        db = MagicMock()
        db.is_closed.return_value = True
        ensure_bound_connection(db)
        db.connect.assert_called()
        db.execute_sql.assert_called_with("SELECT 1")

    def test_ensure_bound_connection_heals_already_closed(self):
        from ..utils.db_connections import ensure_bound_connection

        db = MagicMock()
        db.is_closed.return_value = False
        db.execute_sql.side_effect = [RuntimeError("connection already closed"), None]
        ensure_bound_connection(db)
        self.assertGreaterEqual(db.connect.call_count, 1)
        self.assertEqual(db.execute_sql.call_count, 2)

    def test_bind_historian_proxy_points_models_at_new_handle(self):
        from ..dbmodels.core import proxy
        from ..utils.db_connections import bind_historian_proxy

        original = proxy.obj
        previous = MagicMock(name="previous")
        candidate = MagicMock(name="candidate")
        try:
            bind_historian_proxy(previous)
            self.assertIs(proxy.obj, previous)
            bind_historian_proxy(candidate)
            self.assertIs(proxy.obj, candidate)
        finally:
            bind_historian_proxy(original)

    def test_historian_application_name_is_prefixed(self):
        from ..utils.db_connections import historian_application_name

        self.assertTrue(historian_application_name("LoggerWorker").startswith("PyAutomationIO:"))
        self.assertEqual(historian_application_name("LoggerWorker"), "PyAutomationIO:LoggerWorker")
        self.assertEqual(historian_application_name("SM-LDS"), "PyAutomationIO:SM-LDS")

    def test_ephemeral_historian_closes_when_not_logger_worker(self):
        from ..utils.db_connections import ephemeral_historian

        db = MagicMock()
        db.is_closed.return_value = False
        with patch("automation.utils.db_connections.keep_historian_socket", return_value=False):
            with ephemeral_historian(db):
                pass
        db.close.assert_called_once()

    def test_tracked_connect_skipped_during_outage(self):
        from peewee import OperationalError

        from ..utils.db_connections import TrackedPostgresqlDatabase
        from ..utils.db_io import mark_remote_db_dead, mark_remote_db_live

        mark_remote_db_dead(30.0)
        try:
            db = TrackedPostgresqlDatabase(None)
            with self.assertRaises(OperationalError):
                db._connect()
        finally:
            mark_remote_db_live()

    def test_ephemeral_historian_keeps_logger_worker_socket(self):
        from ..utils.db_connections import ephemeral_historian

        db = MagicMock()
        with patch("automation.utils.db_connections.keep_historian_socket", return_value=True):
            with ephemeral_historian(db):
                pass
        db.close.assert_not_called()


class TestJournalThenRemoteCloses(unittest.TestCase):
    def test_closes_caller_socket_after_remote_write(self):
        from datetime import datetime, timezone

        from ..persistence import outbox
        from ..persistence.records import PersistableRecord

        record = PersistableRecord.alarm_create(
            name="a1",
            state="Unacknowledged",
            timestamp=datetime.now(timezone.utc),
        )
        gateway = MagicMock()
        gateway.enqueue.return_value = 1
        db = MagicMock()
        db.is_closed.return_value = False
        app = MagicMock()
        app._db = db
        with patch.object(outbox, "get_persistence_gateway", return_value=gateway), \
             patch("automation.PyAutomation", return_value=app), \
             patch("automation.utils.db_connections.keep_historian_socket", return_value=False):
            result, journaled = outbox.journal_then_remote(record, lambda: object(), True)
        self.assertTrue(journaled)
        self.assertIsNotNone(result)
        db.close.assert_called()


def connections_over_threshold():
    from ..utils.db_connections import connections_alert_threshold

    return connections_alert_threshold() + 1
