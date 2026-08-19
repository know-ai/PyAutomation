import os
import unittest
from unittest.mock import patch

from flask import Flask

from .. import PyAutomation
from ..utils import connection_alarms as conn_alarms


class TestConnectionAlarms(unittest.TestCase):
    def setUp(self) -> None:
        file_path = os.path.join(".", "db", "test.db")
        if os.path.exists(file_path):
            os.remove(file_path)
        self.app = PyAutomation()
        self.server = Flask(__name__)
        self.app.run(server=self.server, debug=True, test=True, create_tables=True)
        self._reset_db_alarm()
        return super().setUp()

    def tearDown(self) -> None:
        self.app.safe_stop()
        return super().tearDown()

    def _alarm_state(self, alarm):
        return alarm.state.state.lower()

    def _reset_db_alarm(self):
        conn_alarms.set_db_disconnected(False)
        alarm = self.app.alarm_manager.get_alarm_by_name(conn_alarms.DB_ALARM_NAME)
        if alarm is None:
            return
        current = alarm.current_state.name.lower()
        if current in ("unack_alarm", "rtn_unack"):
            alarm.acknowledge()
        conn_alarms.set_db_disconnected(False)

    def test_database_connection_alarm_is_created_once_on_connect(self):
        alarm = self.app.alarm_manager.get_alarm_by_name(conn_alarms.DB_ALARM_NAME)
        tag = self.app.cvt.get_tag_by_name(conn_alarms.DB_TAG_NAME)

        self.assertIsNotNone(tag)
        self.assertIsNotNone(alarm)
        self.assertEqual(alarm.alarm_setpoint.type.value, "BOOL")
        self.assertEqual(alarm.alarm_setpoint.value, True)
        self.assertEqual(self._alarm_state(alarm), "normal")

        conn_alarms.ensure_db_connection_alarm()
        conn_alarms.ensure_db_connection_alarm()
        matches = [
            item
            for _, item in self.app.get_alarms().items()
            if item.name == conn_alarms.DB_ALARM_NAME
        ]
        self.assertEqual(len(matches), 1)

    def test_database_disconnect_ack_and_restore(self):
        alarm = self.app.alarm_manager.get_alarm_by_name(conn_alarms.DB_ALARM_NAME)
        self.assertEqual(self._alarm_state(alarm), "normal")

        conn_alarms.set_db_disconnected(True)
        self.assertEqual(self._alarm_state(alarm), "unacknowledged")
        self.assertEqual(alarm.state.alarm_status, "Active")

        alarm.acknowledge()
        self.assertEqual(self._alarm_state(alarm), "acknowledged")
        self.assertEqual(alarm.state.alarm_status, "Active")

        conn_alarms.set_db_disconnected(False)
        self.assertEqual(self._alarm_state(alarm), "normal")
        self.assertEqual(alarm.state.alarm_status, "Not Active")

    def test_database_return_to_normal_unacknowledged(self):
        alarm = self.app.alarm_manager.get_alarm_by_name(conn_alarms.DB_ALARM_NAME)

        conn_alarms.set_db_disconnected(True)
        self.assertEqual(self._alarm_state(alarm), "unacknowledged")

        conn_alarms.set_db_disconnected(False)
        self.assertEqual(self._alarm_state(alarm), "rtn unacknowledged")

        alarm.acknowledge()
        self.assertEqual(self._alarm_state(alarm), "normal")

    def test_opcua_connection_alarm_lifecycle_without_second_definition(self):
        client_name = "PLC1"
        conn_alarms.ensure_opcua_connection_alarm(client_name)
        alarm = self.app.alarm_manager.get_alarm_by_name(conn_alarms.opcua_alarm_name(client_name))
        tag = self.app.cvt.get_tag_by_name(conn_alarms.opcua_tag_name(client_name))

        self.assertIsNotNone(tag)
        self.assertIsNotNone(alarm)
        self.assertEqual(alarm.alarm_setpoint.type.value, "BOOL")
        self.assertEqual(self._alarm_state(alarm), "normal")

        conn_alarms.set_opcua_disconnected(client_name, True)
        conn_alarms.set_opcua_disconnected(client_name, True)
        self.assertEqual(self._alarm_state(alarm), "unacknowledged")

        matches = [
            item
            for _, item in self.app.get_alarms().items()
            if item.name == conn_alarms.opcua_alarm_name(client_name)
        ]
        self.assertEqual(len(matches), 1)

        alarm.acknowledge()
        self.assertEqual(self._alarm_state(alarm), "acknowledged")

        conn_alarms.set_opcua_disconnected(client_name, False)
        self.assertEqual(self._alarm_state(alarm), "normal")

    def test_opcua_client_connect_and_disconnect_drive_the_same_alarm(self):
        with patch("automation.opcua.models.OPCClient.__init__", return_value=None):
            from ..opcua.models import Client

            client = Client.__new__(Client)
            client._id = None
            client._server_url = "opc.tcp://10.0.0.8:4840"
            client._timeout = 60
            client.name = "PLC-FIELD"
            client._client = None
            client._is_open = False
            client._opc_ua_tree = dict()
            client._connection_state = "unknown"
            client._reconnect_attempts = 0
            client._reconnect_in_progress = False
            client._last_failure_event_monotonic = 0.0
            client._audit_source = "client-connect"
            client._suppress_connection_alarm = False

        with patch("automation.opcua.models.record_opcua_connection_event"), patch(
            "automation.opcua.models.OPCClient.connect", return_value=None
        ):
            result, status = client.connect()

        self.assertEqual(status, 200)
        alarm = self.app.alarm_manager.get_alarm_by_name(conn_alarms.opcua_alarm_name("PLC-FIELD"))
        self.assertIsNotNone(alarm)
        self.assertEqual(self._alarm_state(alarm), "normal")

        with patch("automation.opcua.models.record_opcua_connection_event"), patch(
            "automation.opcua.models.OPCClient.disconnect", return_value=None
        ):
            client.disconnect()

        self.assertEqual(self._alarm_state(alarm), "unacknowledged")
        alarm.acknowledge()
        self.assertEqual(self._alarm_state(alarm), "acknowledged")

        with patch("automation.opcua.models.record_opcua_connection_event"), patch(
            "automation.opcua.models.OPCClient.connect", return_value=None
        ):
            client.connect()

        self.assertEqual(self._alarm_state(alarm), "normal")
        matches = [
            item
            for _, item in self.app.get_alarms().items()
            if item.name == conn_alarms.opcua_alarm_name("PLC-FIELD")
        ]
        self.assertEqual(len(matches), 1)

    def test_disconnect_to_db_activates_existing_alarm(self):
        alarm = self.app.alarm_manager.get_alarm_by_name(conn_alarms.DB_ALARM_NAME)
        self.assertEqual(self._alarm_state(alarm), "normal")

        self.app.disconnect_to_db()
        self.assertEqual(self._alarm_state(alarm), "unacknowledged")
        self.assertFalse(self.app.is_db_connected())

    def test_reconnect_probe_failure_keeps_alarm_and_skips_hydrate(self):
        conn_alarms.set_db_disconnected(True)
        alarm = self.app.alarm_manager.get_alarm_by_name(conn_alarms.DB_ALARM_NAME)
        self.assertEqual(self._alarm_state(alarm), "unacknowledged")

        with patch.object(self.app, "get_db_config", return_value={"dbtype": "sqlite", "dbfile": "test.db"}), \
             patch.object(self.app, "set_db"), \
             patch.object(self.app, "_historian_is_live", return_value=False), \
             patch.object(self.app, "load_opcua_clients_from_db") as load_opcua, \
             patch.object(self.app, "load_db_to_alarm_manager") as load_alarms, \
             patch.object(self.app, "load_db_to_roles") as load_roles, \
             patch.object(self.app, "load_db_to_users") as load_users, \
             patch.object(self.app, "load_db_tags_to_machine") as load_tags:
            ok = self.app.reconnect_to_db(source="watchdog")

        self.assertFalse(ok)
        self.assertFalse(self.app._db_live)
        self.assertFalse(self.app.is_db_connected())
        load_opcua.assert_not_called()
        load_alarms.assert_not_called()
        load_roles.assert_not_called()
        load_users.assert_not_called()
        load_tags.assert_not_called()
        self.assertEqual(self._alarm_state(alarm), "unacknowledged")
        self.assertEqual(alarm.state.alarm_status, "Active")

    def test_reconnect_success_clears_alarm_after_ack(self):
        conn_alarms.set_db_disconnected(True)
        alarm = self.app.alarm_manager.get_alarm_by_name(conn_alarms.DB_ALARM_NAME)
        self.assertEqual(self._alarm_state(alarm), "unacknowledged")
        alarm.acknowledge()

        ok = self.app.reconnect_to_db(test=True)
        self.assertTrue(ok)
        self.assertTrue(self.app._db_live)
        self.assertTrue(self.app.is_db_connected())
        self.assertEqual(self._alarm_state(alarm), "normal")
        self.assertEqual(alarm.state.alarm_status, "Not Active")

    def test_ntp_sync_alarm_created_with_multi_edge_system_tag(self):
        from unittest.mock import MagicMock

        from ..utils.connection_alarms import _ensure_bool_alarm

        scope = MagicMock()
        scope.enabled = True
        scope.is_valid = True
        scope.area = "Linea1"
        scope.site = "Supe"
        scope.node_id = "edge-linea1"
        scope.owns_area = lambda _area: True
        scope.owns_node = lambda _node: True

        tag_name = "Linea1.SYS.NTP.OutOfSync"
        alarm_name = "Linea1.ALM.NTP.OutOfSync"

        env = {
            "AUTOMATION_MULTI_EDGE_ENABLED": "true",
            "AUTOMATION_NODE_ID": "edge-linea1",
            "AUTOMATION_SEGMENT": "Linea1",
            "AUTOMATION_MANUFACTURER": "Supe",
        }
        with patch.dict(os.environ, env, clear=False), patch(
            "automation.node_scope.get_node_scope", return_value=scope
        ), patch.object(self.app, "_refresh_node_scope", return_value=scope):
            _ensure_bool_alarm(
                self.app,
                tag_name=tag_name,
                alarm_name=alarm_name,
                tag_description="True when the edge clock is out of sync with plant NTP",
                alarm_description="Edge clock out of sync with plant NTP",
                display_name="NTP Out Of Sync",
            )

        tag = self.app.cvt.get_tag_by_name(tag_name)
        alarm = self.app.alarm_manager.get_alarm_by_name(alarm_name)
        self.assertIsNotNone(tag)
        self.assertIsNotNone(alarm)
        self.assertEqual(alarm.alarm_setpoint.type.value, "BOOL")
        self.assertEqual(self._alarm_state(alarm), "normal")
