import time
import unittest
from unittest.mock import MagicMock, patch


class TestOpcuaAuditHelper(unittest.TestCase):
    def test_clip_keeps_short_text(self):
        from ..utils.opcua_audit import clip

        self.assertEqual(clip("client=PLC1 url=opc.tcp://10.0.0.1:4840", 256), "client=PLC1 url=opc.tcp://10.0.0.1:4840")

    def test_clip_truncates_long_text(self):
        from ..utils.opcua_audit import clip

        text = "e" * 300
        out = clip(text, 256)
        self.assertEqual(len(out), 256)
        self.assertTrue(out.endswith("…"))

    def test_queues_when_system_user_missing_and_flushes(self):
        from ..utils import opcua_audit

        opcua_audit.clear_pending_opcua_audits()
        user = MagicMock(name="system")
        with patch.object(opcua_audit, "_get_system_user", return_value=None):
            self.assertFalse(
                opcua_audit.record_opcua_connection_event(
                    action="CONNECTED",
                    client_name="PLC1",
                    server_url="opc.tcp://127.0.0.1:4840",
                )
            )
        with patch.object(opcua_audit, "_get_system_user", return_value=user), patch.object(
            opcua_audit,
            "persist_system_event",
            return_value=True,
        ) as persist:
            self.assertEqual(opcua_audit.flush_pending_opcua_audits(), 1)
            persist.assert_called_once()
        opcua_audit.clear_pending_opcua_audits()



class TestOpcuaClientConnectionAudit(unittest.TestCase):
    def _client(self):
        from ..opcua.models import Client

        client = Client.__new__(Client)
        client._id = None
        client._server_url = "opc.tcp://10.0.0.8:4840"
        client._timeout = 60
        client.name = "PLC1"
        client._client = None
        client._is_open = False
        client._opc_ua_tree = dict()
        client._connection_state = "unknown"
        client._reconnect_attempts = 0
        client._reconnect_in_progress = False
        client._last_failure_event_monotonic = 0.0
        client._audit_source = "client-connect"
        client._suppress_connection_alarm = True
        client._username = None
        client._password = None
        client._inflight = {}
        return client

    @patch("automation.opcua.models.record_opcua_connection_event")
    @patch("automation.opcua.models.sync_adapter.open_session")
    def test_initial_connect_success_is_audited(self, super_connect, record_event):
        client = self._client()
        super_connect.return_value = None

        with patch("automation.opcua.models._scope_owns_node", return_value=True):
            result, status = client.connect()

        self.assertEqual(status, 200)
        self.assertEqual(result["is_connected"], True)
        record_event.assert_called()
        kwargs = record_event.call_args.kwargs
        self.assertEqual(kwargs["action"], "CONNECTED")
        self.assertEqual(kwargs["client_name"], "PLC1")
        self.assertEqual(kwargs["server_url"], "opc.tcp://10.0.0.8:4840")

    @patch("automation.opcua.models.record_opcua_connection_event")
    @patch("automation.opcua.models.sync_adapter.open_session", side_effect=OSError("server down"))
    def test_initial_connect_failure_includes_error(self, _super_connect, record_event):
        client = self._client()

        with patch("automation.opcua.models._scope_owns_node", return_value=True):
            result, status = client.connect()

        self.assertEqual(status, 404)
        kwargs = record_event.call_args.kwargs
        self.assertEqual(kwargs["action"], "CONNECTION_FAILED")
        self.assertIn("OSError", kwargs["error"])
        self.assertIn("server down", result["error"])

    @patch("automation.opcua.models.record_opcua_connection_event")
    @patch("automation.opcua.models.sync_adapter.open_session", side_effect=OSError("timeout"))
    def test_reconnect_failure_is_rate_limited(self, _super_connect, record_event):
        client = self._client()
        client._connection_state = "disconnected"
        client._reconnect_in_progress = True
        client._reconnect_attempts = 2
        client._last_failure_event_monotonic = time.monotonic()

        with patch("automation.opcua.models._scope_owns_node", return_value=True):
            client.connect()
            client.connect()

        failed = [c.kwargs["action"] for c in record_event.call_args_list]
        self.assertEqual(failed, [])

    @patch("automation.opcua.models.record_opcua_connection_event")
    def test_reconnect_noop_when_already_connected(self, record_event):
        client = self._client()
        client.is_connected = MagicMock(return_value=True)

        self.assertIsNone(client.reconnect())
        record_event.assert_not_called()

    @patch("automation.opcua.models.Client._emit_opcua_socket")
    @patch("automation.opcua.models.record_opcua_connection_event")
    @patch("automation.opcua.models.sync_adapter.close_session")
    def test_operator_hold_keeps_the_endpoint_and_skips_reconnect(self, _close, _record, _emit):
        client = self._client()
        client._is_open = True
        client._connection_state = "connected"
        client._manual_hold = False

        payload, status = client.disconnect(retain_endpoint=True)

        self.assertEqual(status, 200)
        self.assertTrue(payload["manual_hold"])
        self.assertEqual(client._server_url, "opc.tcp://10.0.0.8:4840")
        self.assertTrue(client._manual_hold)
        self.assertIsNone(client.reconnect())

    @patch("automation.opcua.models.record_opcua_connection_event")
    @patch("automation.opcua.models.sync_adapter.open_session")
    def test_explicit_connect_clears_operator_hold(self, _open, _record):
        client = self._client()
        client._manual_hold = True

        with patch("automation.opcua.models._scope_owns_node", return_value=True):
            _payload, status = client.connect()

        self.assertEqual(status, 200)
        self.assertFalse(client._manual_hold)

    def test_watchdog_does_not_reopen_a_held_client(self):
        from ..workers.logger import LoggerWorker

        client = self._client()
        client._manual_hold = True
        worker = LoggerWorker.__new__(LoggerWorker)
        worker._opcua_empty_until = 0.0
        worker._opcua_empty_step = 0
        app = MagicMock()
        app.opcua_client_manager._clients = {client.name: client}
        with patch("automation.workers.logger._scope_owns_node", return_value=True), patch(
            "automation.PyAutomation", return_value=app
        ), patch.object(client, "is_connected", return_value=False), patch.object(
            client, "reconnect"
        ) as reconnect:
            worker.check_opcua_connection()
        reconnect.assert_not_called()

    def test_embedded_endpoint_is_recognized_and_a_waiter_is_not_reconnected(self):
        import os

        from ..managers.opcua_client import targets_local_embedded_server
        from ..workers.logger import LoggerWorker

        with patch.dict(os.environ, {"AUTOMATION_OPCUA_SERVER_PORT": "53530"}):
            self.assertTrue(targets_local_embedded_server("127.0.0.1", 53530))
            self.assertFalse(targets_local_embedded_server("10.0.0.8", 4840))
        client = self._client()
        client._awaiting_embedded = True
        worker = LoggerWorker.__new__(LoggerWorker)
        worker._opcua_empty_until = 0.0
        worker._opcua_empty_step = 0
        app = MagicMock()
        app.opcua_client_manager._clients = {client.name: client}
        with patch("automation.workers.logger._scope_owns_node", return_value=True), patch(
            "automation.PyAutomation", return_value=app
        ), patch.object(client, "is_connected", return_value=False), patch.object(
            client, "reconnect"
        ) as reconnect:
            worker.check_opcua_connection()
        reconnect.assert_not_called()
