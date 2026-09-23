"""Real asyncua client browse, read and write. Skipped unless OPCUA_E2E=1."""

import os
import socket
import unittest

from asyncua import ua
from asyncua.sync import Client, Server

from automation.opcua_server.identity import make_node_id


def _port() -> int:
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    return port


@unittest.skipUnless(os.environ.get("OPCUA_E2E") == "1", "set OPCUA_E2E=1 to run the SCADA client")
class TestScadaClient(unittest.TestCase):
    def test_browse_read_and_write(self):
        port = _port()
        server = Server()
        endpoint = f"opc.tcp://127.0.0.1:{port}/OPCUAServer/"
        server.set_endpoint(endpoint)
        idx = server.register_namespace("urn:pyautomationio:opcua:2.9")
        objects = server.get_node(ua.ObjectIds.ObjectsFolder)
        root = objects.add_folder(ua.NodeId(Identifier="PyAutomationIO", NamespaceIndex=idx), "PyAutomationIO")
        identifier = make_node_id("t", "L1", "fi_01")
        node = root.add_variable(ua.NodeId(Identifier=identifier, NamespaceIndex=idx), "fi_01", 0.0)
        server.start()
        client = Client(endpoint)
        try:
            client.connect()
            client.get_root_node().get_child(["0:Objects", f"{idx}:PyAutomationIO"])
            remote = client.get_node(node.nodeid.to_string())
            data_value = remote.read_value()
            self.assertEqual(data_value, 0.0)
            remote.write_value(2.5)
            self.assertEqual(remote.read_value(), 2.5)
        finally:
            try:
                client.disconnect()
            except Exception:
                client = None
            server.stop()
