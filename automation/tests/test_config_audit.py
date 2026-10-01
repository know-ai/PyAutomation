import unittest
from unittest.mock import MagicMock, patch


class TestConfigAuditDiffs(unittest.TestCase):
    def test_realtime_trends_ignores_timestamp_only_saves(self):
        from ..utils.config_audit import realtime_trends_changes

        chart = {
            "id": "a",
            "title": "Inlet",
            "tagNames": ["PT-1"],
            "timeSpanMinutes": 15,
            "x": 0,
            "y": 0,
            "w": 6,
            "h": 4,
        }
        before = {"panelTitle": "Trends", "updatedAt": "t1", "charts": [chart]}
        after = {"panelTitle": "Trends", "updatedAt": "t2", "charts": [dict(chart)]}
        self.assertEqual(realtime_trends_changes(before, after), [])

    def test_realtime_trends_add_edit_delete_and_move(self):
        from ..utils.config_audit import realtime_trends_changes

        before = {
            "panelTitle": "A",
            "charts": [
                {"id": "keep", "title": "Keep", "tagNames": ["A"], "timeSpanMinutes": 10, "x": 0, "y": 0, "w": 4, "h": 4},
                {"id": "gone", "title": "Gone", "tagNames": [], "timeSpanMinutes": 5, "x": 0, "y": 0, "w": 4, "h": 4},
            ],
        }
        after = {
            "panelTitle": "B",
            "charts": [
                {"id": "keep", "title": "Kept", "tagNames": ["A", "B"], "timeSpanMinutes": 10, "x": 1, "y": 0, "w": 4, "h": 4},
                {"id": "new", "title": "New", "tagNames": ["C"], "timeSpanMinutes": 30, "x": 0, "y": 1, "w": 4, "h": 4},
                {"id": "slide", "title": "Slide", "tagNames": ["D"], "timeSpanMinutes": 5, "x": 2, "y": 0, "w": 4, "h": 4},
            ],
        }
        # slide is new, not a move. Add a stable chart that only moves.
        before["charts"].append(
            {"id": "slide", "title": "Slide", "tagNames": ["D"], "timeSpanMinutes": 5, "x": 0, "y": 2, "w": 4, "h": 4}
        )
        messages = dict(realtime_trends_changes(before, after))
        self.assertIn("Real-time trends panel title updated", messages)
        self.assertIn("Real-time trend chart added", messages)
        self.assertIn("tags=C", messages["Real-time trend chart added"])
        self.assertIn("Real-time trend chart deleted", messages)
        self.assertIn("Gone", messages["Real-time trend chart deleted"])
        self.assertIn("Real-time trend chart updated", messages)
        self.assertIn("tags=A,B", messages["Real-time trend chart updated"])
        self.assertEqual(messages["Real-time trend layout updated"], "charts=Slide")

    def test_summary_columns_added_and_removed(self):
        from ..utils.config_audit import summary_column_changes

        changes = summary_column_changes(
            ["name", "state", "criticity"],
            ["name", "state", "description"],
        )
        self.assertEqual(len(changes), 1)
        self.assertEqual(changes[0][0], "Machines summary columns updated")
        self.assertIn("added=description", changes[0][1])
        self.assertIn("removed=criticity", changes[0][1])
        self.assertEqual(
            summary_column_changes(["name", "state"], ["name", "state"]),
            [],
        )

    def test_grants_only_report_differences(self):
        from ..utils.config_audit import grant_changes

        before = [
            {"resource_key": "hmi:view.settings", "action": "view", "effect": "allow"},
            {"resource_key": "hmi:view.authz", "action": "use", "effect": "deny"},
        ]
        saved = [
            {"resource_key": "hmi:view.settings", "action": "view", "effect": "allow"},
            {"resource_key": "hmi:view.authz", "action": "use", "effect": "allow"},
        ]
        changes = grant_changes("role", "operator", before, saved)
        self.assertEqual(len(changes), 1)
        self.assertIn("subject=role:operator", changes[0][1])
        self.assertIn("hmi:view.authz use deny->allow", changes[0][1])
        self.assertNotIn("hmi:view.settings", changes[0][1])
        self.assertEqual(grant_changes("role", "operator", before, before), [])

    def test_client_preference_rejects_unknown_values(self):
        from ..utils.config_audit import client_preference_change

        self.assertIsNone(client_preference_change("password", "secret"))
        self.assertIsNone(client_preference_change("theme", "neon"))
        message, description = client_preference_change("show_infra_machines", "true")
        self.assertEqual(message, "Workstation preference updated")
        self.assertEqual(description, "key=show_infra_machines to=true")

    def test_import_description_omits_nested_payloads(self):
        from ..utils.config_audit import import_description

        text = import_description("plant.json", {
            "summary": {"imported": 4, "password": "nope", "errors": {"tags": ["secret"]}},
        })
        self.assertIn("file=plant.json", text)
        self.assertIn("imported=4", text)
        self.assertNotIn("secret", text)
        self.assertNotIn("nope", text)

    def test_settings_description_is_from_to(self):
        from ..utils.config_audit import settings_change_description

        text = settings_change_description(
            {"log_level": 20, "logger_period": 1.0},
            {"log_level": 30, "logger_period": 1.0},
        )
        self.assertEqual(text, "log_level:20->30")
        self.assertIsNone(settings_change_description({"log_level": 20}, {"log_level": 20}))

    def test_record_uses_actor_and_never_raises(self):
        from ..utils import config_audit

        user = MagicMock()
        user.username = "integrator"
        with patch.object(config_audit, "persist_system_event", return_value=True) as persist:
            self.assertTrue(config_audit.record_configuration_event(
                message="OPC UA client created",
                description="client=line-1 host=10.0.0.8 port=4840",
                user=user,
            ))
        kwargs = persist.call_args.kwargs
        self.assertEqual(kwargs["classification"], "Configuration")
        self.assertEqual(kwargs["user"], user)
        self.assertNotIn("password", kwargs["description"])

        with patch.object(config_audit, "persist_system_event", side_effect=RuntimeError("db")):
            self.assertFalse(config_audit.record_configuration_event(
                message="x",
                description="y",
                user=user,
            ))


class TestUserEnabledAudit(unittest.TestCase):
    def test_disable_is_a_known_security_event(self):
        from ..utils import user_session_audit

        actor = MagicMock()
        actor.username = "admin"
        target = MagicMock()
        target.username = "operator1"
        with patch.object(user_session_audit, "persist_system_event", return_value=True) as persist:
            self.assertTrue(user_session_audit.record_user_session_event(
                action="USER_DISABLED",
                user=target,
                actor=actor,
            ))
        kwargs = persist.call_args.kwargs
        self.assertEqual(kwargs["message"], "User account disabled")
        self.assertEqual(kwargs["classification"], "Security")
        self.assertIn("username=operator1", kwargs["description"])
        self.assertIn("actor=admin", kwargs["description"])
        self.assertTrue(kwargs.get("plant_wide"))
