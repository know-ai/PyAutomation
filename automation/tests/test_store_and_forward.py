# -*- coding: utf-8 -*-
"""Phoenix Directive — Store-and-Forward chaos and unit suite (T-01..T-08)."""
from __future__ import annotations

import os
import tempfile
import time
import unittest
from datetime import datetime, timezone
from unittest.mock import MagicMock

from ..persistence import reset_persistence_gateway
from ..persistence.config import SafConfig
from ..persistence.contracts import NullRemoteDB
from ..persistence.exceptions import JournalBackpressureError, JournalDiskFullError
from ..persistence.journal import JournalWriter, STATUS_PENDING, STATUS_SENT
from ..persistence.orchestrator import PersistenceOrchestrator
from ..persistence.records import DOMAIN, PersistableRecord
from ..persistence.replicator import CircuitBreaker, RateLimiter, RemoteReplicator


class FakeRemote:
    def __init__(self, fail_times: int = 0):
        self.fail_times = fail_times
        self.calls = 0
        self.written = []
        self.reachable = True
        self._seen = set()

    def is_reachable(self) -> bool:
        return self.reachable

    def write_batch(self, domain, payloads):
        self.calls += 1
        if self.fail_times > 0:
            self.fail_times -= 1
            raise RuntimeError("remote historian down")
        accepted = 0
        for item in payloads:
            payload = dict(item)
            key = payload.get("sample_uuid") or payload.get("idempotency_key") or (domain, str(payload))
            if key in self._seen:
                accepted += 1
                continue
            self._seen.add(key)
            self.written.append((domain, payload))
            accepted += 1
        return accepted

    def batch_insert_with_dedupe(self, payloads):
        return self.write_batch(DOMAIN.TAG, payloads)


class TestSafJournal(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = os.path.join(self.tmp.name, "journal.db")
        self.config = SafConfig(
            journal_path=self.path,
            ring_maxsize=8,
            tag_batch_size=4,
            tag_flush_interval_s=0.005,
            replicate_batch_size=100,
            replicate_rate_per_s=10_000,
            max_disk_bytes=5 * 1024 * 1024,
            gc_sent_after_s=0.0,
        )
        self.journal = JournalWriter(self.config)
        self.journal.start()

    def tearDown(self):
        self.journal.stop()
        self.tmp.cleanup()
        reset_persistence_gateway()

    def test_t02_restart_replays_pending(self):
        record = PersistableRecord.event(message="boom", username="system")
        row_id = self.journal.append(record)
        self.journal.flush_sync()
        self.assertGreater(row_id, 0)
        self.journal.stop()
        revived = JournalWriter(self.config)
        revived.start()
        pending = revived.fetch_pending(10)
        revived.stop()
        self.assertEqual(len(pending), 1)
        self.assertEqual(pending[0]["idempotency_key"], record.idempotency_key())

    def test_c02_failed_replicate_keeps_pending(self):
        self.journal.append(PersistableRecord.event(message="keep", username="system"))
        self.journal.flush_sync()
        replicator = RemoteReplicator(self.journal, FakeRemote(fail_times=3), self.config)
        self.assertEqual(replicator.replicate_once(), 0)
        pending = self.journal.fetch_pending(10)
        self.assertEqual(len(pending), 1)
        self.assertEqual(pending[0]["status"] if "status" in pending[0] else STATUS_PENDING, STATUS_PENDING)

    def test_ack_marks_sent_and_gc(self):
        self.journal.append(PersistableRecord.event(message="ok", username="system"))
        self.journal.flush_sync()
        replicator = RemoteReplicator(self.journal, FakeRemote(), self.config)
        self.assertEqual(replicator.replicate_once(), 1)
        self.assertEqual(self.journal.fetch_pending(10), [])

    def test_idempotent_duplicate_key(self):
        rec = PersistableRecord.event(message="dup", username="system", timestamp=datetime(2026, 1, 1, tzinfo=timezone.utc))
        first = self.journal.append(rec)
        second = self.journal.append(rec)
        self.assertEqual(first, second)
        self.journal.flush_sync()
        self.assertEqual(len(self.journal.fetch_pending(10)), 1)

    def test_t07_ring_backpressure(self):
        tight = SafConfig(
            journal_path=self.path,
            ring_maxsize=2,
            tag_batch_size=50,
            tag_flush_interval_s=60.0,
        )
        writer = JournalWriter(tight)
        writer.start()
        try:
            writer._stop.set()
            if writer._flusher:
                writer._flusher.join(timeout=1)
            writer._ring.clear()
            writer.append(PersistableRecord.tag_sample("t", 1.0, datetime.now(timezone.utc)))
            writer.append(PersistableRecord.tag_sample("t", 2.0, datetime.now(timezone.utc)))
            with self.assertRaises(JournalBackpressureError):
                writer.append(PersistableRecord.tag_sample("t", 3.0, datetime.now(timezone.utc)))
            self.assertGreaterEqual(writer.dropped_full, 1)
        finally:
            writer._stop.set()
            writer.stop()

    def test_evict_never_deletes_pending(self):
        self.journal.append(PersistableRecord.event(message="pending-sacred", username="system"))
        self.journal.flush_sync()
        deleted = self.journal.evict_sent_oldest(100)
        self.assertEqual(deleted, 0)
        self.assertEqual(len(self.journal.fetch_pending(10)), 1)

    def test_health_snapshot_keys(self):
        orch = PersistenceOrchestrator(config=self.config, remote=NullRemoteDB())
        snap = orch.snapshot()
        for key in ("SAF_QUEUE_DEPTH", "SAF_REPLICATION_LAG", "SAF_DROPPED_FULL"):
            self.assertIn(key, snap)
        orch.close()


class TestSafReplicatorControls(unittest.TestCase):
    def test_rate_limiter(self):
        limiter = RateLimiter(rate_per_s=5)
        self.assertEqual(limiter.take(3), 3)
        self.assertEqual(limiter.take(10), 2)
        self.assertEqual(limiter.take(1), 0)

    def test_circuit_opens(self):
        breaker = CircuitBreaker(fail_threshold=2, open_s=60)
        breaker.failure()
        self.assertTrue(breaker.allow())
        breaker.failure()
        self.assertFalse(breaker.allow())

    def test_null_remote_liskov(self):
        remote = NullRemoteDB()
        self.assertFalse(remote.is_reachable())
        with self.assertRaises(RuntimeError):
            remote.write_batch(DOMAIN.TAG, [{"tag": "x"}])
        with self.assertRaises(RuntimeError):
            remote.batch_insert_with_dedupe([{"tag": "x"}])


class TestSafOrchestrator(unittest.TestCase):
    def setUp(self):
        reset_persistence_gateway()
        self.tmp = tempfile.TemporaryDirectory()
        self.config = SafConfig(
            journal_path=os.path.join(self.tmp.name, "journal.db"),
            tag_flush_interval_s=0.005,
        )

    def tearDown(self):
        reset_persistence_gateway()
        self.tmp.cleanup()

    def test_tags_alarms_events_logs_share_outbox(self):
        remote = FakeRemote()
        orch = PersistenceOrchestrator(config=self.config, remote=remote)
        orch.enqueue(PersistableRecord.tag_sample("flow", 1.23, datetime.now(timezone.utc)))
        orch.enqueue(PersistableRecord.event(message="evt", username="system"))
        orch.enqueue(PersistableRecord.alarm_create(name="A1", state="Unacknowledged", timestamp=datetime.now(timezone.utc)))
        orch.enqueue(PersistableRecord.log(message="log", username="system"))
        orch.flush_sync()
        self.assertGreaterEqual(orch.pending_count(), 4)
        replicated = orch.replicate_once()
        self.assertGreaterEqual(replicated, 4)
        self.assertEqual(orch.pending_count(), 0)
        domains = {item[0] for item in remote.written}
        self.assertEqual(
            domains,
            {DOMAIN.TAG, DOMAIN.EVENT, DOMAIN.ALARM_SUMMARY, DOMAIN.LOG},
        )
        orch.close()


class TestIdempotentBatchInserter(unittest.TestCase):
    def test_on_conflict_does_not_duplicate(self):
        from peewee import BigIntegerField, CharField, FloatField, IntegerField, Model, SqliteDatabase

        from ..persistence.idempotent_insert import IdempotentBatchInserter

        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        db = SqliteDatabase(os.path.join(tmp.name, "remote.db"))

        class RemoteTagValue(Model):
            tag_id = IntegerField()
            timestamp = BigIntegerField()
            value = FloatField()
            sample_uuid = CharField(unique=True, null=True)

            class Meta:
                database = db
                indexes = ((("tag_id", "timestamp"), True),)

        db.connect()
        db.create_tables([RemoteTagValue])
        inserter = IdempotentBatchInserter(model=RemoteTagValue)
        row = {"tag_id": 7, "timestamp": 1_700_000_000_000_000, "value": 42.0, "sample_uuid": "tag:P:1"}
        self.assertEqual(inserter.insert_tag_values([row]), 1)
        self.assertEqual(inserter.insert_tag_values([row]), 1)
        self.assertEqual(inserter.insert_tag_values([row]), 1)
        self.assertEqual(RemoteTagValue.select().count(), 1)
        db.close()

    def test_long_tag_sample_uuid_fits_varchar64(self):
        from ..persistence.records import SAMPLE_UUID_MAX_LEN, canonical_sample_uuid

        ts = datetime(2026, 8, 13, 14, 19, 2, 123456, tzinfo=timezone.utc)
        record = PersistableRecord.tag_sample(
            "Observer.leak_location_longitude",
            1.0,
            ts,
        )
        raw = f"tag:{record.entity}:{record.payload()['timestamp']}"
        self.assertGreater(len(raw), SAMPLE_UUID_MAX_LEN)
        sample_uuid = record.payload()["sample_uuid"]
        self.assertEqual(sample_uuid, canonical_sample_uuid(raw))
        self.assertLessEqual(len(sample_uuid), SAMPLE_UUID_MAX_LEN)
        self.assertEqual(len(sample_uuid), 64)


class TestTagValuePayloadMapper(unittest.TestCase):
    def test_canonical_journal_payload_uses_value_not_val(self):
        from ..persistence.remote import extract_tag_timestamp, extract_tag_value

        payload = PersistableRecord.tag_sample(
            "FI_01",
            23.5,
            datetime(2026, 8, 13, 14, 19, 2, 123456, tzinfo=timezone.utc),
        ).payload()
        self.assertEqual(payload["value"], 23.5)
        self.assertNotIn("val", payload)
        self.assertNotIn("v", payload)
        self.assertEqual(extract_tag_value(payload), 23.5)
        self.assertIsInstance(extract_tag_timestamp(payload), datetime)

    def test_alias_keys_and_quantity_are_coerced(self):
        from ..persistence.remote import coerce_tag_value, extract_tag_value

        class Quantity:
            value = 11.0

        self.assertEqual(extract_tag_value({"val": 7.1}), 7.1)
        self.assertEqual(coerce_tag_value(Quantity()), 11.0)
        self.assertIsNone(extract_tag_value({"value": None}))
        self.assertIsNone(extract_tag_value({"value": "not-a-number"}))

    def test_mapper_skips_null_value_and_maps_numeric(self):
        from ..persistence.remote import TagValuePayloadMapper

        class FakeTag:
            name = "FI_01"
            display_unit = type("U", (), {"id": 1})()
            unit = type("U", (), {"id": 1})()

        mapper = TagValuePayloadMapper(
            resolve_tag=lambda _name: FakeTag(),
            resolve_unit=lambda tag: tag.unit,
        )
        skipped = mapper.to_rows(
            [{"tag": "FI_01", "value": None, "timestamp": "2026-08-13T14:19:02+00:00"}]
        )
        self.assertEqual(skipped, [])
        rows = mapper.to_rows(
            [{
                "tag": "FI_01",
                "value": 23.5,
                "timestamp": "2026-08-13T14:19:02.123456+00:00",
                "sample_uuid": "short-key",
            }]
        )
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["value"], 23.5)
        self.assertEqual(rows[0]["timestamp"].tzinfo is not None, True)


class TestReplicatorDomainIsolation(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = os.path.join(self.tmp.name, "journal.db")
        self.config = SafConfig(
            journal_path=self.path,
            tag_flush_interval_s=0.005,
            replicate_batch_size=100,
            replicate_rate_per_s=10_000,
            gc_sent_after_s=3600.0,
        )
        self.journal = JournalWriter(self.config)
        self.journal.start()

    def tearDown(self):
        self.journal.stop()
        self.tmp.cleanup()
        reset_persistence_gateway()

    def test_event_zero_rows_does_not_block_tags(self):
        class EventStarvedRemote(FakeRemote):
            def write_batch(self, domain, payloads):
                if domain == DOMAIN.EVENT:
                    return 0
                return super().write_batch(domain, payloads)

        self.journal.append(PersistableRecord.event(message="already-there", username="system"))
        self.journal.append(PersistableRecord.tag_sample("FI_01", 1.0, datetime.now(timezone.utc)))
        self.journal.flush_sync()
        remote = EventStarvedRemote()
        replicator = RemoteReplicator(self.journal, remote, self.config)
        replicated = replicator.replicate_once()
        self.assertEqual(replicated, 1)
        pending = self.journal.fetch_pending(10)
        self.assertEqual(len(pending), 1)
        self.assertEqual(pending[0]["domain"], DOMAIN.EVENT)
        self.assertEqual({item[0] for item in remote.written}, {DOMAIN.TAG})


class TestT01Apocalypse(unittest.TestCase):
    """Baptism of fire. Scale with SAF_SOAK_SECONDS / TAGS / HZ (plant: 1800 / 1000 / 100)."""

    def test_t01_kill9_replay_exact_once(self):
        import signal
        import subprocess
        import sys

        duration = float(os.environ.get("SAF_SOAK_SECONDS", "2"))
        n_tags = int(os.environ.get("SAF_SOAK_TAGS", "1000"))
        hz = float(os.environ.get("SAF_SOAK_HZ", "100"))
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        journal_path = os.path.join(tmp.name, "journal.db")
        count_path = os.path.join(tmp.name, "generated.txt")
        repo = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
        child = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "automation.persistence.soak_producer",
                journal_path,
                count_path,
                str(duration),
                str(n_tags),
                str(hz),
            ],
            cwd=repo,
        )
        time.sleep(max(0.4, duration / 2.0))
        child.send_signal(signal.SIGKILL)
        child.wait(timeout=10)

        generated = 0
        if os.path.exists(count_path):
            with open(count_path, encoding="utf-8") as handle:
                generated = int(handle.read() or "0")

        config = SafConfig(
            journal_path=journal_path,
            replicate_batch_size=20_000,
            replicate_rate_per_s=2_000_000,
            gc_sent_after_s=86_400,
            tag_flush_interval_s=0.005,
        )
        journal = JournalWriter(config)
        journal.start()
        journal.flush_sync()
        durable = journal.pending_count()
        remote = FakeRemote()
        replicator = RemoteReplicator(journal, remote, config)
        total = 0
        idle = 0
        while idle < 3:
            flushed = replicator.flush()
            total += flushed
            if flushed == 0:
                idle += 1
            else:
                idle = 0
        first_remote = len(remote.written)
        replicator.flush()
        replicator.flush()
        second_remote = len(remote.written)
        pending_after = journal.pending_count()
        ring_lag = max(0, generated - durable)
        achieved_hz = (generated / n_tags / max(duration / 2.0, 0.001)) if n_tags else 0.0
        report = os.path.join(repo, "audits", "T01_SOAK_LAST_RUN.md")
        os.makedirs(os.path.dirname(report), exist_ok=True)
        with open(report, "w", encoding="utf-8") as handle:
            handle.write(
                "\n".join(
                    [
                        "# T-01 Soak — last run",
                        "",
                        f"- tags={n_tags} hz={hz} duration_s={duration} kill_at_s={duration/2:.3f}",
                        f"- achieved_tick_hz={achieved_hz:.2f}",
                        f"- generated_fsync={generated}",
                        f"- journal_durable={durable}",
                        f"- ring_lag_samples={ring_lag}",
                        f"- replicated={total}",
                        f"- remote_rows_first_pass={first_remote}",
                        f"- remote_rows_after_retry={second_remote}",
                        f"- pending_after={pending_after}",
                        f"- exact_once={first_remote == second_remote}",
                        f"- remote_equals_durable={first_remote == durable}",
                        "",
                        "Ring lag is the hardware window of the in-memory flusher (≤ tag_flush_interval_s).",
                        "Those samples never reached WAL before SIGKILL; they are the only acceptable loss.",
                        "",
                    ]
                )
            )
        journal.stop()
        self.assertGreater(generated, 0)
        self.assertGreater(durable, 0)
        self.assertEqual(pending_after, 0)
        self.assertEqual(first_remote, durable)
        self.assertEqual(second_remote, first_remote)
        self.assertGreaterEqual(ring_lag, 0)
