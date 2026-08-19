# -*- coding: utf-8 -*-
from __future__ import annotations

import os
import sys
import tempfile
import types
import unittest
from contextlib import contextmanager
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from ..opcua.subscription import DAS
from ..persistence.config import SafConfig
from ..persistence.journal import JournalWriter
from ..persistence.orchestrator import PersistenceOrchestrator
from ..persistence.records import PersistableRecord
from ..persistence.replicator import RemoteReplicator
from ..tags.cvt import CVT
from ..tags.tag import Tag, TagObserver


class FakeScope:
    enabled = True
    is_valid = True
    node_id = "edge-a"
    area = "Area-A"
    site = "Plant"

    def owns_area(self, area):
        return area == self.area

    def owns_node(self, owner_node):
        return owner_node == self.node_id

    def owns_tag(self, tag):
        return self.owns_area(getattr(tag, "area", None)) and self.owns_node(
            getattr(tag, "owner_node", None)
        )


@contextmanager
def installed_scope(scope=None):
    scope = scope or FakeScope()
    module = types.ModuleType("automation.node_scope")
    module.get_node_scope = lambda: scope
    with patch.dict(sys.modules, {"automation.node_scope": module}):
        yield scope


def make_tag(name, area="Area-A", owner_node="edge-a"):
    return Tag(
        name=name,
        unit="C",
        variable="Temperature",
        data_type="float",
        area=area,
        owner_node=owner_node,
    )


class FakeRemote:
    def __init__(self):
        self.written = []

    def is_reachable(self):
        return True

    def write_batch(self, domain, payloads):
        self.written.extend((domain, dict(item)) for item in payloads)
        return len(payloads)

    def batch_insert_with_dedupe(self, payloads):
        return self.write_batch("tag", payloads)


class TestMultiEdgeHotPath(unittest.TestCase):
    def test_machines_engine_create_accepts_area(self):
        import inspect
        from ..logger.machines import MachinesLoggerEngine

        signature = inspect.signature(MachinesLoggerEngine.create)
        self.assertIn("area", signature.parameters)

    def test_tag_serializes_partition_identity(self):
        tag = make_tag("Area-A.T1")
        payload = tag.serialize()
        self.assertEqual(payload["area"], "Area-A")
        self.assertEqual(payload["owner_node"], "edge-a")

    def test_cvt_rejects_foreign_write_without_mutating_tag(self):
        cvt = CVT()
        own = make_tag("Area-A.T1")
        foreign = make_tag("Area-B.T1", area="Area-B", owner_node="edge-b")
        for tag in (own, foreign):
            cvt._tags[tag.id] = tag
            cvt._index_tag(tag)
        stamp = datetime.now(timezone.utc)

        with installed_scope():
            self.assertEqual(
                cvt.set_value(id=own.id, value=10.0, timestamp=stamp),
                10.0,
            )
            self.assertIsNone(
                cvt.set_value(id=foreign.id, value=20.0, timestamp=stamp)
            )

        self.assertEqual(own.get_value(), 10.0)
        self.assertEqual(foreign.get_value(), 0.0)

    def test_cvt_creation_assigns_scope_and_rejects_foreign_identity(self):
        cvt = CVT()
        with installed_scope():
            own, _ = cvt.set_tag(
                name="Area-A.T1",
                unit="C",
                data_type="float",
                description="",
                variable="Temperature",
            )
            foreign, message = cvt.set_tag(
                name="Area-B.T1",
                unit="C",
                data_type="float",
                description="",
                variable="Temperature",
                area="Area-B",
                owner_node="edge-b",
            )
        self.assertEqual(own.area, "Area-A")
        self.assertEqual(own.owner_node, "edge-a")
        self.assertIsNone(foreign)
        self.assertIn("not owned", message)

    def test_tag_observer_does_not_enqueue_foreign_sample_and_audits_once(self):
        tag = make_tag("Area-B.T1", area="Area-B", owner_node="edge-b")
        observer = TagObserver(MagicMock())
        tag.attach(observer)
        with installed_scope(), patch(
            "automation.utils.system_event_audit.persist_system_event"
        ) as audit, patch(
            "automation.persistence.orchestrator.PersistenceOrchestrator.enqueue"
        ) as enqueue:
            observer.update()
        enqueue.assert_not_called()
        audit.assert_called_once()

    def test_das_does_not_subscribe_foreign_namespace(self):
        das = DAS()
        das.monitored_items = {}
        das.client_subscriptions = {}
        foreign = make_tag("Area-B.T1", area="Area-B", owner_node="edge-b")
        foreign.node_namespace = "ns=2;s=T1"
        das.cvt = MagicMock()
        das.cvt.get_tag_by_node_namespace.return_value = foreign
        subscription = MagicMock()
        node = type(
            "Node",
            (),
            {"nodeid": type("NodeId", (), {"to_string": lambda self: "ns=2;s=T1"})()},
        )()

        with installed_scope():
            self.assertIsNone(das.subscribe(subscription, "PLC-B", node))
        subscription.subscribe_data_change.assert_not_called()

    def test_opc_client_never_connects_for_foreign_owner(self):
        with patch("automation.opcua.models.OPCClient.__init__", return_value=None):
            from ..opcua.models import Client

            client = Client(
                "opc.tcp://127.0.0.1:4840",
                client_name="PLC-B",
                owner_node="edge-b",
            )
        with installed_scope(), patch(
            "automation.opcua.models.OPCClient.connect"
        ) as connect:
            result, status = client.connect()
        self.assertEqual(status, 403)
        self.assertFalse(result["is_connected"])
        connect.assert_not_called()


class TestMultiEdgeSaf(unittest.TestCase):
    def test_records_carry_scope_metadata(self):
        with installed_scope():
            record = PersistableRecord.tag_sample(
                "Area-A.T1",
                1.0,
                datetime.now(timezone.utc),
            )
        self.assertEqual(record.payload()["area"], "Area-A")
        self.assertEqual(record.payload()["owner_node"], "edge-a")

    def test_orchestrator_rejects_foreign_record_before_journal(self):
        with tempfile.TemporaryDirectory() as tmp, installed_scope():
            config = SafConfig(journal_path=os.path.join(tmp, "journal.db"))
            orchestrator = PersistenceOrchestrator(config=config, remote=FakeRemote())
            try:
                record = PersistableRecord.tag_sample(
                    "Area-B.T1",
                    1.0,
                    datetime.now(timezone.utc),
                    area="Area-B",
                    owner_node="edge-b",
                )
                self.assertEqual(orchestrator.enqueue(record), 0)
                self.assertEqual(orchestrator.pending_count(), 0)
            finally:
                orchestrator.close()

    def test_replicator_discards_foreign_pending_without_remote_write(self):
        with tempfile.TemporaryDirectory() as tmp, installed_scope():
            config = SafConfig(
                journal_path=os.path.join(tmp, "journal.db"),
                gc_sent_after_s=3600,
                replicate_rate_per_s=100,
            )
            journal = JournalWriter(config)
            remote = FakeRemote()
            try:
                journal.append(
                    PersistableRecord.tag_sample(
                        "Area-B.T1",
                        1.0,
                        datetime.now(timezone.utc),
                        area="Area-B",
                        owner_node="edge-b",
                    )
                )
                journal.flush_sync()
                replicator = RemoteReplicator(journal, remote, config)
                self.assertEqual(replicator.replicate_once(), 0)
                self.assertEqual(journal.fetch_pending(10), [])
                self.assertEqual(remote.written, [])
            finally:
                journal.stop()


class TestApplicationAlarmContract(unittest.TestCase):
    def test_leak_alarm_name_does_not_need_area_prefix(self):
        env = {
            "AUTOMATION_MULTI_EDGE_ENABLED": "true",
            "AUTOMATION_NODE_ID": "edge-linea1",
            "AUTOMATION_SEGMENT": "Linea1",
            "AUTOMATION_MANUFACTURER": "Test",
        }
        with patch.dict(os.environ, env, clear=False):
            from .. import PyAutomation

            app = PyAutomation()
            app._refresh_node_scope()
            tag_name = f"Test.Linea1.LDS.leak.{id(self)}"
            alarm_name = f"alarm.{tag_name}"
            tag, message = app.cvt.set_tag(
                name=tag_name,
                unit="adim",
                data_type="int",
                description="leak flag",
                variable="Adimentional",
            )
            self.assertIsNotNone(tag, message)
            alarm, message = app.create_alarm(
                name=alarm_name,
                tag=tag_name,
                skip_validation=True,
            )
            self.assertIsNotNone(alarm, message)
            self.assertIsNotNone(app.get_alarm_by_name(name=alarm_name))
            self.assertIsNone(app.get_alarm_by_name(name=f"missing.{id(self)}"))


if __name__ == "__main__":
    unittest.main()
