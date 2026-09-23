import unittest
from unittest.mock import MagicMock, patch

from automation.opcua_server.writeback import WriteBackHandler


class TestWriteBack(unittest.TestCase):
    def test_one_subscription_for_one_hundred_nodes(self):
        handler = MagicMock()
        handler.subscriptions = {}
        server = MagicMock()
        subscription = MagicMock()
        server.create_subscription.return_value = subscription
        writeback = WriteBackHandler()
        with patch("automation.opcua.subscription.SubHandlerServer", return_value=handler):
            for index in range(100):
                node = MagicMock()
                node.nodeid.to_string.return_value = f"ns=2;s=t:_:n{index}"
                writeback.subscribe(server, node)
        self.assertEqual(server.create_subscription.call_count, 1)
        self.assertEqual(writeback.active, 100)
        self.assertEqual(len(handler.subscriptions), 100)
