import unittest
from unittest.mock import MagicMock, patch

from automation.workers.logger import LoggerWorker, _EMPTY_OPC_RETRY_S


def _idle_worker() -> LoggerWorker:
    worker = object.__new__(LoggerWorker)
    worker._opcua_empty_until = 0.0
    worker._opcua_empty_step = 0
    return worker


class TestOpcuaIdleReload(unittest.TestCase):
    def test_empty_node_does_not_poll_db_every_logger_period(self):
        worker = _idle_worker()
        app = MagicMock()
        app.opcua_client_manager._clients = {}
        app.is_db_connected.return_value = True

        with patch("automation.PyAutomation", return_value=app), patch(
            "automation.workers.logger.time.monotonic", return_value=1_000.0
        ):
            worker.check_opcua_connection()
        app.load_opcua_clients_from_db.assert_called_once()
        self.assertEqual(worker._opcua_empty_until, 1_000.0 + _EMPTY_OPC_RETRY_S[0])

        app.load_opcua_clients_from_db.reset_mock()
        with patch("automation.PyAutomation", return_value=app), patch(
            "automation.workers.logger.time.monotonic", return_value=1_010.0
        ):
            worker.check_opcua_connection()
        app.load_opcua_clients_from_db.assert_not_called()

        with patch("automation.PyAutomation", return_value=app), patch(
            "automation.workers.logger.time.monotonic", return_value=1_000.0 + _EMPTY_OPC_RETRY_S[0]
        ):
            worker.check_opcua_connection()
        app.load_opcua_clients_from_db.assert_called_once()
        self.assertEqual(worker._opcua_empty_step, 2)
        self.assertEqual(worker._opcua_empty_until, 1_000.0 + _EMPTY_OPC_RETRY_S[0] + _EMPTY_OPC_RETRY_S[1])

    def test_configured_client_skips_catalog_reload(self):
        worker = _idle_worker()
        worker._opcua_empty_until = 9_999.0
        worker._opcua_empty_step = 3
        app = MagicMock()
        app.opcua_client_manager._clients = {"PLC81": object()}

        with patch("automation.PyAutomation", return_value=app):
            worker.check_opcua_connection()

        app.load_opcua_clients_from_db.assert_not_called()
        self.assertEqual(worker._opcua_empty_until, 0.0)
        self.assertEqual(worker._opcua_empty_step, 0)
