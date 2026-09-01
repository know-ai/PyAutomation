# -*- coding: utf-8 -*-
import unittest

from automation.modules.alarms.filters import filter_serialized_alarms


def _alarm(name, description="", state="Normal", mnemonic="NORM", tag="T1"):
    return {
        "name": name,
        "description": description,
        "tag": tag,
        "state": {"mnemonic": mnemonic, "state": state},
    }


class TestAlarmDefinitionFilters(unittest.TestCase):
    def setUp(self):
        self.alarms = [
            _alarm("alarm.Linea1.Area.HighPress.H", "Alta presión", "Unacknowledged", "UNACK"),
            _alarm("alarm.Linea1.Area.LowPress.L", "Baja presión", "Normal", "NORM"),
            _alarm("SYS.ALM.PERF.CPU", "CPU above threshold", "Acknowledged", "ACKED"),
        ]

    def test_search_matches_name_or_description(self):
        by_name = filter_serialized_alarms(self.alarms, query="HighPress")
        self.assertEqual([item["name"] for item in by_name], ["alarm.Linea1.Area.HighPress.H"])
        by_desc = filter_serialized_alarms(self.alarms, query="presión")
        self.assertEqual(len(by_desc), 2)

    def test_state_matches_name_or_mnemonic(self):
        unack = filter_serialized_alarms(self.alarms, state="Unacknowledged")
        self.assertEqual(len(unack), 1)
        self.assertEqual(unack[0]["state"]["mnemonic"], "UNACK")
        by_mnemonic = filter_serialized_alarms(self.alarms, state="NORM")
        self.assertEqual(len(by_mnemonic), 1)
        self.assertEqual(by_mnemonic[0]["name"], "alarm.Linea1.Area.LowPress.L")

    def test_search_and_state_combine(self):
        matched = filter_serialized_alarms(self.alarms, query="press", state="Normal")
        self.assertEqual([item["name"] for item in matched], ["alarm.Linea1.Area.LowPress.L"])

    def test_empty_filters_return_all(self):
        self.assertEqual(len(filter_serialized_alarms(self.alarms)), 3)


if __name__ == "__main__":
    unittest.main()
