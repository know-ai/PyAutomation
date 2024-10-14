import unittest
from automation.alarms import Alarm
from automation.tags.tag import Tag
from automation.tags.cvt import CVTEngine
from automation.models import StringType, FloatType

cvt = CVTEngine()

class TestAlarms(unittest.TestCase):

    def setUp(self) -> None:
        
        return super().setUp()

    def tearDown(self) -> None:
        
        return super().tearDown()
    
    def test_create_alarm(self):
        r"""
        Documentation here
        """
        name = "alarm1"
        cvt.set_tag(
            name="tag1",
            variable="Temperature",
            unit="C",
            data_type="FLOAT",
            description="tag1"
        )
        tag = cvt.get_tag_by_name(name="tag1")
        alarm = Alarm(
            name=name,
            tag=tag,
            alarm_type=StringType("HIGH"),
            alarm_setpoint=FloatType(50.0)
        )

        self.assertEqual(alarm.state.state.lower(), "normal")

    def test_alarm_state_attribute(self):
        r"""
        Documentation here
        """
        name = "alarm1"
        cvt.set_tag(
            name="tag2",
            variable="Temperature",
            unit="C",
            data_type="FLOAT",
            description="tag2"
        )
        tag = cvt.get_tag_by_name(name="tag2")
        alarm = Alarm(
            name=name,
            tag=tag,
            alarm_type=StringType("HIGH"),
            alarm_setpoint=FloatType(50.0)
        )

        with self.subTest("Test alarm Unack status"):
            tag.set_value(value=55)
            self.assertEqual(alarm.state.state.lower(), "unacknowledged")

        with self.subTest("Test alarm Ack status"):
            alarm.acknowledge()
            self.assertEqual(alarm.state.state.lower(), "acknowledged")

        with self.subTest("Test alarm Normal status"):
            tag.set_value(value=45)
            self.assertEqual(alarm.state.state.lower(), "normal")
        
    def test_alarm_state_machine(self):
        r"""
        Documentation here
        """
        name = "alarm1"
        cvt.set_tag(
            name="tag3",
            variable="Temperature",
            unit="C",
            data_type="FLOAT",
            description="tag3"
        )
        tag = cvt.get_tag_by_name(name="tag3")
        alarm = Alarm(
            name=name,
            tag=tag,
            alarm_type=StringType("HIGH"),
            alarm_setpoint=FloatType(50.0)
        )

        tag.set_value(value=55)
        with self.subTest("Test alarm Unack status"):
            self.assertEqual(alarm.current_state.value.lower(), "unack_alarm")

        with self.subTest("Test alarm Ack status"):
            alarm.acknowledge()
            self.assertEqual(alarm.current_state.value.lower(), "ack_alarm")

        with self.subTest("Test alarm Normal status"):
            tag.set_value(value=45)
            self.assertEqual(alarm.current_state.value.lower(), "normal")

    


    

    