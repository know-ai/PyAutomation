import unittest
from unittest.mock import MagicMock

from ..utils.tag_audit import describe_tag_update


class TestDescribeTagUpdate(unittest.TestCase):
    def test_includes_field_old_and_new_values(self):
        tag = MagicMock()
        tag.name = "FI_01"
        tag.get_scan_time.return_value = 1000
        tag.get_dead_band.return_value = 0.1
        description = describe_tag_update(
            tag,
            {"scan_time": 500, "dead_band": 0.5},
        )
        self.assertIn("Tag: FI_01", description)
        self.assertIn("scan_time: 1000 → 500", description)
        self.assertIn("dead_band: 0.1 → 0.5", description)

    def test_skips_unchanged_fields(self):
        tag = MagicMock()
        tag.name = "PI_01"
        tag.get_scan_time.return_value = 1000
        description = describe_tag_update(tag, {"scan_time": 1000, "name": "PI_01"})
        self.assertEqual(description, "Tag: PI_01")
