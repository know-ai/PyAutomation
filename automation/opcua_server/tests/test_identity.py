import os
import unittest
from unittest.mock import patch

from automation.opcua_server.identity import (
    canonicalize_name,
    canonical_area,
    make_node_id,
    property_node_id,
)


class TestIdentity(unittest.TestCase):
    def setUp(self):
        canonicalize_name.cache_clear()
        canonical_area.cache_clear()

    def test_casefold_equal(self):
        self.assertEqual(
            canonicalize_name("Supe.Linea1.FI_01"),
            canonicalize_name("SUPE.LINEA1.FI_01"),
        )

    def test_whitespace_collapses_to_dots(self):
        self.assertEqual(canonicalize_name(" a  b "), "a.b")

    def test_empty(self):
        self.assertEqual(canonicalize_name(""), "_")

    def test_reserved_chars(self):
        self.assertEqual(canonicalize_name("a;b,c"), "a_b_c")

    def test_nfc_casefold(self):
        self.assertEqual(canonicalize_name("Línea1"), "línea1")

    def test_type_prefix_is_not_in_the_identifier(self):
        self.assertEqual(make_node_id("t", "Linea1", "X.Y"), "x.y")
        self.assertEqual(make_node_id("a", "Linea1", "X.Y"), "x.y")
        self.assertEqual(make_node_id("e", "Linea1", "X.Y"), "x.y")

    def test_area_is_not_part_of_the_identifier(self):
        self.assertEqual(make_node_id("t", None, "X"), "x")
        with patch.dict(os.environ, {"AUTOMATION_MANUFACTURER": "Supe", "AUTOMATION_SEGMENT": "Linea1"}):
            self.assertEqual(make_node_id("t", "Linea1", "Supe.Linea1.FI_02"), "fi_02")
            self.assertEqual(make_node_id("t", None, "Linea1.SYS.PERF.SAF_QUEUE"), "sys.perf.saf_queue")
            self.assertEqual(make_node_id("t", None, "Supe.Linea1.LDS.leak_flow"), "lds.leak_flow")
            self.assertEqual(make_node_id("a", None, "Supe.Linea1.PPA.leak"), "ppa.leak")
            self.assertEqual(make_node_id("e", None, "Supe.Linea1.LDS"), "lds")

    def test_engine_property_does_not_reuse_the_tag_id(self):
        with patch.dict(os.environ, {"AUTOMATION_MANUFACTURER": "Supe", "AUTOMATION_SEGMENT": "Linea1"}):
            tag_id = make_node_id("t", None, "Supe.Linea1.LDS.threshold")
            engine_id = make_node_id("e", None, "Supe.Linea1.LDS")
        self.assertEqual(tag_id, "lds.threshold")
        self.assertEqual(property_node_id(engine_id, "threshold"), "lds#threshold")
        self.assertNotEqual(property_node_id(engine_id, "threshold"), tag_id)

    def test_bad_entity(self):
        with self.assertRaises(ValueError):
            make_node_id("bad", "a", "b")

    def test_cache_hits(self):
        canonicalize_name.cache_clear()
        canonicalize_name("Supe.Linea1.FI_01")
        before = canonicalize_name.cache_info().misses
        for _ in range(1000):
            canonicalize_name("Supe.Linea1.FI_01")
        after = canonicalize_name.cache_info().misses
        self.assertEqual(after, before)

    def test_cache_growth_bound(self):
        import time

        canonicalize_name.cache_clear()
        names = [f"tag.{i}" for i in range(100)]
        started = time.perf_counter()
        for _ in range(10):
            for name in names:
                canonicalize_name(name)
        first = time.perf_counter() - started
        started = time.perf_counter()
        for _ in range(100):
            for name in names:
                canonicalize_name(name)
        second = time.perf_counter() - started
        self.assertLessEqual(second, max(first * 20, 0.05))
        self.assertLessEqual(canonicalize_name.cache_info().currsize, 10_000)
