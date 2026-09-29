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
        self.assertLessEqual(1 + len(node.get_properties()), 6)
        self.assertGreaterEqual(len(node.get_properties()), 2)
        published = exposer._props[next(iter(exposer._props))]
        self.assertIn("unit", published)
        self.assertNotIn("EngineeringUnits", published)
        self.assertNotIn("area", published)

    def test_published_unit_follows_the_display_unit(self):
        from automation.opcua_server.async_core.snapshots import _tag_properties
        from automation.opcua_server.exposures.common import published_unit

        tag = _Tag()
        tag.get_display_unit = lambda: "kg/lt"
        self.assertEqual(published_unit(tag), "kg/lt")
        props = dict(_tag_properties(SimpleNamespace(analog_item_supported=True), tag, "analog"))
        self.assertEqual(props["unit"], "kg/lt")
        self.assertNotIn("EngineeringUnits", props)
        self.assertNotIn("area", props)
        tag.get_display_unit = lambda: ""
        self.assertEqual(published_unit(tag), "Pa")

    def test_value_write_carries_the_display_unit(self):
        from automation.opcua_server.async_core.snapshots import write_item

        tag = SimpleNamespace(
            name="Supe.Linea1.DI_02",
            segment="Linea1",
            area="Linea1",
            quality=1.0,
            stale=False,
            opc_status_code=None,
            get_unit=lambda: "kg/m3",
            get_display_unit=lambda: "kg/lt",
            get_data_type=lambda: "float",
            get_variable=lambda: "Density",
            get_value=lambda: 1.25,
            get_timestamp=lambda: None,
        )
        server = SimpleNamespace(cvt=SimpleNamespace(get_tag_by_name=lambda name: tag))
        item = write_item(server, "t", tag.name, None)
        self.assertEqual(item.unit, "kg/lt")

    def test_alarm_write_uses_the_linked_tag_value(self):
        from automation.opcua_server.async_core.snapshots import write_item

        tag = SimpleNamespace(
            name="Linea1.SYS.PERF.CPU",
            segment="Linea1",
            area="Linea1",
            quality=1.0,
            stale=False,
            get_value=lambda: 37.5,
            get_timestamp=lambda: None,
        )
        alarm = SimpleNamespace(
            name="Linea1.ALM.PERF.CPU",
            segment="Linea1",
            area="Linea1",
            tag=tag,
            description="cpu",
            state=SimpleNamespace(serialize=lambda: {"state": "Normal", "process_condition": "Normal", "mnemonic": "CPU", "description": "cpu"}),
        )
        server = SimpleNamespace(
            cvt=SimpleNamespace(get_tag_by_name=lambda name: tag if name == tag.name else None),
            alarm_manager=SimpleNamespace(get_alarm_by_name=lambda name: alarm),
            _namespace_idx=2,
            access=SimpleNamespace(resolve=lambda namespace: 1),
            analog_item_supported=False,
        )
        item = write_item(server, "a", alarm.name, None)
        self.assertEqual(item.data_value.Value.Value, 37.5)
        self.assertIsNotNone(item.refresh)
        self.assertEqual(dict(item.refresh.properties)["state"], "Normal")

    def test_alarm_publishes_state_and_definition(self):
        builder = AddressSpaceBuilder(_Folder(), 2)
        exposer = AlarmExposer(builder, {}, {})
        state = SimpleNamespace(
            serialize=lambda: {
                "state": "Normal",
                "process_condition": "OK",
                "mnemonic": "L",
                "alarm_status": "Not Active",
                "annunciate_status": "Not Annunciated",
                "acknowledge_status": "Acknowledged",
                "description": "d",
            }
        )
        alarm = SimpleNamespace(
            name="alarm.LDS.leak",
            tag=_Tag(),
            state=state,
            description="d",
            display_name="leak",
            alarm_setpoint=SimpleNamespace(serialize=lambda: {"type": "BOOL", "value": True}),
            _on_delay_s=lambda: 5,
            _off_delay_s=lambda: 0,
            on_delay_units="s",
            off_delay_units="s",
            timestamp="",
            ack_timestamp="",
            _condition_met=False,
            _delay_phase=lambda: "",
            last_transition_from="Normal",
            last_transition_to="Normal",
        )
        exposer.upsert(alarm.name, alarm)
        ident = next(iter(exposer._prop_nodes))
        props = exposer._prop_nodes[ident]
        self.assertIn("state", props)
        self.assertIn("acknowledge_status", props)
        self.assertIn("alarm_type", props)
        self.assertIn("trigger_value", props)
        self.assertIn("on_delay", props)
        seen = {}
        for key, prop in props.items():
            prop.set_value = lambda value, key=key: seen.__setitem__(key, value)
        state.serialize = lambda: {
            "state": "Unacknowledged",
            "process_condition": "Abnormal",
            "mnemonic": "UNACK",
            "alarm_status": "Active",
            "annunciate_status": "Annunciated",
            "acknowledge_status": "Not Acknowledged",
            "description": "d",
        }
        alarm._condition_met = True
        exposer.update_value(ident, alarm)
        self.assertEqual(seen["state"], "Unacknowledged")
        self.assertEqual(seen["acknowledge_status"], "Not Acknowledged")
        self.assertIs(seen["condition_met"], True)

    def test_engine_attributes_follow_serialize(self):
        from automation.opcua_server.exposures.published import engine_properties

        engine = SimpleNamespace(
            name="LDS",
            segment="Linea1",
            manufacturer="Supe",
            serialize=lambda: {
                "state": "run",
                "classification": "LDS",
                "fluid": "diesel",
                "description": "Leak Detection System",
                "on_delay": 5,
                "criticity": 1,
                "priority": 2,
                "buffer_size": 40,
                "execution_interval": 1.0,
                "threshold": {"value": 60.0, "unit": "%", "tag": {"name": "LDS.threshold"}, "read_only": False},
                "leak": {"value": 1.0, "unit": "adim", "tag": {"name": "LDS.leak"}, "read_only": False},
                "manufacturer": "Supe",
                "segment": "Linea1",
            },
        )
        props = dict(engine_properties(engine))
        self.assertEqual(props["state"], "run")
        self.assertEqual(props["on_delay"], 5)
        self.assertEqual(props["criticity"], 1)
        self.assertEqual(props["priority"], 2)
        self.assertEqual(props["threshold"], 60.0)
        self.assertNotIn("leak", props)
        self.assertNotIn("manufacturer", props)
        builder = AddressSpaceBuilder(_Folder(), 2)
        exposer = EngineExposer(builder, {}, {})
        exposer.upsert("LDS", engine)
        ident = next(iter(exposer._prop_nodes))
        self.assertIn("threshold", exposer._prop_nodes[ident])
        seen = {}
        for key, prop in exposer._prop_nodes[ident].items():
            prop.set_value = lambda value, key=key: seen.__setitem__(key, value)
        engine.serialize = lambda: {
            "state": "leak",
            "classification": "LDS",
            "fluid": "diesel",
            "description": "Leak Detection System",
            "on_delay": 8,
            "criticity": 5,
            "priority": 2,
            "buffer_size": 40,
            "execution_interval": 1.0,
            "threshold": {"value": 70.0, "unit": "%", "tag": {"name": "LDS.threshold"}, "read_only": False},
        }
        exposer.update_value(ident, engine)
        self.assertEqual(seen["state"], "leak")
        self.assertEqual(seen["on_delay"], 8)
        self.assertEqual(seen["criticity"], 5)
        self.assertEqual(seen["priority"], 2)
        self.assertEqual(seen["threshold"], 70.0)

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
        self.assertEqual(exposer.property_count(ident), 2)
        self.assertNotIn("fluid", exposer._prop_nodes[ident])

    def test_opt_in_attributes_stay_on_the_declaring_engine(self):
        from automation.opcua_server.exposures.published import engine_properties

        payload = {
            "state": "run",
            "classification": "LDS",
            "fluid": "diesel",
            "maneuver": "diesel->Discharge",
            "operation": "Stable",
        }
        generic = SimpleNamespace(name="PPA", serialize=lambda: dict(payload))
        lds = SimpleNamespace(
            name="LDS",
            opcua_attributes=("maneuver", "fluid", "operation"),
            fluid=SimpleNamespace(value="diesel"),
            maneuver=SimpleNamespace(value="diesel->Discharge"),
            operation=SimpleNamespace(value="Stable"),
        )

        def serialize():
            data = dict(payload)
            data["fluid"] = lds.fluid.value
            data["maneuver"] = lds.maneuver.value
            data["operation"] = lds.operation.value
            return data

        lds.serialize = serialize
        self.assertNotIn("fluid", dict(engine_properties(generic)))
        self.assertNotIn("maneuver", dict(engine_properties(generic)))
        published = dict(engine_properties(lds))
        self.assertEqual(published["fluid"], "diesel")
        self.assertEqual(published["maneuver"], "diesel->Discharge")
        self.assertEqual(published["operation"], "Stable")
        lds.operation = SimpleNamespace(value="Shut-In")
        self.assertEqual(dict(engine_properties(lds))["operation"], "Shut-In")

    def test_criticity_and_priority_come_from_the_live_engine(self):
        from automation.opcua_server.exposures.published import engine_properties

        engine = SimpleNamespace(
            name="LDS",
            criticity=SimpleNamespace(value=4),
            priority=SimpleNamespace(value=1),
            serialize=lambda: {"state": "run", "classification": "LDS", "fluid": "diesel"},
        )
        props = dict(engine_properties(engine))
        self.assertEqual(props["criticity"], 4)
        self.assertEqual(props["priority"], 1)


class TestAlarmStatePublish(unittest.TestCase):
    def test_state_entry_marks_the_opc_alarm_even_when_persist_is_deferred(self):
        from unittest.mock import patch

        from automation.utils.decorators import put_alarm_state

        alarm = SimpleNamespace(
            name="alarm.LDS.leak",
            identifier="1",
            state=SimpleNamespace(state="Unacknowledged"),
            sio=None,
            _defer_persist=True,
        )

        @put_alarm_state
        def enter(alarm):
            return "entered"

        with patch("automation.opcua_server.bridge.mark_alarm") as mark:
            self.assertEqual(enter(alarm), "entered")
        mark.assert_called_once_with("alarm.LDS.leak")
