import unittest
from unittest.mock import MagicMock, patch

from automation.opcua_server.access import AccessControlService


class TestAccess(unittest.TestCase):
    def test_batch_prefetch_is_one_query(self):
        logger = MagicMock()
        logger.read_by_namespaces.return_value = []
        with patch("automation.logger.opcua_server.OPCUAServerLogger", return_value=logger):
            service = AccessControlService({})
            namespaces = [f"ns=2;s=t:_:n{i}" for i in range(1000)]
            service.prefetch(namespaces)
        self.assertEqual(service.query_count, 1)
        self.assertEqual(logger.read_by_namespaces.call_count, 1)

    def test_five_thousand_is_one_query(self):
        logger = MagicMock()
        logger.read_by_namespaces.return_value = []
        with patch("automation.logger.opcua_server.OPCUAServerLogger", return_value=logger):
            service = AccessControlService({})
            service.prefetch([f"ns-{i}" for i in range(5000)])
        self.assertEqual(service.query_count, 1)

    def test_cache_hit_is_stored(self):
        service = AccessControlService({})
        service.remember("ns=2;s=t:_:a", 3)
        self.assertEqual(service.resolve("ns=2;s=t:_:a"), 3)
        self.assertEqual(service.resolve("missing"), 1)
