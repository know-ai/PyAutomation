import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock

from automation.opcua_server.address_space import AddressSpaceBuilder
from automation.opcua_server.exposures.alarm_exposer import AlarmExposer
from automation.opcua_server.exposures.cvt_exposer import CvtExposer
from automation.opcua_server.exposures.engine_exposer import EngineExposer


class _Node:
    def __init__(self, identifier):
        self.nodeid = SimpleNamespace(to_string=lambda identifier=identifier: f"ns=2;s={identifier}")
        self.properties = []

    def add_property(self, nodeid, name, value):
        ident = getattr(nodeid, "identifier", name)
        prop = _Node(ident)
        self.properties.append(prop)
        return prop

    def get_properties(self):
        return list(self.properties)

    def set_data_value(self, _value):
        return None

    def set_value(self, _value):
        return None

    def get_attribute(self, _attr):
        return MagicMock()

    def set_attribute(self, _attr, _value):
        return None

    def get_display_name(self):
        return SimpleNamespace(Text="")


class _Folder:
    def __init__(self, name="root"):
        self.name = name
        self.children = []

    def add_folder(self, _idx, name):
        child = _Folder(name)
        self.children.append(child)
        return child

    def add_variable(self, nodeid, _name, _initial):
        ident = getattr(nodeid, "identifier", "x")
        return _Node(ident)


class _Tag:
    name = "Supe.Linea1.FI_01"
    segment = "Linea1"
    area = "Linea1"
    manufacturer = "Supe"
    display_name = "FI_01"
    filter_enabled = False
    quality = 1.0
    stale = False
    opc_status_code = None

    def get_data_type(self):
        return "float"

    def get_variable(self):
        return "Pressure"

    def get_unit(self):
        return "Pa"

    def get_scan_time(self):
        return None

    def get_dead_band(self):
        return 0

    def get_value(self):
        return 1.25

    def get_timestamp(self):
        return None


class TestExposers(unittest.TestCase):
    def test_cvt_analog_stays_within_node_budget(self):
        builder = AddressSpaceBuilder(_Folder(), 2)
        nodes, by_ns = {}, {}
        exposer = CvtExposer(builder, nodes, by_ns)
        node = exposer.upsert("Supe.Linea1.FI_01", _Tag())
        self.assertLessEqual(1 + len(node.get_properties()), 7)
        self.assertGreaterEqual(len(node.get_properties()), 3)

    def test_alarm_has_four_properties(self):
        builder = AddressSpaceBuilder(_Folder(), 2)
        exposer = AlarmExposer(builder, {}, {})
        state = SimpleNamespace(serialize=lambda: {"state": "Normal", "process_condition": "OK", "mnemonic": "L", "description": "d"})
        alarm = SimpleNamespace(name="alarm.LDS.leak", tag=_Tag(), state=state, description="d", display_name="leak")
        exposer.upsert(alarm.name, alarm)
        ident = next(iter(exposer._prop_nodes))
        self.assertEqual(exposer.property_count(ident), 4)

    def test_engine_has_three_properties(self):
        builder = AddressSpaceBuilder(_Folder(), 2)
        exposer = EngineExposer(builder, {}, {})
        engine = SimpleNamespace(
            name="LDS",
            segment="Linea1",
            manufacturer="Supe",
            serialize=lambda: {"state": "run", "classification": "LDS", "fluid": "diesel"},
        )
        exposer.upsert("LDS", engine)
        ident = next(iter(exposer._prop_nodes))
        self.assertEqual(exposer.property_count(ident), 3)
