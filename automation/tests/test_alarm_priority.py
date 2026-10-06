import unittest

from automation.alarms.p2.constants import alarm_priority_or_default, coerce_alarm_priority
from automation.alarms.p2.priority import PriorityManager


class AlarmPriorityTests(unittest.TestCase):
    def test_coerce_default_and_scale(self):
        self.assertEqual(coerce_alarm_priority(None), 4)
        self.assertEqual(coerce_alarm_priority(1), 1)
        self.assertEqual(coerce_alarm_priority("4"), 4)

    def test_coerce_rejects_out_of_range(self):
        with self.assertRaises(ValueError):
            coerce_alarm_priority(0)
        with self.assertRaises(ValueError):
            coerce_alarm_priority(5)

    def test_bad_value_falls_back_on_load(self):
        self.assertEqual(alarm_priority_or_default("nope"), 4)
        self.assertEqual(alarm_priority_or_default(9), 4)

    def test_manager_records_the_change(self):
        manager = PriorityManager()
        manager.set_priority("a", 1, op_id=7, reason="rationalization")
        self.assertEqual(manager.get_priority("a"), 1)
        event = manager._events.last()
        self.assertEqual(event["name"], "ALM.PRIORITY.CHANGED")
        self.assertEqual(event["to_priority"], 1)


if __name__ == "__main__":
    unittest.main()
