# -*- coding: utf-8 -*-
import unittest
from unittest.mock import MagicMock, patch

from ..health import (
    DB_UNAVAILABLE_CODE,
    DB_UNAVAILABLE_MESSAGE,
    DatabaseHealthService,
    HealthSnapshot,
    UnavailablePayload,
    get_database_health_service,
    set_database_health_service,
)
from ..health.interfaces import IHealthProvider, IReconnectionHandler
from ..modules.health.require_db import db_unavailable_response, require_remote_db


class FakeHealth(IHealthProvider):
    def __init__(self, connected: bool):
        self.connected = connected

    def is_connected(self) -> bool:
        return self.connected

    def snapshot(self) -> HealthSnapshot:
        return HealthSnapshot(connected=self.connected, message="fake")


class TestUnavailablePayload(unittest.TestCase):
    def test_standard_body_has_no_secrets(self):
        body = UnavailablePayload().as_dict()
        self.assertEqual(body["status"], "error")
        self.assertEqual(body["code"], DB_UNAVAILABLE_CODE)
        self.assertEqual(body["retry_after"], 30)
        self.assertIn("almacenando localmente", body["message"])
        blob = str(body).lower()
        self.assertNotIn("password", blob)
        self.assertNotIn("postgres", blob)


class TestRequireRemoteDb(unittest.TestCase):
    def tearDown(self):
        set_database_health_service(None)

    def test_returns_503_when_disconnected(self):
        set_database_health_service(FakeHealth(False))

        @require_remote_db
        def handler():
            return {"ok": True}, 200

        body, status, headers = handler()
        self.assertEqual(status, 503)
        self.assertEqual(body["code"], DB_UNAVAILABLE_CODE)
        self.assertEqual(headers["Retry-After"], "30")

    def test_delegates_when_connected(self):
        set_database_health_service(FakeHealth(True))

        @require_remote_db
        def handler():
            return {"ok": True}, 200

        body, status = handler()
        self.assertEqual(status, 200)
        self.assertEqual(body, {"ok": True})


class TestDatabaseHealthService(unittest.TestCase):
    def tearDown(self):
        set_database_health_service(None)

    def test_disconnected_when_no_handle(self):
        service = DatabaseHealthService(timeout_s=0.2, cache_ttl_s=0)
        with patch.object(service, "_db_handle", return_value=None), patch.object(
            service, "_current_engine", return_value="PostgreSQL"
        ):
            snap = service.snapshot(force=True)
        self.assertFalse(snap.connected)
        self.assertEqual(snap.status, "error")
        self.assertEqual(snap.message, DB_UNAVAILABLE_MESSAGE)
        self.assertIsNone(snap.latency_ms)

    def test_connected_select_one(self):
        service = DatabaseHealthService(timeout_s=0.5, cache_ttl_s=0)
        db = MagicMock()
        db.execute_sql.return_value = None
        with patch.object(service, "_db_handle", return_value=db), patch.object(
            service, "_current_engine", return_value="PostgreSQL"
        ):
            snap = service.snapshot(force=True)
        self.assertTrue(snap.connected)
        self.assertEqual(snap.message, "PostgreSQL connected")
        self.assertIsNotNone(snap.latency_ms)
        db.execute_sql.assert_called_with("SELECT 1;")

    def test_timeout_fails_closed(self):
        service = DatabaseHealthService(timeout_s=0.05, cache_ttl_s=0)

        db = MagicMock()
        db.execute_sql.side_effect = TimeoutError("database health probe timed out")
        with patch.object(service, "_db_handle", return_value=db), patch.object(
            service, "_current_engine", return_value="PostgreSQL"
        ):
            snap = service.snapshot(force=True)
        self.assertFalse(snap.connected)
        self.assertEqual(snap.message, DB_UNAVAILABLE_MESSAGE)

    def test_cache_avoids_repeat_ping(self):
        service = DatabaseHealthService(timeout_s=0.5, cache_ttl_s=30)
        db = MagicMock()
        with patch.object(service, "_db_handle", return_value=db), patch.object(
            service, "_current_engine", return_value="PostgreSQL"
        ):
            first = service.snapshot()
            second = service.snapshot()
        self.assertTrue(first.connected)
        self.assertIs(first, second)
        self.assertEqual(db.execute_sql.call_count, 1)

    def test_factory_returns_injected_mock(self):
        fake = FakeHealth(False)
        set_database_health_service(fake)
        self.assertIs(get_database_health_service(), fake)
        self.assertIsInstance(get_database_health_service(), IHealthProvider)
        self.assertNotIsInstance(get_database_health_service(), IReconnectionHandler)

    def test_db_unavailable_response_tuple(self):
        body, status, headers = db_unavailable_response()
        self.assertEqual(status, 503)
        self.assertEqual(body["code"], "DB_UNAVAILABLE")
        self.assertEqual(headers["Retry-After"], "30")
