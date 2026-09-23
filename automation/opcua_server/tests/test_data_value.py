import unittest
from types import SimpleNamespace

from automation.opcua_server.data_value import quality_to_status_code, to_data_value


class TestDataValue(unittest.TestCase):
    def test_good_quality_has_status_and_timestamp(self):
        tag = SimpleNamespace(
            quality=1.0,
            stale=False,
            opc_status_code=None,
            value=1.234567,
            timestamp=None,
            get_value=lambda: 1.234567,
            get_timestamp=lambda: None,
        )
        data_value = to_data_value(tag)
        self.assertIsNotNone(data_value.StatusCode)
        self.assertIsNotNone(data_value.SourceTimestamp)
        self.assertIsNotNone(data_value.ServerTimestamp)

    def test_stale_maps_to_waiting(self):
        from asyncua import ua

        tag = SimpleNamespace(quality=1.0, stale=True, opc_status_code=None)
        code = quality_to_status_code(tag)
        self.assertEqual(code.value, ua.StatusCode(ua.StatusCodes.BadWaitingForInitialData).value)
