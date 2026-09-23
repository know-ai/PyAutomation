"""AST lint for the field-client asyncua migration. AP-1 through AP-9."""

from __future__ import annotations

import ast
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CLIENT_ROOT = ROOT / "opcua"
MANAGER = ROOT / "managers" / "opcua_client.py"
SERVER_ROOT = ROOT / "opcua_server"
PACKAGE = ROOT / "opcua" / "asyncua_client"


def _py_files(folder: Path):
    return [path for path in folder.rglob("*.py") if path.is_file()]


class TestClientAsyncuaLint(unittest.TestCase):
    def test_no_legacy_opcua_import(self):
        offenders = []
        for path in _py_files(CLIENT_ROOT) + [MANAGER]:
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    names = [alias.name.split(".")[0] for alias in node.names]
                elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                    names = [node.module.split(".")[0]]
                else:
                    continue
                if "opcua" in names:
                    offenders.append(str(path))
        self.assertEqual(offenders, [])

    def test_no_private_socket_api(self):
        blob = "\n".join(path.read_text(encoding="utf-8") for path in _py_files(CLIENT_ROOT))
        blob += "\n" + MANAGER.read_text(encoding="utf-8")
        self.assertNotIn("_uasocket", blob)
        self.assertNotIn("uaclient._connection", blob)
        self.assertNotIn("._uasocket", blob)

    def test_daq_does_not_call_read_values(self):
        blob = "\n".join(path.read_text(encoding="utf-8") for path in _py_files(CLIENT_ROOT))
        self.assertNotIn("read_values", blob)

    def test_handler_does_not_write_cvt(self):
        source = (PACKAGE / "handlers.py").read_text(encoding="utf-8")
        self.assertNotIn("set_value_fast", source)
        self.assertNotIn("cvt.set_value", source)

    def test_queues_declare_maxsize(self):
        for name in ("command_queue.py", "result_queue.py"):
            source = (PACKAGE / name).read_text(encoding="utf-8")
            self.assertIn("maxsize", source)
            self.assertIn("10_000", source)

    def test_client_loop_is_not_the_server_loop(self):
        client = (PACKAGE / "runner.py").read_text(encoding="utf-8")
        self.assertIn("opcua-asyncua-client", client)
        for path in _py_files(SERVER_ROOT):
            text = path.read_text(encoding="utf-8")
            self.assertNotIn("asyncua_client", text)

    def test_sync_adapter_and_loop_stay_small(self):
        adapter = len((PACKAGE / "sync_adapter.py").read_text(encoding="utf-8").splitlines())
        loop = sum(len((PACKAGE / name).read_text(encoding="utf-8").splitlines()) for name in (
            "runner.py",
            "command_queue.py",
            "result_queue.py",
            "commands.py",
            "handlers.py",
        ))
        self.assertLessEqual(adapter, 300)
        self.assertLessEqual(loop, 700)
