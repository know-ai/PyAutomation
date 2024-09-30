import unittest, os
from datetime import datetime
from automation import PyAutomation
from automation.alarms.alarms import Alarm, AlarmState
from time import sleep


class TestCore(unittest.TestCase):

    def setUp(self) -> None:
        file_path = "./test.db"
        if os.path.exists(file_path):
            os.remove(file_path)
        self.app = PyAutomation()
        self.app.run(debug=True, test=True, create_tables=True, alarm_worker=True)
        return super().setUp()

    def tearDown(self) -> None:
        self.app.safe_stop()
        return super().tearDown()
    
    @staticmethod
    def assert_dict_contains_subset(subset, superset, msg=None):
        """
        Custom assertion to check if `subset` is a subset of `superset`.
        """
        missing_keys = {key for key in subset if key not in superset}
        assert not missing_keys, f"{msg or 'Dictionary subset check failed'}: Missing keys {missing_keys}"

        for key, value in subset.items():
            assert superset[key] == value, f"{msg or 'Dictionary subset check failed'}: Value mismatch for key '{key}'"
    
    def test_tags(self):
        
        # CREATE TAGS
        _tag1 = {
            "name": "P1",
            "unit": "Pa",
            "variable": "Pressure"
        }
        tag1, _ = self.app.create_tag(**_tag1)
        with self.subTest("Test tag in cvt"):
            
            tag_in_cvt = self.app.cvt.get_tag_by_name(name=_tag1['name'])
            self.assertEqual(tag1, tag_in_cvt)

        with self.subTest("Test tag in DB"):

            tag_in_db = self.app.logger_engine.get_tag_by_name(name=_tag1['name'])
            self.assert_dict_contains_subset(tag_in_db.serialize(), tag_in_cvt.serialize())

        # GET TAGS
        _tag2 = {
            "name": "T1",
            "unit": "C",
            "variable": "Temperature"
        }
        tag2, _ = self.app.create_tag(**_tag2)
        tags_in_cvt = self.app.get_tags()
        tags_in_db = self.app.logger_engine.get_tags()

        with self.subTest("Test get tags CVT - DB"):

            for counter, tag_in_db in enumerate(tags_in_db):
                
                self.assert_dict_contains_subset(tag_in_db, tags_in_cvt[counter])

        # SET TAG VALUES
        timestamp = datetime.now()
        value = 35
        self.app.cvt.set_value(id=tag2.id, value=value, timestamp=timestamp)
        with self.subTest("Test Value in CVT"):
            
            self.assertEqual(self.app.cvt.get_value(id=tag2.id), value)

        # UPDATE TAGS
        name = "TT"
        updated_tag, _ = self.app.update_tag(id=tag2.id, name=name)
        with self.subTest("Test update tag name"):

            self.assertEqual(name, updated_tag.name)

        with self.subTest("Test update tag name from DB"):

            updated_tag = self.app.logger_engine.get_tag_by_name(name=name)
            self.assertEqual(name, updated_tag.name)

        unit = "K"
        updated_tag, _ = self.app.update_tag(id=tag2.id, unit=unit)
        with self.subTest("Test update tag unit"):

            self.assertEqual(unit, updated_tag.unit)

        with self.subTest("Test update tag unit from DB"):

            updated_tag = self.app.logger_engine.get_tag_by_name(name=tag2.name)
            self.assertEqual(unit, updated_tag.unit.unit)

        # DELETE TAG
        self.app.delete_tag(id=tag2.id)
        with self.subTest("Test delete tag"):

            self.assertIsNone(self.app.get_tag_by_name(name=tag2.name))

        with self.subTest("Test delete tag from DB"):

            self.assertIsNone(self.app.logger_engine.get_tag_by_name(name=tag2.name))

        # DELETE TAG BY NAME
        self.app.delete_tag_by_name(name=tag1.name)
        with self.subTest("Test delete tag by name"):

            self.assertIsNone(self.app.get_tag_by_name(name=tag1.name))

        with self.subTest("Test delete tag by name from DB"):

            self.assertIsNone(self.app.logger_engine.get_tag_by_name(name=tag1.name))

    def test_alarms(self):
        r"""
        Documentation here
        """

        tag_payload = {
            "name": "T2",
            "unit": "C",
            "variable": "Temperature"
        }
        tag, _ = self.app.create_tag(**tag_payload)

        alarm_LL_payload = {
            "name": "alarm_LL",
            "tag": tag.name,
            "alarm_type": "LOW-LOW",
            "trigger_value": 10.0,
        }

        # CREATE ALARM
        alarm_LL, _ = self.app.create_alarm(**alarm_LL_payload)
        with self.subTest("Test create alarm instance"):

            self.assertIsInstance(alarm_LL, Alarm)

        with self.subTest("Test create alarm in alarm manager"):

            self.assertEqual(alarm_LL, self.app.alarm_manager.get_alarm_by_name(name=alarm_LL.name))

        with self.subTest("Test create alarm in DB"):
            alarm = self.app.alarms_engine.get_alarm_by_name(name=alarm_LL.name)
            self.assert_dict_contains_subset(alarm.serialize(), alarm_LL.serialize())

        alarm_L_payload = {
            "name": "alarm_L",
            "tag": tag.name,
            "alarm_type": "LOW",
            "trigger_value": 20.0,
        }
        alarm_L, _ = self.app.create_alarm(**alarm_L_payload)
        with self.subTest("Test create alarm instance"):

            self.assertIsInstance(alarm_L, Alarm)
        
        with self.subTest("Test create alarm in alarm manager"):

            self.assertEqual(alarm_L, self.app.alarm_manager.get_alarm_by_name(name=alarm_L.name))

        with self.subTest("Test create alarm in DB"):
            alarm = self.app.alarms_engine.get_alarm_by_name(name=alarm_L.name)
            self.assert_dict_contains_subset(alarm.serialize(), alarm_L.serialize())

        alarm_H_payload = {
            "name": "alarm_H",
            "tag": tag.name,
            "alarm_type": "HIGH",
            "trigger_value": 30.0,
        }
        alarm_H, _ = self.app.create_alarm(**alarm_H_payload)
        with self.subTest("Test create alarm instance"):

            self.assertIsInstance(alarm_H, Alarm)

        with self.subTest("Test create alarm in alarm manager"):

            self.assertEqual(alarm_H, self.app.alarm_manager.get_alarm_by_name(name=alarm_H.name))

        with self.subTest("Test create alarm in DB"):
            alarm = self.app.alarms_engine.get_alarm_by_name(name=alarm_H.name)
            self.assert_dict_contains_subset(alarm.serialize(), alarm_H.serialize())

        alarm_HH_payload = {
            "name": "alarm_HH",
            "tag": tag.name,
            "alarm_type": "HIGH-HIGH",
            "trigger_value": 40.0,
        }
        alarm_HH, _ = self.app.create_alarm(**alarm_HH_payload)
        with self.subTest("Test create alarm instance"):

            self.assertIsInstance(alarm_HH, Alarm)

        with self.subTest("Test create alarm in alarm manager"):

            self.assertEqual(alarm_HH, self.app.alarm_manager.get_alarm_by_name(name=alarm_HH.name))

        with self.subTest("Test create alarm in DB"):
            alarm = self.app.alarms_engine.get_alarm_by_name(name=alarm_HH.name)
            self.assert_dict_contains_subset(alarm.serialize(), alarm_HH.serialize())

        # UPDATE ALARM DEFINITION
        self.app.update_alarm(id=alarm_HH.identifier, trigger_value=50)
        with self.subTest("Test update alarm in Alarm Manager"):
            
            self.assertEqual(alarm_HH._trigger.value, 50)

        with self.subTest("Test update alarm in DB"):
            alarm = self.app.alarms_engine.get_alarm_by_name(name=alarm_HH.name)
            self.assertEqual(alarm.trigger_value, 50)

        # TRIGGER ALARMS
        timestamp = datetime.now()
        self.app.cvt.set_value(id=tag.id, value=35, timestamp=timestamp)
        # This step is important, you must way from worker make its job
        sleep(1)
        with self.subTest("Test Trigger HIGH Alarm"):
            
            self.assertTrue(alarm_H.state.is_triggered)

        with self.subTest("Test check UNACK alarm state"):
            
            self.assertEqual(alarm_H.state, AlarmState.UNACK)

        with self.subTest("Test aknowledge alarm"):
            alarm_H.acknowledge()
            self.assertEqual(alarm_H.state, AlarmState.ACKED)

        with self.subTest("Test  not Trigger HIGH-HIGH Alarm"):

            self.assertFalse(alarm_HH.state.is_triggered)

        self.app.cvt.set_value(id=tag.id, value=0, timestamp=timestamp)
        sleep(1)
        with self.subTest("Test Trigger LOW Alarm"):
            
            self.assertTrue(alarm_L.state.is_triggered)

        with self.subTest("Test Trigger LOW-LOW Alarm"):
            
            self.assertTrue(alarm_LL.state.is_triggered)

        with self.subTest("Test check UNACK alarm LL state"):
            
            self.assertEqual(alarm_LL.state, AlarmState.UNACK)

        with self.subTest("Test check UNACK alarm L state"):
            
            self.assertEqual(alarm_L.state, AlarmState.UNACK)

        self.app.cvt.set_value(id=tag.id, value=15, timestamp=timestamp)
        sleep(1)
        with self.subTest("Test check UNACK alarm LL state"):
            
            self.assertEqual(alarm_LL.state, AlarmState.RTNUN)

        with self.subTest("Test aknowledge LL alarm"):
            alarm_LL.acknowledge()
            self.assertEqual(alarm_LL.state, AlarmState.NORM)

        with self.subTest("Test aknowledge L alarm"):
            alarm_L.acknowledge()
            self.assertEqual(alarm_L.state, AlarmState.ACKED)

        # DELETE TAG
        self.app.delete_alarm(id=alarm_LL.identifier)
        self.app.delete_alarm(id=alarm_L.identifier)
        self.app.delete_alarm(id=alarm_H.identifier)
        self.app.delete_alarm(id=alarm_HH.identifier)
        self.app.delete_tag(id=tag.id)