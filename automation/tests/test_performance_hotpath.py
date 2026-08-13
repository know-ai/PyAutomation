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
