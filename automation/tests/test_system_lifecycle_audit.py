import unittest
from unittest.mock import patch

from ..utils.system_lifecycle_audit import (
    record_system_started,
    record_system_stopped,
    reset_system_lifecycle_audit,
)


class TestSystemLifecycleAudit(unittest.TestCase):
    def setUp(self):
        reset_system_lifecycle_audit()

    def tearDown(self):
        reset_system_lifecycle_audit()

    def test_boot_is_recorded_once(self):
        with patch(
            "automation.utils.system_lifecycle_audit.persist_system_event",
            return_value=True,
        ) as persist:
            self.assertTrue(record_system_started())
            self.assertFalse(record_system_started())

        persist.assert_called_once()
        kwargs = persist.call_args.kwargs
        self.assertEqual(kwargs["message"], "System started")
        self.assertEqual(kwargs["classification"], "System")
        self.assertEqual(kwargs["description"], "boot")

    def test_stop_is_recorded_once(self):
        with patch(
            "automation.utils.system_lifecycle_audit.persist_system_event",
            return_value=True,
        ) as persist:
            self.assertTrue(record_system_stopped())
            self.assertFalse(record_system_stopped())
        persist.assert_called_once()
        kwargs = persist.call_args.kwargs
        self.assertEqual(kwargs["message"], "System stopped")
        self.assertEqual(kwargs["classification"], "System")

    def test_never_raises(self):
        with patch(
            "automation.utils.system_lifecycle_audit.persist_system_event",
            side_effect=RuntimeError("db"),
        ):
            self.assertFalse(record_system_started())
