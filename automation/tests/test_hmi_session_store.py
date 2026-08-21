import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

from peewee import SqliteDatabase

from automation.dbmodels.core import proxy
from automation.dbmodels.hmi_sessions import HMISession


class TestHmiSessionStoreGetDb(unittest.TestCase):
    def test_get_db_reopens_closed_greenlet_handle(self):
        from automation.utils.hmi_session_store import _get_db

        db = MagicMock()
        db.is_closed.return_value = True
        app = MagicMock()
        app.is_db_connected.return_value = True
        app.db_manager.get_db.return_value = db
        with patch("automation.PyAutomation", return_value=app), patch(
            "automation.utils.db_connections.ensure_bound_connection"
        ) as ensure:
            self.assertIs(_get_db(), db)
        ensure.assert_called_once_with(db)


class TestHmiSessionStore(unittest.TestCase):
    def setUp(self):
        self.db = SqliteDatabase(":memory:")
        proxy.initialize(self.db)
        self.db.create_tables([HMISession])
        self.node_patcher = patch(
            "automation.utils.hmi_session_store.node_identity",
            return_value=("edge-a", "Line1"),
        )
        self.db_patcher = patch(
            "automation.utils.hmi_session_store._get_db",
            return_value=self.db,
        )
        self.close_patcher = patch(
            "automation.utils.hmi_session_store._close_historian_socket"
        )
        self.node_patcher.start()
        self.db_patcher.start()
        self.close_patcher.start()

    def tearDown(self):
        self.close_patcher.stop()
        self.db_patcher.stop()
        self.node_patcher.stop()
        self.db.drop_tables([HMISession])
        self.db.close()

    def test_upsert_and_count(self):
        from automation.utils.hmi_session_store import count_sessions, upsert_session

        self.assertTrue(upsert_session(sid="sid-1", username="op1", origin="10.0.0.1"))
        self.assertTrue(upsert_session(sid="sid-2", username="op2", origin="10.0.0.2"))
        self.assertEqual(count_sessions(), 2)

    def test_remove_session(self):
        from automation.utils.hmi_session_store import count_sessions, remove_session, upsert_session

        upsert_session(sid="sid-1", username="op1", origin="10.0.0.1")
        snapshot = remove_session("sid-1")
        self.assertIsNotNone(snapshot)
        self.assertEqual(snapshot.username, "op1")
        self.assertEqual(count_sessions(), 0)

    def test_touch_heartbeat(self):
        from automation.utils.hmi_session_store import touch_heartbeat, upsert_session

        upsert_session(sid="sid-1", username="op1", origin="10.0.0.1")
        row = HMISession.get_by_id("sid-1")
        old = row.last_heartbeat
        self.assertTrue(touch_heartbeat("sid-1"))
        row = HMISession.get_by_id("sid-1")
        self.assertGreaterEqual(row.last_heartbeat, old)

    def test_cleanup_stale_sessions(self):
        from automation.utils.hmi_session_store import cleanup_stale_sessions, upsert_session

        upsert_session(sid="sid-stale", username="op1", origin="10.0.0.1")
        stale = datetime.now(timezone.utc) - timedelta(minutes=5)
        HMISession.update(last_heartbeat=stale).where(HMISession.sid == "sid-stale").execute()
        removed = cleanup_stale_sessions(stale_seconds=120)
        self.assertEqual(removed, 1)


class TestHmiSocketAuditAplus(unittest.TestCase):
    @patch("automation.utils.hmi_socket_audit.persist_system_event", return_value=True)
    @patch("automation.utils.hmi_socket_audit.get_system_user")
    @patch("automation.utils.hmi_socket_audit.count_sessions", return_value=1)
    @patch("automation.utils.hmi_socket_audit.upsert_session", return_value=True)
    def test_valid_connect(self, upsert, _count, get_user, persist):
        from automation.utils.hmi_socket_audit import attempt_hmi_socket_connect

        user = MagicMock(username="operator")
        get_user.return_value = user
        with patch(
            "automation.utils.hmi_socket_audit.resolve_connect_user",
            return_value=(user, "operator", ""),
        ), patch(
            "automation.utils.hmi_socket_audit.socket_request_origin",
            return_value="192.168.10.20",
        ), patch(
            "automation.utils.hmi_socket_audit._edge_label",
            return_value="Plant.Line1",
        ):
            self.assertTrue(
                attempt_hmi_socket_connect(auth={"token": "abc"}, sid="sid-abc")
            )
        upsert.assert_called_once()
        self.assertEqual(persist.call_args.kwargs["message"], "HMI client connected")

    @patch("automation.utils.hmi_socket_audit.persist_system_event", return_value=True)
    @patch("automation.utils.hmi_socket_audit.get_system_user")
    @patch("automation.utils.hmi_socket_audit.count_sessions", return_value=0)
    def test_invalid_token_rejected(self, _count, get_user, persist):
        from automation.utils.hmi_socket_audit import attempt_hmi_socket_connect

        get_user.return_value = MagicMock(username="system")
        with patch(
            "automation.utils.hmi_socket_audit.resolve_connect_user",
            return_value=(None, "unknown", "invalid_token"),
        ), patch(
            "automation.utils.hmi_socket_audit.socket_request_origin",
            return_value="192.168.10.20",
        ), patch(
            "automation.utils.hmi_socket_audit._edge_label",
            return_value="Plant.Line1",
        ):
            self.assertFalse(
                attempt_hmi_socket_connect(auth={"token": "bad"}, sid="sid-x")
            )
        self.assertEqual(
            persist.call_args.kwargs["message"], "HMI client connection rejected"
        )
        self.assertIn("invalid_token", persist.call_args.kwargs["description"])

    @patch("automation.utils.hmi_socket_audit.persist_system_event", return_value=True)
    @patch("automation.utils.hmi_socket_audit.count_sessions", return_value=0)
    @patch("automation.utils.hmi_socket_audit.upsert_session", return_value=False)
    def test_session_store_unavailable_still_accepts(self, _upsert, _count, persist):
        """Local catalog autonomy: Socket.IO must not depend on historian sessions."""
        from automation.utils.hmi_socket_audit import attempt_hmi_socket_connect

        user = MagicMock(username="operator")
        with patch(
            "automation.utils.hmi_socket_audit.resolve_connect_user",
            return_value=(user, "operator", ""),
        ), patch(
            "automation.utils.hmi_socket_audit.socket_request_origin",
            return_value="192.168.10.20",
        ), patch(
            "automation.utils.hmi_socket_audit._edge_label",
            return_value="Plant.Line1",
        ):
            self.assertTrue(
                attempt_hmi_socket_connect(auth={"token": "abc"}, sid="sid-abc")
            )
        self.assertIn(
            "session_store_degraded",
            persist.call_args.kwargs["description"],
        )

    @patch("automation.utils.hmi_socket_audit.persist_system_event", return_value=True)
    @patch("automation.utils.hmi_socket_audit.get_system_user")
    @patch("automation.utils.hmi_socket_audit.count_sessions", return_value=0)
    @patch("automation.utils.hmi_socket_audit.remove_session")
    def test_disconnect_after_remove(self, remove_session, _count, get_user, persist):
        from automation.utils.hmi_session_store import StoredSession
        from automation.utils.hmi_socket_audit import register_hmi_socket_disconnect

        get_user.return_value = MagicMock(username="system")
        remove_session.return_value = StoredSession(
            sid="sid-abc",
            node_id="edge-a",
            username="operator",
            origin="192.168.10.20",
            area="Line1",
        )
        register_hmi_socket_disconnect(sid="sid-abc", reason="transport close")
        self.assertEqual(persist.call_args.kwargs["message"], "HMI client disconnected")


class TestHmiTlsTelemetryPerIp(unittest.TestCase):
    def setUp(self):
        from automation.utils.hmi_tls_telemetry import reset_for_tests

        reset_for_tests()

    def test_per_ip_rate_limit(self):
        import ssl

        from automation.utils.hmi_tls_telemetry import record_client_tls_failure

        err = ssl.SSLError(1, "certificate unknown")
        timeline = iter([0.0, 1.0, 301.0])
        with patch("automation.utils.hmi_tls_telemetry._IP_RATE_S", 300.0):
            with patch("automation.utils.hmi_tls_telemetry.time.monotonic", lambda: next(timeline)):
                with patch("automation.utils.system_event_audit.persist_system_event") as mock_event:
                    record_client_tls_failure(err, origin="10.0.0.55")
                    record_client_tls_failure(err, origin="10.0.0.55")
                    self.assertEqual(mock_event.call_count, 0)
                    record_client_tls_failure(err, origin="10.0.0.55")
                    self.assertEqual(mock_event.call_count, 1)
                    description = mock_event.call_args.kwargs.get("description") or ""
                    self.assertIn("origin=10.0.0.55", description)
                    self.assertEqual(
                        mock_event.call_args.kwargs.get("message"),
                        "HMI TLS handshake failure",
                    )


if __name__ == "__main__":
    unittest.main()
