import unittest

from automation.alarms.audio_profile import (
    cues_from_alarms,
    default_document,
    normalize_profiles,
    urgent_priority,
)


class _State:
    def __init__(self, state):
        self.state = state


class _Alarm:
    def __init__(self, identifier, state, priority=3):
        self.identifier = identifier
        self.state = _State(state)
        self.priority = priority


class AlarmAudioProfileTests(unittest.TestCase):
    def test_default_intervals_increase(self):
        profiles = normalize_profiles(default_document()["profiles"])
        seconds = [row["repeatSeconds"] for row in profiles]
        sounds = [row["soundId"] for row in profiles]
        self.assertEqual(seconds, [2, 5, 10, 30])
        self.assertEqual(sounds, [4, 4, 4, 4])

    def test_rejects_a_faster_lower_priority(self):
        rows = default_document()["profiles"]
        rows[3]["repeatSeconds"] = 2
        with self.assertRaises(ValueError):
            normalize_profiles(rows)

    def test_cues_ignore_return_to_normal(self):
        alarms = [
            _Alarm("a", "Unacknowledged", 2),
            _Alarm("b", "RTN Unacknowledged", 1),
            _Alarm("c", "Acknowledged", 1),
        ]
        cues = cues_from_alarms(alarms)
        self.assertEqual(cues, [{"id": "a", "priority": 2}])
        self.assertEqual(urgent_priority(cues), 2)

    def test_urgent_priority_is_the_lowest_number(self):
        self.assertEqual(
            urgent_priority([{"priority": 4}, {"priority": 1}, {"priority": 3}]),
            1,
        )
        self.assertIsNone(urgent_priority([]))


if __name__ == "__main__":
    unittest.main()
