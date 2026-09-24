import unittest

from automation.opcua_server.identity import (
    IdentityCounters,
    canonical_area,
    canonicalize_name,
    folder_token,
    make_node_id,
    normalize_tag_name,
)


class TestIdentityContract(unittest.TestCase):
    def setUp(self):
        canonicalize_name.cache_clear()
        canonical_area.cache_clear()

    def test_case_insensitive(self):
        self.assertEqual(canonicalize_name("SUPE.LINEA1.FI_01"), "supe.linea1.fi_01")

    def test_whitespace_collapse(self):
        self.assertEqual(canonicalize_name(" a   b "), "a.b")

    def test_nfc_normalization(self):
        self.assertEqual(canonicalize_name("Línea1"), "línea1")

    def test_reserved_chars_escaped(self):
        self.assertEqual(canonicalize_name("a;b,c"), "a_b_c")

    def test_control_chars_stripped(self):
        self.assertEqual(canonicalize_name("a\x00b"), "ab")

    def test_length_truncated(self):
        before = IdentityCounters.length_truncated
        text = canonicalize_name("a" * 1000)
        self.assertEqual(len(text), 256)
        self.assertGreater(IdentityCounters.length_truncated, before)

    def test_empty_returns_underscore(self):
        self.assertEqual(canonicalize_name(""), "_")
        self.assertEqual(canonical_area(None), "_")
        self.assertEqual(canonical_area("  "), "_")

    def test_idempotent(self):
        samples = ["Supe.Linea1.FI_01", " a  b ", "a;b", ".FI_01", "FI..01", "a" * 300]
        for sample in samples:
            once = canonicalize_name(sample)
            self.assertEqual(canonicalize_name(once), once)

    def test_end_dots_drop_and_inner_dots_stay(self):
        self.assertEqual(canonicalize_name(".FI_01"), "fi_01")
        self.assertEqual(canonicalize_name("FI_01."), "fi_01")
        self.assertEqual(canonicalize_name("FI..01"), "fi..01")

    def test_type_prefix(self):
        self.assertNotEqual(
            make_node_id("t", "Linea1", "FI_01"),
            make_node_id("a", "Linea1", "FI_01"),
        )
        self.assertNotEqual(
            make_node_id("a", "Linea1", "FI_01"),
            make_node_id("e", "Linea1", "FI_01"),
        )

    def test_area_argument_does_not_change_the_identifier(self):
        self.assertEqual(
            make_node_id("t", "Linea1", "Supe.Linea1.FI_01"),
            make_node_id("t", "Linea2", "Supe.Linea1.FI_01"),
        )
        self.assertEqual(make_node_id("t", "Linea1", "Supe.Linea1.FI_01"), "t:supe.linea1.fi_01")

    def test_no_manufacturer_field(self):
        same = make_node_id("t", "Linea1", "Supe.Linea1.FI_01")
        self.assertEqual(same, make_node_id("t", "Linea1", "Supe.Linea1.FI_01"))
        self.assertNotIn("manufacturer", same)

    def test_invalid_entity_type(self):
        with self.assertRaises(ValueError):
            make_node_id("x", "Linea1", "FI_01")

    def test_deterministic(self):
        first = make_node_id("t", "Linea1", "Supe.Linea1.FI_01")
        for _ in range(100):
            self.assertEqual(first, make_node_id("t", "Linea1", "Supe.Linea1.FI_01"))

    def test_empty_folders(self):
        self.assertEqual(folder_token("", "Default"), "Default")
        self.assertEqual(folder_token("", "Global"), "Global")

    def test_tag_name_without_manufacturer_prefix(self):
        self.assertEqual(normalize_tag_name("FI_01", "Supe", "Linea1"), "Supe.Linea1.FI_01")
        self.assertEqual(normalize_tag_name("Supe.Linea1.FI_01", "Supe", "Linea1"), "Supe.Linea1.FI_01")
        self.assertEqual(normalize_tag_name("FI_01", "", ""), "Default.Global.FI_01")
