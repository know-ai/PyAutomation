import unittest

from automation.opcua_server.identity import (
    IdentityCounters,
    conflicting_canonical_name,
    validate_tag_name,
)


class TestReservedPrefixes(unittest.TestCase):
    def test_reserved_prefix_rejected(self):
        before = IdentityCounters.reserved_rejected
        with self.assertRaises(ValueError):
            validate_tag_name("PyAutomationIO.secret")
        with self.assertRaises(ValueError):
            validate_tag_name("alarm.SYS.cpu")
        self.assertGreater(IdentityCounters.reserved_rejected, before)

    def test_ordinary_alarm_name_is_kept(self):
        validate_tag_name("alarm.LDS.leak")

    def test_collision_detected(self):
        before = IdentityCounters.collisions
        conflict = conflicting_canonical_name("FI_01", ["fi_01"])
        self.assertEqual(conflict, "fi_01")
        self.assertIsNone(conflicting_canonical_name("FI_01", ["FI_01"]))
        self.assertGreater(IdentityCounters.collisions, before)

    def test_homoglyph_stays_distinct(self):
        roman = "F\u2160_01"
        ascii_name = "FI_01"
        self.assertIsNone(conflicting_canonical_name(roman, [ascii_name]))

    def test_builder_rejects_reserved_leaf(self):
        from automation.opcua_server.address_space import AddressSpaceBuilder

        builder = AddressSpaceBuilder(None, 2)
        with self.assertRaises(ValueError):
            builder.reject_reserved_leaf("PyAutomationIO.secret")
