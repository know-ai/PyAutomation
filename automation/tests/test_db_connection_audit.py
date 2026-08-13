import unittest
from unittest.mock import patch

from ..utils.db_audit import (
    DatabaseConnectionAuditor,
    build_db_event_description,
    summarize_db_config,
)


class TestSummarizeDbConfig(unittest.TestCase):
    def test_redacts_password_and_keeps_target(self):
        summary = summarize_db_config(
            {
                "dbtype": "postgresql",
                "host": "db.internal",
                "port": 5432,
                "name": "app_db",
                "user": "automation",
                "password": "super-secret",
            }
        )
        self.assertIn("type=postgresql", summary)
        self.assertIn("host=db.internal", summary)
        self.assertIn("port=5432", summary)
        self.assertIn("name=app_db", summary)
        self.assertIn("user=automation", summary)
        self.assertNotIn("super-secret", summary)
        self.assertNotIn("password", summary.lower())

    def test_sqlite_summary(self):
        self.assertEqual(
            summarize_db_config({"dbtype": "sqlite", "dbfile": "app.db", "password": "x"}),
            "type=sqlite dbfile=app.db",
        )

    def test_unknown_when_missing(self):
        self.assertEqual(summarize_db_config(None), "target=unknown")
        self.assertEqual(summarize_db_config({}), "target=unknown")

    def test_description_is_clipped_and_structured(self):
        description = build_db_event_description(
            target="type=postgresql host=db port=5432 name=app",
            source="watchdog",
            reason="connection-lost",
            attempts=6,
            error="x" * 400,
        )
        self.assertLessEqual(len(description), 256)
        self.assertIn("source=watchdog", description)
        self.assertTrue(description.endswith("…"))


class TestDatabaseConnectionAuditor(unittest.TestCase):
    def setUp(self):
        self.auditor = DatabaseConnectionAuditor()

    def _messages(self, persist):
        return [call.kwargs["message"] for call in persist.call_args_list]

    def test_connect_success_is_audited(self):
        with patch("automation.utils.db_audit.persist_system_event", return_value=True) as persist:
            self.auditor.notify_connect_success(
                source="core-startup",
                target="type=sqlite dbfile=app.db",
            )

        self.assertEqual(self.auditor.state, "connected")
        self.assertEqual(self._messages(persist), ["Database connected"])
        self.assertIn("source=core-startup", persist.call_args.kwargs["description"])
        self.assertEqual(persist.call_args.kwargs["classification"], "Database")

    def test_connect_failure_is_buffered_when_store_is_down(self):
        with patch("automation.utils.db_audit.persist_system_event", return_value=False):
            self.auditor.notify_connect_failure(
                source="core-startup",
                target="type=postgresql host=db port=5432 name=app",
                error="could not connect",
            )

        self.assertEqual(self.auditor.pending_actions, ("CONNECTION_FAILED",))

    def test_outage_does_not_flood_and_flushes_chronologically(self):
        with patch("automation.utils.db_audit.persist_system_event", return_value=True) as persist:
            self.auditor.notify_connect_success(source="core-startup", target="type=sqlite dbfile=app.db")
            persist.reset_mock()
            persist.return_value = False

            self.auditor.notify_link_lost(source="watchdog")
            self.auditor.notify_link_lost(source="watchdog")
            for index in range(12):
                self.auditor.notify_reconnect_attempt(source="watchdog")
                self.auditor.notify_reconnect_failure(error=f"refused-{index}")

            self.assertEqual(self.auditor.pending_actions, ("DISCONNECTED", "RECONNECTING"))
            persist.reset_mock()
            persist.return_value = True

            self.auditor.notify_reconnect_success(source="watchdog", target="type=sqlite dbfile=app.db")

        self.assertEqual(
            self._messages(persist),
            [
                "Database disconnected",
                "Database reconnecting",
                "Database reconnected",
            ],
        )
        reconnected = persist.call_args_list[-1].kwargs
        self.assertIn("attempts=12", reconnected["description"])
        self.assertIn("error=refused-11", reconnected["description"])
        self.assertEqual(self.auditor.state, "connected")
        self.assertEqual(self.auditor.pending_actions, ())

    def test_requested_disconnect_is_audited_once_before_drop(self):
        with patch("automation.utils.db_audit.persist_system_event", return_value=True) as persist:
            self.auditor.notify_connect_success(source="connect", target="type=sqlite dbfile=app.db")
            persist.reset_mock()
            self.auditor.notify_disconnect_requested(source="disconnect")
            self.auditor.notify_disconnect_requested(source="disconnect")

        self.assertEqual(self._messages(persist), ["Database disconnected"])
        self.assertIn("reason=requested", persist.call_args.kwargs["description"])
        self.assertEqual(self.auditor.state, "disconnected")

    def test_never_raises_when_persist_explodes(self):
        with patch(
            "automation.utils.db_audit.persist_system_event",
            side_effect=RuntimeError("store down"),
        ):
            self.auditor.notify_connect_success(source="connect")
            self.auditor.notify_connect_failure(error="boom")
            self.auditor.notify_link_lost()
            self.auditor.notify_reconnect_attempt()
            self.auditor.notify_reconnect_failure(error="boom")
            self.auditor.notify_reconnect_success()
            self.auditor.notify_disconnect_requested()
            self.auditor.flush()
