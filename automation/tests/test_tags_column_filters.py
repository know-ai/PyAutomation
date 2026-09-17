# -*- coding: utf-8 -*-
import unittest

from automation.modules.tags.filters import filter_serialized_tags


class TestFilterSerializedTags(unittest.TestCase):
    def setUp(self):
        self.tags = [
            {
                "name": "Supe.Linea1.PI_01",
                "variable": "Pressure",
                "value": 12.5,
                "display_unit": "bar",
                "opcua_client_name": "PLC",
                "node_namespace": "ns=2;s=PI_01",
                "scan_time": 1.0,
                "dead_band": 0.1,
            },
            {
                "name": "Supe.Linea1.PI_02",
                "variable": "Pressure",
                "value": True,
                "display_unit": "bar",
                "opcua_address": "opc.tcp://host",
                "node_namespace": "ns=2;s=PI_02",
                "scan_time": 1.0,
            },
            {
                "name": "Supe.Linea1.FI_01",
                "variable": "Flow",
                "value": None,
                "display_unit": "",
                "opcua_client_name": "FlowComputer",
                "scan_time": 0.5,
                "dead_band": 0,
            },
        ]

    def test_no_filters_returns_all(self):
        self.assertEqual(len(filter_serialized_tags(self.tags)), 3)

    def test_name_substring_then_ready_to_page(self):
        matched = filter_serialized_tags(self.tags, name="PI_")
        self.assertEqual([tag["name"] for tag in matched], [
            "Supe.Linea1.PI_01",
            "Supe.Linea1.PI_02",
        ])

    def test_name_filter_is_case_insensitive(self):
        matched = filter_serialized_tags(self.tags, name="fi_01")
        self.assertEqual(len(matched), 1)
        self.assertEqual(matched[0]["name"], "Supe.Linea1.FI_01")

    def test_combined_filters(self):
        matched = filter_serialized_tags(self.tags, name="Linea1", variable="flow")
        self.assertEqual(len(matched), 1)
        self.assertEqual(matched[0]["name"], "Supe.Linea1.FI_01")

    def test_value_formats_bool_and_dash(self):
        self.assertEqual(len(filter_serialized_tags(self.tags, value="true")), 1)
        self.assertEqual(len(filter_serialized_tags(self.tags, value="-")), 1)

    def test_opcua_falls_back_to_address(self):
        matched = filter_serialized_tags(self.tags, opcua_client="opc.tcp")
        self.assertEqual(len(matched), 1)
        self.assertEqual(matched[0]["name"], "Supe.Linea1.PI_02")


if __name__ == "__main__":
    unittest.main()
