import unittest

from automation.opcua_server.flags import namespace_uri
from automation.opcua_server.identity import canonicalize_name, make_node_id


class TestRegressionGolden(unittest.TestCase):
    def test_node_id_stable_under_case_change(self):
        self.assertEqual(
            make_node_id("t", "Linea1", "Supe.Linea1.FI_01"),
            make_node_id("t", "LINEA1", "supe.linea1.fi_01"),
        )

    def test_namespace_uri_uses_package_minor(self):
        self.assertTrue(namespace_uri().startswith("urn:pyautomationio:opcua:"))
        self.assertNotIn("freeopcua", namespace_uri())

    def test_whitespace_does_not_change_identity(self):
        self.assertEqual(canonicalize_name("FI 01"), canonicalize_name("FI  01"))
