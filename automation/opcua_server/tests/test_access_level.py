"""Access level, write gate, router, rollback, rate limit and terminology."""

import ast
import pathlib
import unittest
from types import SimpleNamespace

from asyncua import ua

from automation.opcua_server.access.applier import apply_level
from automation.opcua_server.access.enforcement import (
    check_history_read,
    check_history_write,
    check_value_write,
)
from automation.opcua_server.access.level import AccessLevel, access_label, parse_access_level
from automation.opcua_server.dirty.observer import TagDirtyObserver
from automation.opcua_server.linting.rules.ap_10_access import AccessWriteGateRule, scan_sources
from automation.opcua_server.loop_prevention import SlidingWindowRateLimiter, WindowOscillationDetector
from automation.opcua_server.propagation import (
    CvtRollback,
    FieldPropagationRouter,
    PropagationResult,
    http_status,
    new_transaction,
)

ROOT = pathlib.Path(__file__).resolve().parents[3]


class _Node:
    def __init__(self) -> None:
        self.bits: dict = {}

    async def set_attr_bit(self, attr, bit) -> None:
        self.bits.setdefault(attr, set()).add(bit)

    async def unset_attr_bit(self, attr, bit) -> None:
        self.bits.setdefault(attr, set()).discard(bit)

    async def write_attribute(self, attr, value) -> None:
        raise RuntimeError("attribute rejected")


class _Writer:
    def __init__(self, status: str) -> None:
        self.status = status
        self.calls = 0

    def write(self, url, node_id, value) -> str:
        self.calls += 1
        return self.status


class TestParser(unittest.TestCase):
    def test_int_hex_and_labels(self):
        self.assertEqual(parse_access_level(3), 3)
        self.assertEqual(parse_access_level("0x03"), 3)
        self.assertEqual(parse_access_level("Read"), 1)
        self.assertEqual(parse_access_level("Write"), 2)
        self.assertEqual(parse_access_level("ReadWrite"), 3)
        self.assertEqual(parse_access_level("TimestampWrite"), 0x40)
        self.assertEqual(access_label(1), "Read")
        self.assertEqual(access_label(0x41), "CurrentRead|TimestampWrite")
        with self.assertRaises(ValueError):
            parse_access_level("nope")

    def test_each_bit_is_distinct(self):
        masks = [int(bit) for bit in AccessLevel]
        self.assertEqual(len(masks), 7)
        self.assertEqual(len(set(masks)), 7)


class TestApplier(unittest.IsolatedAsyncioTestCase):
    async def test_apply_sets_and_clears_bits(self):
        node = _Node()
        stuck = await apply_level(node, AccessLevel.CURRENT_READ | AccessLevel.CURRENT_WRITE)
        self.assertFalse(stuck)
        written = node.bits[ua.AttributeIds.AccessLevel]
        self.assertIn(ua.AccessLevel.CurrentRead, written)
        self.assertIn(ua.AccessLevel.CurrentWrite, written)
        self.assertNotIn(ua.AccessLevel.HistoryRead, written)
        self.assertEqual(node.bits[ua.AttributeIds.UserAccessLevel], written)


class TestStatusCodes(unittest.TestCase):
    def test_each_denial(self):
        self.assertEqual(check_value_write(1, 1), ua.StatusCodes.BadNotWritable)
        self.assertEqual(check_value_write(3, 1), ua.StatusCodes.BadUserAccessDenied)
        self.assertEqual(check_value_write(3, 3, status_code=1), ua.StatusCodes.BadNotWritable)
        self.assertIsNone(check_value_write(0x23, 0x23, status_code=1))
        self.assertEqual(check_value_write(3, 3, explicit_timestamp=True), ua.StatusCodes.BadNotWritable)
        self.assertIsNone(check_value_write(0x43, 0x43, explicit_timestamp=True, value=1.0, expected="analog"))
        self.assertEqual(check_value_write(3, 3, value="x", expected="analog"), ua.StatusCodes.BadTypeMismatch)
        self.assertEqual(
            check_value_write(3, 3, value=11, expected="analog", low=0, high=10),
            ua.StatusCodes.BadOutOfRange,
        )
        self.assertEqual(check_value_write(3, 3, value=1, rate_ok=False), ua.StatusCodes.BadTooManyOperations)
        self.assertEqual(check_history_read(1), ua.StatusCodes.BadUserAccessDenied)
        self.assertIsNone(check_history_read(0x04))
        self.assertEqual(check_history_write(1), ua.StatusCodes.BadNotWritable)
        self.assertIsNone(check_history_write(0x08))


class TestRouter(unittest.TestCase):
    def test_fake_writer_and_rollback(self):
        tag = SimpleNamespace(opcua_address="opc.tcp://127.0.0.1:4840", node_namespace="ns=2;s=t")
        writer = _Writer("ok")
        rolled = {}

        class _Cvt:
            def set_value_fast(self, id, value, timestamp, **kwargs):
                rolled["source"] = kwargs.get("source")
                rolled["value"] = value

        result = FieldPropagationRouter(writer).route(tag, 15, new_transaction())
        self.assertTrue(result.ok)
        self.assertEqual(http_status(result), 200)
        self.assertEqual(writer.calls, 1)
        failed = FieldPropagationRouter(_Writer("timeout")).route(tag, 15, new_transaction())
        self.assertEqual(http_status(failed), 504)
        down = FieldPropagationRouter(_Writer("disconnected")).route(tag, 15, new_transaction())
        self.assertEqual(http_status(down), 503)
        rejected = FieldPropagationRouter(_Writer("bad")).route(tag, 15, new_transaction())
        self.assertEqual(http_status(rejected), 400)
        skipped = FieldPropagationRouter(writer).route(tag, 15, new_transaction(source="field"))
        self.assertEqual(skipped, PropagationResult.skipped("field_origin"))
        CvtRollback(_Cvt()).revert(SimpleNamespace(id="t1", value=SimpleNamespace(value=4)), 4)
        self.assertEqual(rolled["source"], "rollback")
        self.assertEqual(rolled["value"], 4)

    def test_external_source_does_not_mark_dirty(self):
        server = SimpleNamespace(marked=False, mark_tag=lambda tag: setattr(server, "marked", True))
        observer = TagDirtyObserver(server)
        observer._subject = SimpleNamespace(last_source="external")
        observer.update()
        self.assertFalse(server.marked)
        observer._subject = SimpleNamespace(last_source="rollback")
        observer.update()
        self.assertTrue(server.marked)


class TestLimits(unittest.TestCase):
    def test_rate_and_oscillation(self):
        limiter = SlidingWindowRateLimiter(tag_per_s=10, session_per_s=100)
        self.assertTrue(all(limiter.allow("tag", "session") for _ in range(10)))
        self.assertFalse(limiter.allow("tag", "session"))
        detector = WindowOscillationDetector(limit=8, window_s=10, throttle_s=60)
        flags = [detector.observe("tag", i) for i in range(8)]
        self.assertEqual(flags, [False] * 7 + [True])
        self.assertTrue(detector.throttled("tag"))


class TestTerminologyLint(unittest.TestCase):
    def test_null_handler_is_flagged(self):
        rule = AccessWriteGateRule()
        tree = ast.parse("def run():\n    server.create_subscription(100, None)\n")
        self.assertTrue(rule.check(tree, "missing.py"))
        clean = ast.parse("def _ensure_write_subscription():\n    server.create_subscription(100, handler)\n")
        self.assertEqual(rule.check(clean, "missing.py"), [])

    def test_product_sources_do_not_use_the_retired_name(self):
        hits = scan_sources(ROOT / "automation") + scan_sources(ROOT / "hmi" / "src")
        self.assertEqual(hits, [])
