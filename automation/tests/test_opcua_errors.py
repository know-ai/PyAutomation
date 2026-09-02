import unittest

from automation.opcua.errors import (
    BROWSE_FAILED,
    CLIENT_NOT_FOUND,
    CONNECTION_REFUSED,
    CONNECTION_TIMEOUT,
    DISCOVERY_FAILED,
    NOT_CONNECTED,
    classify_opcua_error,
    from_connect_failure,
    opcua_error,
    unpack_result,
)


class TestOpcUaErrors(unittest.TestCase):
    def test_classify_connection_refused(self):
        self.assertEqual(
            classify_opcua_error("ConnectionRefusedError: [Errno 111] Connection refused"),
            CONNECTION_REFUSED,
        )

    def test_classify_timeout(self):
        self.assertEqual(classify_opcua_error("TimeoutError: timed out"), CONNECTION_TIMEOUT)

    def test_classify_nonetype_unpack_as_not_connected(self):
        self.assertEqual(
            classify_opcua_error("cannot unpack non-iterable NoneType object"),
            NOT_CONNECTED,
        )

    def test_classify_dict_payload(self):
        payload = {
            "message": "Connection could not be established",
            "url": "opc.tcp://172.20.0.1:4840",
            "error": "ConnectionRefusedError: [Errno 111] Connection refused",
        }
        self.assertEqual(classify_opcua_error(payload), CONNECTION_REFUSED)

    def test_classify_discovery_not_client_not_found(self):
        self.assertEqual(classify_opcua_error("Servers not found at host"), DISCOVERY_FAILED)
        self.assertEqual(classify_opcua_error("OPC UA client not found"), CLIENT_NOT_FOUND)

    def test_from_connect_failure_keeps_endpoint(self):
        payload = from_connect_failure(
            {
                "message": "Connection could not be established",
                "url": "opc.tcp://172.20.0.1:4840",
                "error": "ConnectionRefusedError: [Errno 111] Connection refused",
            },
            client="PLC",
            host="172.20.0.1",
            port=4840,
        )
        self.assertEqual(payload["code"], CONNECTION_REFUSED)
        self.assertNotIn("Errno 111", payload["message"])
        self.assertEqual(payload["params"]["url"], "opc.tcp://172.20.0.1:4840")
        self.assertEqual(payload["params"]["client"], "PLC")

    def test_payload_never_embeds_raw_dict(self):
        payload = opcua_error(BROWSE_FAILED, client="PLC")
        self.assertEqual(payload["code"], BROWSE_FAILED)
        self.assertIsInstance(payload["message"], str)
        self.assertNotIn("{", payload["message"])

    def test_unpack_result(self):
        self.assertEqual(unpack_result(("tree", 200)), ("tree", 200))
        self.assertEqual(unpack_result(None), (None, None))

    def test_none_tree_becomes_structured_browse_error(self):
        tree, extra = unpack_result(None)
        self.assertIsNone(tree)
        payload = from_connect_failure("cannot unpack non-iterable NoneType object", client="PLC")
        self.assertEqual(payload["code"], NOT_CONNECTED)
        self.assertEqual(payload["params"]["client"], "PLC")


if __name__ == "__main__":
    unittest.main()
