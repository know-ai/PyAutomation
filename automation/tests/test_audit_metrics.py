import unittest

from ..utils.audit_metrics import (
    cooldown_allows,
    events_rate_per_min,
    note_event_persisted,
    reset_audit_metrics,
    snapshot,
)


class TestAuditMetrics(unittest.TestCase):
    def setUp(self):
        reset_audit_metrics()

    def tearDown(self):
        reset_audit_metrics()

    def test_rate_counts_persisted_events(self):
        self.assertEqual(events_rate_per_min(), 0.0)
        note_event_persisted()
        note_event_persisted()
        self.assertEqual(events_rate_per_min(), 2.0)
        data = snapshot()
        self.assertEqual(data["EVENTS_RATE_PER_MIN"], 2.0)
        self.assertFalse(data["EVENTS_RATE_ALERT"])
        self.assertEqual(data["EVENTS_RATE_ALERT_THRESHOLD"], 30.0)

    def test_cooldown_allows_once_then_blocks(self):
        self.assertTrue(cooldown_allows("saf:backpressure", 60.0))
        self.assertFalse(cooldown_allows("saf:backpressure", 60.0))
        self.assertTrue(cooldown_allows("saf:disk", 60.0))
