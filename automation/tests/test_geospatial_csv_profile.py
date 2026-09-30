import unittest

from automation.modules.linear_referencing.csv_profile import (
    GeospatialCsvError,
    GeospatialCsvProfile,
)


SAMPLE = (
    "segment_name,kp,latitude,longitude\n"
    "Linea1,1378,-10.80048,-77.74544\n"
    "Linea1,1328,-10.8001,-77.74591\n"
)


class TestGeospatialCsvProfile(unittest.TestCase):
    def setUp(self):
        self.parser = GeospatialCsvProfile()

    def test_reference_header_and_rows(self):
        rows = self.parser.parse(SAMPLE.encode("utf-8"))
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["segment_name"], "Linea1")
        self.assertEqual(rows[0]["kp"], 1378.0)
        self.assertAlmostEqual(rows[0]["latitude"], -10.80048)
        self.assertAlmostEqual(rows[0]["longitude"], -77.74544)
        self.assertIsNone(rows[0]["elevation"])

    def test_utf8_bom_is_accepted(self):
        rows = self.parser.parse(SAMPLE.encode("utf-8-sig"))
        self.assertEqual(rows[0]["segment_name"], "Linea1")

    def test_wrong_header_rejects_the_file(self):
        raw = "segment,kp,lat,lon\nLinea1,1,0,0\n"
        with self.assertRaises(GeospatialCsvError) as caught:
            self.parser.parse(raw.encode("utf-8"))
        self.assertIn("Header must be exactly", str(caught.exception))

    def test_alias_columns_are_rejected(self):
        raw = "segment_name,kp,lat,lon\nLinea1,1,0,0\n"
        with self.assertRaises(GeospatialCsvError):
            self.parser.parse(raw.encode("utf-8"))

    def test_extra_column_rejects_the_row(self):
        raw = (
            "segment_name,kp,latitude,longitude\n"
            "Linea1,1,-10.1,-77.1,12\n"
        )
        with self.assertRaises(GeospatialCsvError) as caught:
            self.parser.parse(raw.encode("utf-8"))
        self.assertIn("Row 2", str(caught.exception))

    def test_latitude_out_of_range(self):
        raw = "segment_name,kp,latitude,longitude\nLinea1,1,91,0\n"
        with self.assertRaises(GeospatialCsvError) as caught:
            self.parser.parse(raw.encode("utf-8"))
        self.assertIn("latitude", str(caught.exception))

    def test_duplicate_kp_rejects_the_file(self):
        raw = (
            "segment_name,kp,latitude,longitude\n"
            "Linea1,10,-10.1,-77.1\n"
            "Linea1,10,-10.2,-77.2\n"
        )
        with self.assertRaises(GeospatialCsvError) as caught:
            self.parser.parse(raw.encode("utf-8"))
        self.assertIn("duplicated kp", str(caught.exception))

    def test_header_only_is_rejected(self):
        raw = "segment_name,kp,latitude,longitude\n"
        with self.assertRaises(GeospatialCsvError) as caught:
            self.parser.parse(raw.encode("utf-8"))
        self.assertIn("no data rows", str(caught.exception))

    def test_file_over_one_megabyte_is_rejected(self):
        raw = b"x" * (1_048_576 + 1)
        with self.assertRaises(GeospatialCsvError) as caught:
            self.parser.parse(raw)
        self.assertIn("1 MB", str(caught.exception))
