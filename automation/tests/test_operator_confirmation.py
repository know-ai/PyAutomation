import os
import tempfile
import unittest

from ..utils.operator_confirmation import (
    action_requires_confirmation,
    consume_confirmation_token,
    issue_confirmation_token,
    reset_confirmation_tokens,
)
from ..modules.settings.operator_confirmation import (
    load_operator_confirmation,
    save_operator_confirmation,
)


class TestOperatorConfirmationPolicy(unittest.TestCase):
    def test_missing_file_is_disabled(self):
        document = load_operator_confirmation(path=os.path.join(tempfile.gettempdir(), "missing-opc.json"))
        self.assertFalse(document["enabled"])

    def test_save_survives_a_reload(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "hmi_operator_confirmation.json")
            saved = save_operator_confirmation(True, path=path)
            self.assertTrue(saved["enabled"])
            loaded = load_operator_confirmation(path=path)
            self.assertTrue(loaded["enabled"])
            save_operator_confirmation(False, path=path)
            self.assertFalse(load_operator_confirmation(path=path)["enabled"])


class TestOperatorConfirmationToken(unittest.TestCase):
    def setUp(self):
        reset_confirmation_tokens()
        self.secret = "test-secret"

    def test_acknowledge_and_restart_are_gated(self):
        self.assertTrue(action_requires_confirmation("POST", "/api/alarms/acknowledge/PT-1"))
        self.assertTrue(action_requires_confirmation("POST", "/api/alarms/acknowledge_all"))
        self.assertTrue(action_requires_confirmation("PUT", "/api/machines/LDS/transition", "restart"))
        self.assertTrue(action_requires_confirmation("PUT", "/api/leaks/report/12"))
        self.assertFalse(action_requires_confirmation("PUT", "/api/machines/LDS/transition", "stop"))
        self.assertFalse(action_requires_confirmation("GET", "/api/leaks/metrics/false-alarms"))
        self.assertFalse(action_requires_confirmation("POST", "/api/alarms/shelve/PT-1"))

    def test_token_is_single_use_and_bound_to_the_action(self):
        token = issue_confirmation_token(
            username="supervisor",
            method="POST",
            path="/api/alarms/acknowledge/PT-1",
            secret=self.secret,
        )
        self.assertTrue(token)
        self.assertEqual(
            consume_confirmation_token(
                token,
                method="POST",
                path="/api/alarms/acknowledge/PT-1",
                secret=self.secret,
            ),
            "supervisor",
        )
        self.assertIsNone(
            consume_confirmation_token(
                token,
                method="POST",
                path="/api/alarms/acknowledge/PT-1",
                secret=self.secret,
            )
        )

    def test_token_rejects_a_different_restart_target(self):
        token = issue_confirmation_token(
            username="supervisor",
            method="PUT",
            path="/api/machines/LDS/transition",
            secret=self.secret,
            target_state="restart",
        )
        self.assertIsNone(
            consume_confirmation_token(
                token,
                method="PUT",
                path="/api/machines/LDS/transition",
                secret=self.secret,
                target_state="stop",
            )
        )
        self.assertEqual(
            consume_confirmation_token(
                token,
                method="PUT",
                path="/api/machines/LDS/transition",
                secret=self.secret,
                target_state="Restart",
            ),
            "supervisor",
        )
