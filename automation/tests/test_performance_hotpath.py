# -*- coding: utf-8 -*-
"""Hot-path performance: Buffer O(1), CVT indexes, DAS subscribe dedupe."""
from __future__ import annotations

import unittest
from datetime import datetime
from unittest.mock import MagicMock

from ..buffer import Buffer
from ..opcua.subscription import DAS
from ..tags.cvt import CVT
from ..tags.tag import Tag


class FakeNodeId:
    def __init__(self, namespace: str):
        self._namespace = namespace

    def to_string(self):
        return self._namespace


class FakeDisplayName:
    def __init__(self, text: str):
        self.Text = text


class FakeNode:
    def __init__(self, namespace: str, name: str = "Press", value=1.0):
        self.nodeid = FakeNodeId(namespace)
        self._name = name
        self._value = value

    def get_display_name(self):
        return FakeDisplayName(self._name)

    def get_value(self):
        return self._value


class FakeSubscription:
    def __init__(self):
        self.subscribed = []
        self.unsubscribed = []
        self.deleted = False

    def subscribe_data_change(self, node):
        handle = object()
        self.subscribed.append((node, handle))
        return handle

    def unsubscribe(self, item):
        self.unsubscribed.append(item)

    def delete(self):
        self.deleted = True


class FakeClient:
    def __init__(self):
        self.created = 0
        self.subscription = FakeSubscription()

    def create_subscription(self, period, handler):
        self.created += 1
        return self.subscription


class TestBufferDeque(unittest.TestCase):
    def test_forward_newest_at_zero_and_maxlen(self):
        buf = Buffer(size=3, roll="forward")
        buf(1)
        buf(2)
        buf(3)
        buf(4)
        self.assertEqual(list(buf), [4, 3, 2])
        self.assertEqual(buf.current(), 4)
        self.assertEqual(buf.last(), 2)
        self.assertEqual(buf.previous_current(), 3)

    def test_backward_append(self):
        buf = Buffer(size=3, roll="backward")
        buf(1)
        buf(2)
        buf(3)
        buf(4)
        self.assertEqual(list(buf), [2, 3, 4])
        self.assertEqual(buf.current(), 4)

    def test_bounded_size_after_many_inserts(self):
        buf = Buffer(size=10, roll="forward")
        for i in range(600):
            buf(i)
        self.assertEqual(len(buf), 10)
        self.assertEqual(buf.current(), 599)

    def test_count_matches_list_semantics(self):
        buf = Buffer(size=8, roll="backward")
        buf(True)
        buf(False)
        buf(True)
        buf(True)
        self.assertEqual(buf.count(True), 3)
        self.assertEqual(buf.count(False), 1)


class TestCvtIndexes(unittest.TestCase):
    def test_lookups_are_o1_and_is_tag_defined_uses_name(self):
        cvt = CVT()
        tag = Tag(
            name="P1",
            unit="Pa",
            variable="Pressure",
            data_type="float",
            node_namespace="ns=2;s=P1",
            id="abcd1234",
        )
        cvt._tags[tag.id] = tag
        cvt._index_tag(tag)

        self.assertIs(cvt.get_tag("abcd1234"), tag)
        self.assertIs(cvt.get_tag_by_name("P1"), tag)
        self.assertIs(cvt.get_tag_by_node_namespace("ns=2;s=P1"), tag)
        self.assertTrue(cvt.is_tag_defined("P1"))
        self.assertFalse(cvt.is_tag_defined("abcd1234"))

    def test_delete_unindexes(self):
        cvt = CVT()
        tag = Tag(
            name="T1",
            unit="C",
            variable="Temperature",
            data_type="float",
            node_namespace="ns=2;s=T1",
            id="deadbeef",
        )
        cvt._tags[tag.id] = tag
        cvt._index_tag(tag)
        deleted, _ = cvt.delete_tag(id="deadbeef", user=None)
        self.assertIs(deleted, tag)
        self.assertIsNone(cvt.get_tag_by_name("T1"))
        self.assertFalse(cvt.is_tag_defined("T1"))

    def test_set_value_fast_path_writes_without_missing_tag_error(self):
        cvt = CVT()
        tag = Tag(
            name="F1",
            unit="C",
            variable="Temperature",
            data_type="float",
            id="f1f1f1f1",
        )
        cvt._tags[tag.id] = tag
        cvt._index_tag(tag)
        now = datetime.now()
        result = cvt.set_value(id=tag.id, value=21.5, timestamp=now)
        self.assertEqual(result, 21.5)
        self.assertEqual(tag.get_value(), 21.5)
        self.assertIsNone(cvt.set_value(id="missing", value=1, timestamp=now))


class TestAlarmManagerIndexes(unittest.TestCase):
    def setUp(self):
        from ..managers.alarms import AlarmManager

        self.mgr = AlarmManager()
        self.mgr._alarms.clear()
        self.mgr._by_name.clear()
        self.mgr._by_tag_name.clear()

    def test_lookup_by_name_and_tag_is_indexed(self):
        alarm = MagicMock()
        alarm.name = "HH_P1"
        alarm.tag = type("Tag", (), {"name": "P1"})()
        alarm.identifier = "id-1"
        alarm.detach_from_tag = MagicMock()
        alarm.remove_from_service = MagicMock()
        alarm._queue_observer = None
        self.mgr._alarms[alarm.identifier] = alarm
        self.mgr._index_alarm(alarm)

        self.assertIs(self.mgr.get_alarm_by_name("HH_P1"), alarm)
        self.assertEqual(self.mgr.get_alarm_by_tag("P1"), [alarm])
        self.assertEqual(self.mgr.get_alarm_by_tag(alarm.tag), [alarm])
        self.assertEqual(self.mgr.alarm_count(), 1)

        self.mgr._alarms.pop(alarm.identifier)
        self.mgr._unindex_alarm(alarm)
        self.assertIsNone(self.mgr.get_alarm_by_name("HH_P1"))
        self.assertEqual(self.mgr.get_alarm_by_tag("P1"), [])


class TestSocketPayloadAndTimestamp(unittest.TestCase):
    def test_serialize_socket_is_minimal(self):
        tag = Tag(name="F1", unit="C", variable="Temperature", data_type="float", id="f1f1f1f1")
        now = datetime.now()
        tag.set_value(value=21.5, timestamp=now)
        payload = tag.serialize_socket()
        self.assertEqual(set(payload.keys()), {"name", "value", "timestamp", "unit"})
        self.assertEqual(payload["name"], "F1")
        self.assertEqual(payload["value"], 21.5)
        self.assertIsInstance(payload["timestamp"], str)
        self.assertIn("T", payload["timestamp"])
        self.assertTrue(
            payload["timestamp"].endswith("+00:00") or payload["timestamp"].endswith("Z"),
            payload["timestamp"],
        )

    def test_producer_timestamp_required(self):
        from ..models import require_producer_timestamp

        with self.assertRaises(ValueError):
            require_producer_timestamp(machine=None)
        stamp = datetime(2026, 8, 13, 12, 0, 0, 123456)
        machine = type("M", (), {"cycle_timestamp": stamp})()
        resolved = require_producer_timestamp(machine)
        self.assertEqual(resolved.microsecond % 1000, 0)


class TestPendingCapAndReplicatorCache(unittest.TestCase):
    def test_pending_cap_alerts_without_deleting(self):
        import os
        import tempfile
        from datetime import timezone

        from ..persistence.config import SafConfig
        from ..persistence.exceptions import JournalBackpressureError
        from ..persistence.journal import JournalWriter
        from ..persistence.records import PersistableRecord

        with tempfile.TemporaryDirectory() as tmp:
            cfg = SafConfig(
                journal_path=os.path.join(tmp, "journal.db"),
                max_pending_rows=1,
                ring_maxsize=50,
            )
            writer = JournalWriter(cfg)
            try:
                first = PersistableRecord.tag_sample("T1", 1.0, datetime.now(timezone.utc))
                writer.append(first)
                with self.assertRaises(JournalBackpressureError):
                    writer.append(PersistableRecord.tag_sample("T2", 2.0, datetime.now(timezone.utc)))
                self.assertGreaterEqual(writer.pending_cap_hits, 1)
            finally:
                writer.stop()

    def test_payload_mapper_caches_tags_per_batch(self):
        from datetime import timezone

        from ..persistence.remote import TagValuePayloadMapper

        class FakeTag:
            def __init__(self, name):
                self.name = name
                self.id = name
                self.display_unit = type("U", (), {"id": 1})()
                self.unit = self.display_unit

        lookups = []

        def resolve_tag(name):
            lookups.append(name)
            return FakeTag(name)

        mapper = TagValuePayloadMapper(
            resolve_tag=resolve_tag,
            resolve_unit=lambda tag: tag.unit,
        )
        ts = datetime(2026, 8, 13, 12, 0, 0, tzinfo=timezone.utc).isoformat()
        rows = mapper.to_rows(
            [
                {"tag": "A", "value": 1, "timestamp": ts},
                {"tag": "A", "value": 2, "timestamp": ts},
                {"tag": "B", "value": 3, "timestamp": ts},
            ]
        )
        self.assertEqual(len(rows), 3)
        self.assertEqual(lookups, ["A", "B"])

    def test_cycle_cache_prunes_on_interval_not_every_call(self):
        from ..persistence.cycle_dedupe import CycleSampleCache
        from ..persistence.records import PersistableRecord

        cache = CycleSampleCache(ttl_s=2.0)
        cache._prune_every_s = 10.0
        sample = PersistableRecord.tag_sample("T1", 1.0, datetime.now())
        self.assertFalse(cache.should_drop(sample))
        self.assertTrue(cache.should_drop(sample))
        self.assertEqual(cache.dropped, 1)


class TestDasSubscribeDedupe(unittest.TestCase):
    def setUp(self):
        self.das = DAS()
        self.das.monitored_items = {}
        self.das.client_subscriptions = {}
        self.das.cvt = MagicMock()
        self.das.cvt.get_tag_by_node_namespace.return_value = None

    def test_resubscribe_same_namespace_unsubscribes_previous(self):
        subscription = FakeSubscription()
        node = FakeNode("ns=2;s=Press")
        self.das.subscribe(subscription, "PLC", node)
        self.das.subscribe(subscription, "PLC", node)
        self.assertEqual(len(subscription.subscribed), 2)
        self.assertEqual(len(subscription.unsubscribed), 1)
        self.assertEqual(self.das.monitored_count(), 1)
        self.assertIn("ns=2;s=Press", self.das.monitored_items["PLC"])

    def test_one_subscription_per_client(self):
        client = FakeClient()
        first = self.das.get_or_create_subscription(client, "PLC")
        second = self.das.get_or_create_subscription(client, "PLC")
        self.assertIs(first, second)
        self.assertEqual(client.created, 1)

    def test_reset_client_clears_handles(self):
        subscription = FakeSubscription()
        self.das.client_subscriptions["PLC"] = subscription
        node = FakeNode("ns=2;s=Press")
        self.das.subscribe(subscription, "PLC", node)
        self.das.reset_client("PLC")
        self.assertEqual(self.das.monitored_count(), 0)
        self.assertNotIn("PLC", self.das.client_subscriptions)
        self.assertTrue(subscription.deleted)


if __name__ == "__main__":
    unittest.main()
