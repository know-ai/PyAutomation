# -*- coding: utf-8 -*-
"""CT-01 / CT-02 / CT-04 supports: NTP gate, journal fsync fd, peer heartbeat."""
from __future__ import annotations

import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

from peewee import SqliteDatabase

from automation.dbmodels import Nodes, proxy
from automation.persistence.config import SafConfig
from automation.persistence.journal import JournalWriter
from automation.persistence.records import PersistableRecord
from automation.persistence.replicator import (
    RemoteReplicator,
    clock_blocks_replication,
)
from automation.workers.metrics_sampler import MetricsSamplerWorker

from .test_store_and_forward import FakeRemote


class TestClockBlocksReplication(unittest.TestCase):
    def test_disabled_or_unknown_does_not_block(self):
        self.assertEqual(clock_blocks_replication(None), "")
        self.assertEqual(clock_blocks_replication({"enabled": False, "offset_ms": 5000}), "")
        self.assertEqual(clock_blocks_replication({"enabled": True, "offset_ms": None}), "")

    def test_blocks_when_abs_offset_exceeds_one_second(self):
        reason = clock_blocks_replication({"enabled": True, "offset_ms": 1500})
        self.assertIn("exceeds", reason)
        reason_neg = clock_blocks_replication({"enabled": True, "offset_ms": -1200})
        self.assertIn("exceeds", reason_neg)

    def test_allows_sub_second_offset(self):
        self.assertEqual(
            clock_blocks_replication({"enabled": True, "offset_ms": 250.0}),
            "",
        )


class TestReplicatorNtpGate(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.config = SafConfig(
            journal_path=os.path.join(self.tmp.name, "journal.db"),
            replicate_batch_size=10,
            replicate_rate_per_s=10_000,
        )
        self.journal = JournalWriter(self.config)
        self.journal.start()
        self.journal.append(
            PersistableRecord.event(message="ntp-gate", username="system")
        )
        self.journal.flush_sync()

    def tearDown(self):
        self.journal.stop()
        self.tmp.cleanup()

    def test_keeps_pending_when_clock_offset_exceeds_1s(self):
        remote = FakeRemote()
        replicator = RemoteReplicator(self.journal, remote, self.config)
        status = {"enabled": True, "offset_ms": 2500.0}
        with patch("automation.persistence.replicator._node_scope", return_value=None), patch(
            "automation.persistence.replicator._live_clock_status",
            return_value=status,
        ):
            self.assertEqual(replicator.replicate_once(), 0)
        self.assertIn("clock offset", replicator.last_error)
        self.assertEqual(len(self.journal.fetch_pending(10)), 1)
        self.assertEqual(len(remote.written), 0)

    def test_replicates_when_clock_ok(self):
        remote = FakeRemote()
        replicator = RemoteReplicator(self.journal, remote, self.config)
        with patch("automation.persistence.replicator._node_scope", return_value=None), patch(
            "automation.persistence.replicator._live_clock_status",
            return_value={"enabled": True, "offset_ms": 12.0},
        ):
            self.assertGreaterEqual(replicator.replicate_once(), 1)
        self.assertEqual(len(self.journal.fetch_pending(10)), 0)


class TestJournalDurabilityFd(unittest.TestCase):
    def test_opens_readonly_fd_for_post_commit_fsync(self):
        tmp = tempfile.TemporaryDirectory()
        try:
            writer = JournalWriter(
                SafConfig(journal_path=os.path.join(tmp.name, "journal.db"))
            )
            writer.start()
            self.assertGreaterEqual(writer._durability_fd, 0)
            writer.stop()
            self.assertEqual(writer._durability_fd, -1)
        finally:
            tmp.cleanup()


class TestNodeHeartbeat(unittest.TestCase):
    def setUp(self):
        self.db = SqliteDatabase(":memory:")
        proxy.initialize(self.db)
        self.db.create_tables([Nodes])

    def tearDown(self):
        self.db.close()

    def test_stale_peer_ids_after_ttl(self):
        now = datetime(2026, 8, 28, 12, 0, tzinfo=timezone.utc)
        Nodes.register("edge-a", "Linea1", now=now)
        Nodes.register("edge-b", "Linea2", now=now - timedelta(seconds=120))
        Nodes.heartbeat("edge-a", now=now)
        stale = Nodes.stale_peer_ids("edge-a", older_than_s=90.0, now=now)
        self.assertEqual(stale, ["edge-b"])
        fresh = Nodes.stale_peer_ids("edge-a", older_than_s=180.0, now=now)
        self.assertEqual(fresh, [])


class TestSamplerNtpFields(unittest.TestCase):
    def test_exposes_host_ntp_abs_offset(self):
        worker = MetricsSamplerWorker(interval_seconds=5.0)
        ntp = MagicMock()
        ntp.get_status.return_value = {
            "enabled": True,
            "synced": True,
            "warn": False,
            "offset_ms": -42.5,
        }
        app = MagicMock()
        app.ntp_worker = ntp
        payload: dict = {}
        with patch("automation.PyAutomation", return_value=app):
            worker._sample_clock(payload)
        self.assertEqual(payload["HOST_NTP_OFFSET_MS"], -42.5)
        self.assertEqual(payload["HOST_NTP_ABS_OFFSET_MS"], 42.5)
        self.assertEqual(payload["HOST_NTP_SYNCED"], 1.0)
        self.assertEqual(payload["clock"]["offset_ms"], -42.5)
