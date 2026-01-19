import json
import unittest
from datetime import datetime


class FakeRange:
    def __init__(self, low, high):
        self.Low = low
        self.High = high


class TestOpcuaSerialization(unittest.TestCase):
    def test_to_jsonable_range(self):
        # Import local para no romper discovery si dependencias opcua no están cargadas al importar tests
        from ..opcua.models import Client

        r = FakeRange(low=0.0, high=100.0)
        out = Client._to_jsonable(r)
        self.assertIsInstance(out, dict)
        self.assertEqual(out["Low"], 0.0)
        self.assertEqual(out["High"], 100.0)
        # Debe ser serializable por json
        json.dumps(out)

    def test_to_jsonable_datetime(self):
        from ..opcua.models import Client

        ts = datetime(2026, 1, 1, 12, 0, 0)
        out = Client._to_jsonable(ts)
        self.assertEqual(out, ts.isoformat())
        json.dumps(out)

    def test_to_jsonable_nested(self):
        from ..opcua.models import Client

        payload = {
            "a": FakeRange(1, 2),
            "b": [FakeRange(3, 4), None],
        }
        out = Client._to_jsonable(payload)
        json.dumps(out)


