import unittest, os
from datetime import datetime
from flask import Flask
from .. import PyAutomation
from ..alarms import Alarm, AlarmState
from ..dbmodels.tags import Segment


class TestCore(unittest.TestCase):

    def setUp(self) -> None:
        file_path = os.path.join(".", "db", "test.db")
        if os.path.exists(file_path):
            os.remove(file_path)
        self.app = PyAutomation()
        self.server = Flask(__name__)
        self.app.run(server=self.server, debug=True, test=True, create_tables=True)
        return super().setUp()

    def tearDown(self) -> None:
        self.app.safe_stop()
        return super().tearDown()
    
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

        # GET TAGS
        _tag2 = {
            "name": "T1",
            "unit": "C",
            "variable": "Temperature"
        }
        tag2, _ = self.app.create_tag(**_tag2)

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
            tag = self.app.logger_engine.get_tag_by_name(name=tag2.name)
            self.assertFalse(tag.active)

        # DELETE TAG BY NAME
        self.app.delete_tag_by_name(name=tag1.name)
        with self.subTest("Test delete tag by name"):

            self.assertIsNone(self.app.get_tag_by_name(name=tag1.name))

        with self.subTest("Test delete tag by name from DB"):
            tag = self.app.logger_engine.get_tag_by_name(name=tag1.name)
            self.assertFalse(tag.active)

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

        # UPDATE ALARM DEFINITION
        self.app.update_alarm(id=alarm_HH.identifier, trigger_value=50)
        with self.subTest("Test update alarm in Alarm Manager"):
            
            self.assertEqual(alarm_HH.alarm_setpoint.value, 50)

        with self.subTest("Test update alarm in DB"):
            alarm = self.app.alarms_engine.get_alarm_by_name(name=alarm_HH.name)
            self.assertEqual(alarm.trigger_value, 50)

        # TRIGGER ALARMS
        timestamp = datetime.now()
        self.app.cvt.set_value(id=tag.id, value=35, timestamp=timestamp)
        with self.subTest("Test Trigger HIGH Alarm"):
            
            self.assertEqual(alarm_H.state.alarm_status, "Active")

        with self.subTest("Test check UNACK alarm state"):
            
            self.assertEqual(alarm_H.state, AlarmState.UNACK)

        with self.subTest("Test aknowledge alarm"):
            alarm_H.acknowledge()
            self.assertEqual(alarm_H.state, AlarmState.ACKED)

        with self.subTest("Test not Trigger HIGH-HIGH Alarm"):

            self.assertEqual(alarm_HH.state.alarm_status, "Not Active")

        self.app.cvt.set_value(id=tag.id, value=0, timestamp=timestamp)
        with self.subTest("Test Trigger LOW Alarm"):
            
            self.assertEqual(alarm_L.state.alarm_status, "Active")

        with self.subTest("Test Trigger LOW-LOW Alarm"):
            
            self.assertEqual(alarm_LL.state.alarm_status, "Active")

        with self.subTest("Test check UNACK alarm LL state"):
            
            self.assertEqual(alarm_LL.state, AlarmState.UNACK)

        with self.subTest("Test check UNACK alarm L state"):
            
            self.assertEqual(alarm_L.state, AlarmState.UNACK)

        self.app.cvt.set_value(id=tag.id, value=15, timestamp=timestamp)
        with self.subTest("Test check UNACK alarm LL state"):
            
            self.assertEqual(alarm_LL.state, AlarmState.RTNUN)

        with self.subTest("Test aknowledge LL alarm"):
            alarm_LL.acknowledge()
            self.assertEqual(alarm_LL.state, AlarmState.NORM)

        with self.subTest("Test aknowledge L alarm"):
            alarm_L.acknowledge()
            self.assertEqual(alarm_L.state, AlarmState.ACKED)


        # Boolean Alarm
        tag_payload = {
            "name": "Bool1",
            "unit": "adim",
            "variable": "Adimentional"
        }
        tag, _ = self.app.create_tag(**tag_payload)
        alarm_B_payload = {
            "name": "alarm_B",
            "tag": tag.name,
            "alarm_type": "BOOL",
            "trigger_value": True,
        }
        alarm_B, _ = self.app.create_alarm(**alarm_B_payload)

        with self.subTest("Test Not Trigger BOOL Alarm"):
            
            self.assertEqual(alarm_B.state.alarm_status, "Not Active")

        self.app.cvt.set_value(id=tag.id, value=True, timestamp=timestamp)
        with self.subTest("Test Trigger BOOL Alarm"):
            
            self.assertEqual(alarm_B.state.alarm_status, "Active")

        # DELETE TAG
        self.app.delete_alarm(id=alarm_LL.identifier)
        self.app.delete_alarm(id=alarm_L.identifier)
        self.app.delete_alarm(id=alarm_H.identifier)
        self.app.delete_alarm(id=alarm_HH.identifier)
        self.app.delete_tag(id=tag.id)

    def test_linear_referencing_geospatial(self):
        # Precondition: segment must exist in DB
        segment = Segment.create(name="SEG-A", manufacturer="MANU-A")
        self.assertIsNotNone(segment)

        # CREATE point
        point, message = self.app.create_linear_referencing_geospatial(
            segment_name="SEG-A",
            kp=0.0,
            latitude=10.0,
            longitude=-72.0,
            elevation=100.0
        )
        with self.subTest("Create geospatial point"):
            self.assertIsNotNone(point)
            self.assertEqual(point["segment_name"], "SEG-A")
            self.assertEqual(point["kp"], 0.0)

        # CREATE second point for interpolation
        point2, _ = self.app.create_linear_referencing_geospatial(
            segment_name="SEG-A",
            kp=10.0,
            latitude=20.0,
            longitude=-62.0,
            elevation=200.0
        )
        self.assertIsNotNone(point2)

        # READ all/by-segment/by-id
        all_points = self.app.get_linear_referencing_geospatial_points()
        with self.subTest("Read all points"):
            self.assertGreaterEqual(len(all_points), 2)

        segment_points = self.app.get_linear_referencing_geospatial_points_by_segment(segment_name="SEG-A")
        with self.subTest("Read points by segment"):
            self.assertEqual(len(segment_points), 2)
            self.assertLessEqual(segment_points[0]["kp"], segment_points[1]["kp"])

        point_by_id = self.app.get_linear_referencing_geospatial_point(id=point["id"])
        with self.subTest("Read point by id"):
            self.assertIsNotNone(point_by_id)
            self.assertEqual(point_by_id["kp"], 0.0)

        # UPDATE
        updated, _ = self.app.update_linear_referencing_geospatial_point(
            id=point["id"],
            latitude=11.0,
            longitude=-71.0
        )
        with self.subTest("Update point"):
            self.assertEqual(updated["latitude"], 11.0)
            self.assertEqual(updated["longitude"], -71.0)

        # INTERPOLATION (midpoint between KP 0 and 10)
        interpolated, _ = self.app.get_geospatial_by_segment_and_kp(segment_name="SEG-A", kp=5.0)
        with self.subTest("Interpolate by segment and KP"):
            self.assertIsNotNone(interpolated)
            self.assertTrue(interpolated["interpolated"])
            self.assertAlmostEqual(interpolated["latitude"], 15.5, places=6)
            self.assertAlmostEqual(interpolated["longitude"], -66.5, places=6)
            self.assertAlmostEqual(interpolated["elevation"], 150.0, places=6)

        # BULK IMPORT from normalized rows (create/update/skip)
        import_result = self.app.import_linear_referencing_profile(
            rows=[
                {"segment_name": "SEG-A", "kp": 20.0, "latitude": 30.0, "longitude": -52.0, "elevation": 300.0},
                {"segment_name": "SEG-A", "kp": 10.0, "latitude": 21.0, "longitude": -61.0, "elevation": 201.0},
            ],
            update_existing=True
        )
        with self.subTest("Bulk import with update_existing=True"):
            self.assertEqual(import_result["created"], 1)
            self.assertEqual(import_result["updated"], 1)
            self.assertTrue(import_result["success"])

        import_result_skip = self.app.import_linear_referencing_profile(
            rows=[
                {"segment_name": "SEG-A", "kp": 20.0, "latitude": 99.0, "longitude": -99.0}
            ],
            update_existing=False
        )
        with self.subTest("Bulk import with update_existing=False"):
            self.assertEqual(import_result_skip["skipped"], 1)
            self.assertTrue(import_result_skip["success"])

        # DELETE
        success, _ = self.app.delete_linear_referencing_geospatial_point(id=point2["id"])
        with self.subTest("Delete point by id"):
            self.assertTrue(success)
            deleted = self.app.get_linear_referencing_geospatial_point(id=point2["id"])
            self.assertIsNone(deleted)