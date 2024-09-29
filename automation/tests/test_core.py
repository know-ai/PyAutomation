import unittest, os
from automation import PyAutomation


class TestCore(unittest.TestCase):

    def setUp(self) -> None:
        file_path = "./test.db"
        if os.path.exists(file_path):
            os.remove(file_path)
        self.app = PyAutomation()
        self.app.run(debug=True, test=True, create_tables=True, alarm_worker=True)
        return super().setUp()

    def tearDown(self) -> None:
        
        return super().tearDown()
    
    def test_tags(self):
        
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
            self.assertDictContainsSubset(tag_in_db.serialize(), tag_in_cvt.serialize())

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

                self.assertDictContainsSubset(tag_in_db, tags_in_cvt[counter])

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

        self.app.delete_tag(id=tag2.id)
        with self.subTest("Test delete tag"):

            self.assertIsNone(self.app.get_tag_by_name(name=tag2.name))

        with self.subTest("Test delete tag from DB"):

            self.assertIsNone(self.app.logger_engine.get_tag_by_name(name=tag2.name))