import unittest
from types import SimpleNamespace
from unittest.mock import patch

from automation.opcua_server.grouping import engine_folder_name, engine_groups_for_tag


class ProcessType:
    def __init__(self, tag_name):
        self.tag = SimpleNamespace(name=tag_name)
        self.read_only = True


class TestEngineGrouping(unittest.TestCase):
    def test_folder_name_is_the_engine_segment(self):
        machine = SimpleNamespace(name=SimpleNamespace(value="Supe.Linea1.LDS"))
        self.assertEqual(engine_folder_name(machine), "LDS")

    def test_tag_is_listed_under_every_engine_that_binds_it(self):
        shared = "Supe.Linea1.FI_02"
        lds = SimpleNamespace(name="Supe.Linea1.LDS", inlet=ProcessType(shared))
        ppa = SimpleNamespace(name="Supe.Linea1.PPA", inlet=ProcessType(shared))
        server = SimpleNamespace(name="OPCUAServer", inlet=ProcessType(shared))
        app = SimpleNamespace(get_machines=lambda: [(lds, 0, ""), (ppa, 0, ""), (server, 0, "")])
        with patch("automation.PyAutomation", return_value=app):
            self.assertEqual(engine_groups_for_tag(shared), ("LDS", "PPA"))

    def test_alarm_tree_name_keeps_the_engine(self):
        from types import SimpleNamespace

        from automation.opcua_server.exposures.common import alarm_browse_name, leaf_name

        self.assertEqual(alarm_browse_name("supe.linea1.ppa.leak"), "ppa.leak")
        self.assertEqual(alarm_browse_name("supe.linea1.npw.leak"), "npw.leak")
        alarm = SimpleNamespace(name="Supe.Linea1.PPA.leak", display_name="leak")
        self.assertEqual(leaf_name(alarm, "a"), "PPA.leak")
        tag = SimpleNamespace(name="Supe.Linea1.FI_02", display_name="FI_02")
        self.assertEqual(leaf_name(tag, "t"), "FI_02")
        app = SimpleNamespace(get_machines=lambda: [])
        with patch("automation.PyAutomation", return_value=app):
            self.assertEqual(engine_groups_for_tag("Linea1.SYS.PERF.CPU"), ())
