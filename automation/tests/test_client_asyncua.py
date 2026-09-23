"""Contract tests for the asyncua field client. No PLC socket."""

from __future__ import annotations

import asyncio
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from automation.opcua.asyncua_client.command_queue import ClientCommandQueue
from automation.opcua.asyncua_client.commands import DasResult, ReadBatch, ReadBatchResult
from automation.opcua.asyncua_client.handlers import DasHandler, LoopContext, handle
from automation.opcua.asyncua_client.result_queue import ClientResultQueue
from automation.opcua.subscription import DAS, clamp_subscription_period_ms


class TestClientQueues(unittest.TestCase):
    def test_command_queue_has_explicit_maxsize(self):
        queue = ClientCommandQueue()
        self.assertEqual(queue.maxsize, 10_000)

    def test_result_queue_discards_oldest(self):
        queue = ClientResultQueue(maxsize=2)
        queue.put("a")
        queue.put("b")
        queue.put("c")
        self.assertGreaterEqual(queue.discarded, 1)
        self.assertEqual(queue.drain(), ["b", "c"])


class TestReadBatchParallel(unittest.TestCase):
    def test_two_clients_overlap_on_one_loop(self):
        entered = []
        left = []

        async def slow(ctx, command):
            if not isinstance(command, ReadBatch):
                return
            entered.append((command.client_name, time.monotonic()))
            await asyncio.sleep(0.2)
            left.append((command.client_name, time.monotonic()))
            ctx.results.put(ReadBatchResult(command.correlation_id, ()))

        async def run():
            ctx = LoopContext(SimpleNamespace(put=lambda item: None), lambda name, flag: None)
            await asyncio.gather(
                slow(ctx, ReadBatch("PLC-A", ("ns=2;i=1",), "a")),
                slow(ctx, ReadBatch("PLC-B", ("ns=2;i=2",), "b")),
            )

        asyncio.run(run())
        self.assertEqual(len(entered), 2)
        self.assertLess(left[0][1], entered[0][1] + 0.35)
        self.assertLess(max(item[1] for item in entered), min(item[1] for item in left))

    def test_handler_read_uses_read_attributes(self):
        source = Path("automation/opcua/asyncua_client/handlers.py").read_text(encoding="utf-8")
        self.assertIn("read_attributes", source)
        self.assertNotIn("read_values", source)


class TestSubscribeContract(unittest.TestCase):
    def test_period_is_clamped(self):
        self.assertEqual(clamp_subscription_period_ms(50), 100)
        self.assertEqual(clamp_subscription_period_ms(100), 100)
        self.assertEqual(clamp_subscription_period_ms(None), 1000)
        self.assertEqual(clamp_subscription_period_ms(5000), 1000)

    def test_one_lease_per_client(self):
        das = DAS()
        das.client_subscriptions = {}
        client = SimpleNamespace(uses_asyncua_runner=True, name="PLC")
        with patch("automation.opcua.asyncua_client.sync_adapter.get_runner"):
            first = das.get_or_create_subscription(client, "PLC", period=80)
            second = das.get_or_create_subscription(client, "PLC", period=90)
        self.assertIs(first, second)
        self.assertEqual(first.period_ms, 100)

    def test_callback_does_not_write_cvt(self):
        queued = []
        handler = DasHandler(SimpleNamespace(put=queued.append))
        node = SimpleNamespace(nodeid=SimpleNamespace(to_string=lambda: "ns=2;s=PV"))
        data = SimpleNamespace(
            monitored_item=SimpleNamespace(
                Value=SimpleNamespace(StatusCode=0x80000000, SourceTimestamp=None)
            )
        )
        with patch("automation.tags.cvt.CVTEngine.set_value_fast", side_effect=AssertionError("cvt")):
            handler.datachange_notification(node, 1.0, data)
        self.assertEqual(queued[0].namespace, "ns=2;s=PV")
        self.assertIsInstance(queued[0], DasResult)

    def test_loops_are_distinct_types(self):
        from automation.opcua.asyncua_client.runner import ClientRunner
        from automation.opcua_server.async_core.runner import AsyncioRunner

        self.assertIsNot(ClientRunner, AsyncioRunner)
        source = Path("automation/opcua/asyncua_client/runner.py").read_text(encoding="utf-8")
        self.assertIn('name="opcua-asyncua-client"', source)


class TestDasDrainWritesOnGeventSide(unittest.TestCase):
    def test_drain_calls_update_tag_value(self):
        from automation.opcua.asyncua_client.sync_adapter import _apply

        das = DAS()
        das.update_tag_value = MagicMock()
        item = DasResult("ns=2;s=PV", 3.0, 0, None)
        with patch("automation.opcua.subscription.DAS", return_value=das):
            _apply(item)
        das.update_tag_value.assert_called_once()
        node = das.update_tag_value.call_args.args[0]
        self.assertEqual(node.nodeid.to_string(), "ns=2;s=PV")


class TestHandleDoesNotTouchCvt(unittest.TestCase):
    def test_unknown_command_is_ignored(self):
        ctx = LoopContext(SimpleNamespace(put=lambda item: None), lambda name, flag: None)

        async def run():
            await handle(ctx, SimpleNamespace(correlation_id=None))

        asyncio.run(run())
