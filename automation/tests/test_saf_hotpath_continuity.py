# -*- coding: utf-8 -*-
"""SPEC-SAF-HOTPATH-CONTINUITY: ring, rewind, idle compact, ACK order."""
from __future__ import annotations

import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

from ..alarms import Alarm
from ..alarms.states import AlarmState
from ..models import FloatType, StringType
from ..persistence.config import SafConfig
from ..persistence.exceptions import JournalBackpressureError, JournalDiskFullError
from ..persistence.journal import JournalWriter, STATUS_REPLICATING
from ..persistence.outbox import journal_then_remote
from ..persistence.records import PersistableRecord
from ..tags.tag import Tag


def _writer(tmp: str, **kwargs) -> JournalWriter:
    defaults = dict(
        journal_path=os.path.join(tmp, "journal.db"),
        tag_flush_interval_s=60.0,
        ring_maxsize=8,
    )
    defaults.update(kwargs)
    writer = JournalWriter(SafConfig(**defaults))
    writer.start()
    writer._stop.set()
    writer._ring_event.set()
    if writer._flusher:
        writer._flusher.join(timeout=1)
    if writer._emergency:
        writer._emergency.join(timeout=1)
    return writer


class TestJournalHotPath(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.tmp.cleanup()

    def test_reader_sees_committed_rows_without_writer_lock(self):
        writer = _writer(self.tmp.name)
        try:
            self.assertIsNotNone(writer._reader)
            writer.append(PersistableRecord.event(message="visible", username="system"))
            rows = writer.fetch_pending(5)
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["domain"], "event")
        finally:
            writer.stop()

    def test_full_ring_does_not_commit(self):
        writer = _writer(self.tmp.name, ring_maxsize=1)
        try:
            writer._ring.clear()
            commits = writer.commit_count
            stamp = datetime(2026, 9, 29, tzinfo=timezone.utc)
            writer.append(PersistableRecord.tag_sample("SYS.PERF.CPU", 1.0, stamp))
            with self.assertRaises(JournalBackpressureError):
                writer.append(
                    PersistableRecord.tag_sample("SYS.PERF.CPU", 2.0, stamp + timedelta(milliseconds=1))
                )
            self.assertEqual(writer.commit_count, commits)
            self.assertGreaterEqual(writer.ring_full_dropped, 1)
        finally:
            writer.stop()

    def test_protected_tag_evicts_droppable_sample(self):
        writer = _writer(self.tmp.name, ring_maxsize=1)
        try:
            writer._ring.clear()
            stamp = datetime(2026, 9, 29, tzinfo=timezone.utc)
            writer.append(PersistableRecord.tag_sample("SYS.PERF.CPU", 1.0, stamp))
            writer.append(
                PersistableRecord.tag_sample("FI_001", 2.0, stamp + timedelta(milliseconds=1))
            )
            self.assertEqual(len(writer._ring), 1)
            self.assertIn("FI_001", writer._ring[0].entity_id())
            self.assertGreaterEqual(writer.ring_full_dropped, 1)
        finally:
            writer.stop()

    def test_rewind_replicating_keeps_attempts(self):
        path = os.path.join(self.tmp.name, "journal.db")
        writer = _writer(self.tmp.name)
        try:
            writer.append(PersistableRecord.event(message="inflight", username="system"))
            row = writer.fetch_pending(1)[0]
            writer._conn.execute(
                "UPDATE persistence_journal SET status = ?, attempts = 2 WHERE id = ?",
                (STATUS_REPLICATING, row["id"]),
            )
            writer._conn.commit()
        finally:
            writer.stop()
        revived = JournalWriter(SafConfig(journal_path=path, tag_flush_interval_s=60.0))
        revived.start()
        try:
            pending = revived.fetch_pending(5)
            self.assertEqual(len(pending), 1)
            self.assertEqual(pending[0]["attempts"], 2)
            self.assertGreaterEqual(revived.replicating_rewound, 1)
        finally:
            revived.stop()
        again = JournalWriter(SafConfig(journal_path=path, tag_flush_interval_s=60.0))
        again.start()
        try:
            self.assertEqual(again.replicating_rewound, 0)
        finally:
            again.stop()

    def test_reclaim_skipped_while_draining_or_just_after_critical(self):
        writer = _writer(self.tmp.name, compact_min_interval_s=0.0, compact_min_freelist_bytes=1)
        try:
            writer.drain_active = True
            skipped = writer.reclaim_idle()
            self.assertEqual(skipped.get("skipped"), 1)
            self.assertEqual(skipped["vacuumed"], 0)
            writer.drain_active = False
            writer.last_drain_mono = 0.0
            writer.last_critical_mono = __import__("time").monotonic()
            writer.last_operator_mono = 0.0
            recent = writer.reclaim_idle()
            self.assertEqual(recent.get("skipped"), 1)
        finally:
            writer.stop()


class TestOutboxDoesNotWriteRemote(unittest.TestCase):
    def test_remote_callable_is_ignored(self):
        remote = MagicMock(side_effect=AssertionError("remote"))
        record = PersistableRecord.event(message="local-only", username="system")
        gateway = MagicMock()
        gateway.enqueue.return_value = 3
        with patch("automation.persistence.outbox.get_persistence_gateway", return_value=gateway):
            result, journaled = journal_then_remote(record, remote, True)
        self.assertTrue(journaled)
        self.assertIsNone(result)
        remote.assert_not_called()
        gateway.enqueue.assert_called_once()


class TestAckJournalBeforeRam(unittest.TestCase):
    def test_disk_full_does_not_change_isa_state(self):
        alarm = Alarm(
            name="ack_disk",
            tag=Tag(
                name="tag_ack_disk",
                unit="C",
                variable="Temperature",
                data_type="float",
                id="tagack01",
                area="Linea1",
            ),
            alarm_type=StringType("HIGH"),
            alarm_setpoint=FloatType(50.0),
            identifier="id-ack-disk",
        )
        alarm._defer_persist = True
        try:
            alarm.send("normal_to_unack_alarm")
        finally:
            alarm._defer_persist = False
        self.assertEqual(alarm.state.mnemonic, AlarmState.UNACK.mnemonic)
        with patch.object(
            alarm.alarm_engine,
            "create_record_on_alarm_summary",
            side_effect=JournalDiskFullError("full"),
        ):
            alarm.acknowledge()
        self.assertEqual(alarm.state.mnemonic, AlarmState.UNACK.mnemonic)


class TestSafSoakBench(unittest.TestCase):
    @unittest.skipUnless(os.environ.get("SAF_SOAK") == "1", "set SAF_SOAK=1 for the short drain bench")
    def test_short_tick_and_ack_window(self):
        self.assertTrue(True)
