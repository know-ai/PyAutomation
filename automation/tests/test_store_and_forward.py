# -*- coding: utf-8 -*-
"""Phoenix Directive — Store-and-Forward chaos and unit suite (T-01..T-08)."""
from __future__ import annotations

import os
import tempfile
import time
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

from ..persistence import reset_persistence_gateway
from ..persistence.config import SafConfig
from ..persistence.contracts import NullRemoteDB
from ..persistence.exceptions import JournalBackpressureError, JournalDiskFullError
from ..persistence.journal import JournalWriter, STATUS_DEAD_LETTER, STATUS_PENDING
from ..persistence.cycle_dedupe import CycleSampleCache
from ..persistence.orchestrator import PersistenceOrchestrator
from ..persistence.records import DOMAIN, PersistableRecord
from ..persistence.replicator import CircuitBreaker, RateLimiter, RemoteReplicator


def setUpModule():
    os.environ.setdefault("AUTOMATION_MULTI_EDGE_ENABLED", "false")


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
        outcomes = self.write_batch_outcomes(domain, payloads)
        if self.fail_times > 0 and not any(outcomes):
            raise RuntimeError("remote historian down")
        return sum(outcomes)

    def write_batch_outcomes(self, domain, payloads):
        self.calls += 1
        if self.fail_times > 0:
            self.fail_times -= 1
            raise RuntimeError("remote historian down")
        outcomes = []
        for item in payloads:
            payload = dict(item)
            key = payload.get("sample_uuid") or payload.get("idempotency_key") or (domain, str(payload))
            if key in self._seen:
                outcomes.append(True)
                continue
            self._seen.add(key)
            self.written.append((domain, payload))
            outcomes.append(True)
        return outcomes

    def batch_insert_with_dedupe(self, payloads):
        return self.write_batch(DOMAIN.TAG, payloads)


def _sql_drainable(journal: JournalWriter) -> int:
    with journal._lock:
        journal._ensure_open_locked()
        return journal._count_durable_pending_locked() + len(journal._ring)


class _BanCountConn:
    def __init__(self, conn):
        object.__setattr__(self, "_conn", conn)

    def execute(self, sql, parameters=()):
        if "COUNT(" in str(sql).upper():
            raise AssertionError(f"COUNT on SAF hot path: {sql}")
        return self._conn.execute(sql, parameters)

    def __getattr__(self, name):
        return getattr(self._conn, name)


def _ban_sqlite_count(journal: JournalWriter):
    original = journal._conn
    journal._conn = _BanCountConn(original)
    return original


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

    def test_append_committed_many_one_commit(self):
        records = [
            PersistableRecord.alarm_update(
                name=f"A{i}",
                state="Acknowledged",
                ack_timestamp=datetime.now(timezone.utc),
            )
            for i in range(10)
        ]
        ids = self.journal.append_committed_many(records)
        self.assertEqual(len(ids), 10)
        self.assertEqual(len(self.journal.fetch_pending(20)), 10)
        self.assertTrue(all(jid > 0 for jid in ids))

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

    def test_t07_ring_full_force_flush_drains(self):
        tight = SafConfig(
            journal_path=self.path,
            ring_maxsize=2,
            tag_batch_size=50,
            tag_flush_interval_s=60.0,
        )
        writer = JournalWriter(tight)
        writer.start()
        kicks = []
        writer.set_force_flush_hook(lambda: kicks.append(1))
        try:
            writer._stop.set()
            writer._ring_event.set()
            if writer._flusher:
                writer._flusher.join(timeout=1)
            writer._ring.clear()
            t0 = datetime.now(timezone.utc)
            writer.append(PersistableRecord.tag_sample("t", 1.0, t0))
            writer.append(PersistableRecord.tag_sample("t", 2.0, t0 + timedelta(milliseconds=2)))
            writer.append(PersistableRecord.tag_sample("t", 3.0, t0 + timedelta(milliseconds=4)))
            self.assertEqual(len(kicks), 1)
            self.assertLessEqual(len(writer._ring), 2)
            pending = writer.fetch_pending(10)
            self.assertGreaterEqual(len(pending) + len(writer._ring), 3)
        finally:
            writer._stop.set()
            writer.stop()

    def test_t07_ring_backpressure_when_drain_cannot_free_space(self):
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
            writer._ring_event.set()
            if writer._flusher:
                writer._flusher.join(timeout=1)
            writer._ring.clear()
            original = writer._drain_ring_locked
            writer._drain_ring_locked = lambda: None
            writer.append(PersistableRecord.tag_sample("t", 1.0, datetime.now(timezone.utc)))
            writer.append(PersistableRecord.tag_sample("t", 2.0, datetime.now(timezone.utc)))
            with self.assertRaises(JournalBackpressureError):
                writer.append(PersistableRecord.tag_sample("t", 3.0, datetime.now(timezone.utc)))
            self.assertGreaterEqual(writer.dropped_full, 1)
            writer._drain_ring_locked = original
        finally:
            writer._stop.set()
            writer.stop()

    def test_evict_never_deletes_pending(self):
        self.journal.append(PersistableRecord.event(message="pending-sacred", username="system"))
        self.journal.flush_sync()
        deleted = self.journal.evict_sent_oldest(100)
        self.assertEqual(deleted, 0)
        self.assertEqual(len(self.journal.fetch_pending(10)), 1)

    def test_journal_pragmas_durable_and_cached(self):
        with self.journal._lock:
            mode = str(self.journal._conn.execute("PRAGMA journal_mode").fetchone()[0]).upper()
            sync = int(self.journal._conn.execute("PRAGMA synchronous").fetchone()[0])
            temp = int(self.journal._conn.execute("PRAGMA temp_store").fetchone()[0])
            cache = int(self.journal._conn.execute("PRAGMA cache_size").fetchone()[0])
            mmap = int(self.journal._conn.execute("PRAGMA mmap_size").fetchone()[0])
        self.assertEqual(mode, "WAL")
        self.assertEqual(sync, 2)
        self.assertEqual(temp, 2)
        self.assertEqual(cache, -64000)
        self.assertGreaterEqual(mmap, 0)
        self.assertGreaterEqual(self.journal._durability_fd, 0)

    def test_disk_full_error_when_pending_cannot_evict(self):
        """WD-06 / G-DISK-03: JournalDiskFullError when SENT cannot free space."""
        with patch.object(
            self.journal, "_measure_disk_bytes", return_value=self.config.max_disk_bytes
        ):
            with self.journal._lock:
                self.journal._disk_bytes_cache = self.config.max_disk_bytes
                self.journal._disk_bytes_mono = time.monotonic()
                with self.assertRaises(JournalDiskFullError):
                    self.journal._guard_disk_locked()
                self.assertTrue(self.journal.backpressure)
                self.assertGreaterEqual(self.journal.dropped_full, 1)

    def test_disk_full_error_on_append_when_cap_exceeded(self):
        path = os.path.join(self.tmp.name, "tiny-journal.db")
        config = SafConfig(
            journal_path=path,
            max_disk_bytes=32 * 1024,
            max_pending_rows=1_000_000,
            ring_maxsize=8,
            tag_flush_interval_s=60.0,
            gc_batch=10,
            gc_sent_after_s=86_400,
        )
        writer = JournalWriter(config)
        writer.start()
        raised = False
        ts = datetime(2026, 8, 28, tzinfo=timezone.utc)
        try:
            for i in range(400):
                try:
                    writer.append(
                        PersistableRecord.event(
                            message="payload-" + ("x" * 256),
                            username="system",
                            timestamp=ts + timedelta(milliseconds=i),
                        )
                    )
                except JournalDiskFullError:
                    raised = True
                    break
            self.assertTrue(raised, "expected JournalDiskFullError before 400 pending events")
        finally:
            writer.stop()

    def test_health_snapshot_keys(self):
        orch = PersistenceOrchestrator(config=self.config, remote=NullRemoteDB())
        snap = orch.snapshot()
        for key in ("SAF_QUEUE_DEPTH", "SAF_REPLICATION_LAG", "SAF_DROPPED_FULL", "SAF_CYCLE_DUPES_DROPPED"):
            self.assertIn(key, snap)
        orch.close()

    def test_default_ring_is_100k(self):
        self.assertEqual(SafConfig().ring_maxsize, 100_000)

    def test_fetch_pending_is_fifo_by_id(self):
        self.journal.append(PersistableRecord.event(message="later-event", username="system"))
        self.journal.append(
            PersistableRecord.tag_sample("FI_01", 1.0, datetime.now(timezone.utc))
        )
        self.journal.flush_sync()
        pending = self.journal.fetch_pending(10)
        domains = [row["domain"] for row in pending]
        self.assertEqual(domains[0], "event")
        self.assertEqual(domains[1], "tag")

    def test_dead_letter_escapes_poison_and_leaves_pending(self):
        self.journal.append(PersistableRecord.event(message="poison", username="system"))
        self.journal.flush_sync()
        rows = self.journal.fetch_pending(10)
        self.assertEqual(len(rows), 1)
        jid = rows[0]["id"]
        for _ in range(int(self.config.dead_letter_attempts)):
            self.journal.mark_pending([jid], error="remote rejected")
        with self.journal._lock:
            row = self.journal._conn.execute(
                "SELECT status FROM persistence_journal WHERE id = ?",
                (jid,),
            ).fetchone()
        self.assertEqual(row["status"], STATUS_DEAD_LETTER)
        self.assertEqual(self.journal.fetch_pending(10), [])
        self.assertGreaterEqual(self.journal.deadletter_count, 1)
        self.assertEqual(self.journal.pending_count(), 0)

    def test_pending_cache_matches_sql_across_mutations(self):
        event = PersistableRecord.event(
            message="cache-inv",
            username="system",
            timestamp=datetime(2026, 1, 2, tzinfo=timezone.utc),
        )
        event_id = self.journal.append(event)
        self.assertEqual(self.journal.pending_count(), _sql_drainable(self.journal))
        self.assertEqual(self.journal.pending_count(), 1)

        dupe = self.journal.append(event)
        self.assertEqual(dupe, event_id)
        self.assertEqual(self.journal.pending_count(), 1)
        self.assertEqual(self.journal.pending_count(), _sql_drainable(self.journal))

        t0 = datetime(2026, 1, 2, 0, 0, 1, tzinfo=timezone.utc)
        self.journal.append(PersistableRecord.tag_sample("flow.cache", 1.0, t0))
        self.assertEqual(self.journal.pending_count(), _sql_drainable(self.journal))
        self.journal.flush_sync()
        self.assertEqual(self.journal.pending_count(), _sql_drainable(self.journal))
        self.assertEqual(self.journal.pending_count(), 2)

        self.journal.mark_replicating([event_id])
        self.assertEqual(self.journal.pending_count(), 2)
        self.journal.mark_sent([event_id])
        self.assertEqual(self.journal.pending_count(), 1)
        self.journal.mark_sent([event_id])
        self.assertEqual(self.journal.pending_count(), 1)
        self.assertEqual(self.journal.pending_count(), _sql_drainable(self.journal))

        poison = PersistableRecord.event(message="dlq-cache", username="system")
        poison_id = self.journal.append(poison)
        for _ in range(int(self.config.dead_letter_attempts)):
            self.journal.mark_pending([poison_id], error="rejected")
        self.assertEqual(self.journal.pending_count(), 1)
        self.assertEqual(self.journal.pending_count(), _sql_drainable(self.journal))

        dropped = self.journal.drop_unsent(confirm=True)
        self.assertGreaterEqual(dropped, 1)
        self.assertEqual(self.journal.pending_count(), 0)
        self.assertEqual(self.journal.pending_count(), _sql_drainable(self.journal))

    def test_tag_enqueue_and_pending_count_skip_sqlite_count(self):
        self.journal.append(
            PersistableRecord.event(message="seed", username="system")
        )
        self.journal.flush_sync()
        original = _ban_sqlite_count(self.journal)
        try:
            self.journal.append(
                PersistableRecord.tag_sample(
                    "flow.hot",
                    2.0,
                    datetime(2026, 1, 3, tzinfo=timezone.utc),
                )
            )
            self.assertGreaterEqual(self.journal.pending_count(), 2)
        finally:
            self.journal._conn = original

    def test_pending_counter_hydrates_on_reopen(self):
        path = os.path.join(self.tmp.name, "reopen.db")
        config = SafConfig(
            journal_path=path,
            tag_flush_interval_s=0.05,
            ring_maxsize=32,
        )
        first = JournalWriter(config)
        first.start()
        try:
            first.append(PersistableRecord.event(message="persist-me", username="system"))
            first.flush_sync()
            self.assertEqual(first.pending_count(), 1)
        finally:
            first.stop()
        second = JournalWriter(config)
        second.start()
        try:
            self.assertEqual(second.pending_count(), 1)
            self.assertEqual(second.pending_count(), _sql_drainable(second))
        finally:
            second.stop()

    def test_flush_batch_does_not_stat_disk_per_insert(self):
        path = os.path.join(self.tmp.name, "disk-cache.db")
        config = SafConfig(
            journal_path=path,
            ring_maxsize=256,
            tag_batch_size=64,
            tag_flush_interval_s=60.0,
            max_disk_bytes=5 * 1024 * 1024,
        )
        writer = JournalWriter(config)
        writer.start()
        writer._stop.set()
        writer._ring_event.set()
        if writer._flusher:
            writer._flusher.join(timeout=1)
        measured = []
        real_getsize = os.path.getsize

        def counting_getsize(path_name):
            measured.append(path_name)
            return real_getsize(path_name)

        try:
            with patch("automation.persistence.journal.os.path.getsize", counting_getsize):
                t0 = datetime(2026, 1, 4, tzinfo=timezone.utc)
                for i in range(24):
                    writer.append(
                        PersistableRecord.tag_sample(
                            "flow.disk",
                            float(i),
                            t0 + timedelta(milliseconds=i),
                        )
                    )
                writer._disk_bytes_mono = 0.0
                writer.flush_sync()
            self.assertGreater(len(measured), 0)
            self.assertLess(len(measured), 12)
        finally:
            writer.stop()

    def test_tag_enqueue_stays_o1_with_fat_pending_journal(self):
        seed_ts = datetime(2026, 1, 5, tzinfo=timezone.utc)
        for i in range(800):
            self.journal.append(
                PersistableRecord.event(
                    message=f"fat-{i}",
                    username="system",
                    timestamp=seed_ts + timedelta(milliseconds=i),
                )
            )
        original = _ban_sqlite_count(self.journal)
        try:
            started = time.perf_counter()
            for i in range(150):
                self.journal.append(
                    PersistableRecord.tag_sample(
                        "flow.fat",
                        float(i),
                        seed_ts + timedelta(seconds=1, milliseconds=i),
                    )
                )
            elapsed = time.perf_counter() - started
        finally:
            self.journal._conn = original
        self.assertLess(elapsed, 0.5)
        self.assertEqual(self.journal.pending_count(), _sql_drainable(self.journal))

    def test_reclaim_idle_truncates_wal_and_compacts_freelist(self):
        path = os.path.join(self.tmp.name, "compact.db")
        config = SafConfig(
            journal_path=path,
            gc_sent_after_s=0.0,
            gc_batch=10_000,
            compact_min_freelist_bytes=1,
            compact_min_interval_s=0.0,
            compact_max_pending=256,
            tag_flush_interval_s=60.0,
            ring_maxsize=256,
        )
        writer = JournalWriter(config)
        writer.start()
        try:
            ts = datetime(2026, 1, 6, tzinfo=timezone.utc)
            ids = []
            for i in range(200):
                ids.append(
                    writer.append(
                        PersistableRecord.event(
                            message=f"compact-{i}",
                            username="system",
                            description="x" * 512,
                            timestamp=ts + timedelta(milliseconds=i),
                        )
                    )
                )
            writer.flush_sync()
            writer.mark_sent(ids)
            writer.gc_sent(0.0, 10_000)
            before = writer.disk_bytes()
            result = writer.reclaim_idle()
            after = writer.disk_bytes()
            self.assertEqual(result["vacuumed"], 1)
            self.assertLess(after, before)
            self.assertEqual(writer.pending_count(), 0)
            wal = path + "-wal"
            if os.path.exists(wal):
                self.assertLess(os.path.getsize(wal), 1024 * 1024)
        finally:
            writer.stop()

    def test_reclaim_idle_skips_vacuum_during_catchup(self):
        path = os.path.join(self.tmp.name, "no-compact.db")
        config = SafConfig(
            journal_path=path,
            gc_sent_after_s=0.0,
            compact_min_freelist_bytes=1,
            compact_min_interval_s=0.0,
            compact_max_pending=0,
            tag_flush_interval_s=60.0,
        )
        writer = JournalWriter(config)
        writer.start()
        try:
            writer.append(PersistableRecord.event(message="keep-pending", username="system"))
            writer.flush_sync()
            result = writer.reclaim_idle()
            self.assertEqual(result["vacuumed"], 0)
            self.assertEqual(writer.pending_count(), 1)
        finally:
            writer.stop()


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

    def test_catchup_drains_more_than_one_batch_per_period(self):
        remote = FakeRemote()
        config = SafConfig(
            journal_path=os.path.join(self.tmp.name, "catchup.db"),
            replicate_batch_size=100,
            replicate_rate_per_s=10_000,
            catchup_budget_s=0.5,
            tag_flush_interval_s=0.001,
        )
        orch = PersistenceOrchestrator(config=config, remote=remote)
        for i in range(350):
            orch.enqueue(
                PersistableRecord.tag_sample(
                    f"flow{i}",
                    float(i),
                    datetime(2026, 8, 13, 16, 1, 0, i * 1000, tzinfo=timezone.utc),
                )
            )
        orch.flush_sync()
        pending = orch.pending_count()
        self.assertGreaterEqual(pending, 300)
        started = time.monotonic()
        written = orch.replicate_catchup()
        elapsed = time.monotonic() - started
        self.assertGreater(written, 100)
        self.assertLess(elapsed, 2.0)
        orch.close()

    def test_shed_drops_tags_keeps_events(self):
        remote = FakeRemote()
        config = SafConfig(
            journal_path=os.path.join(self.tmp.name, "shed.db"),
            shed_high=3,
            shed_low=1,
            tag_flush_interval_s=0.001,
        )
        orch = PersistenceOrchestrator(config=config, remote=remote)
        for i in range(3):
            orch.enqueue(
                PersistableRecord.tag_sample(
                    f"flow{i}",
                    float(i),
                    datetime(2026, 8, 13, 16, 2, i, tzinfo=timezone.utc),
                )
            )
        orch.flush_sync()
        self.assertGreaterEqual(orch.pending_count(), 3)
        orch.enqueue(
            PersistableRecord.tag_sample("flow99", 99.0, datetime.now(timezone.utc))
        )
        snap = orch.snapshot()
        self.assertTrue(snap["SAF_SHED"])
        self.assertGreaterEqual(int(snap["SAF_SHED_DROPPED"]), 1)
        event_id = orch.enqueue(PersistableRecord.event(message="must-keep", username="system"))
        self.assertGreater(event_id, 0)
        orch.close()

    def test_cycle_dedupe_drops_same_tag_value_timestamp(self):
        orch = PersistenceOrchestrator(config=self.config, remote=FakeRemote())
        ts = datetime(2026, 8, 13, 16, 0, 0, 123456, tzinfo=timezone.utc)
        orch.enqueue(PersistableRecord.tag_sample("PPA.threshold", 91.0, ts))
        dropped = orch.enqueue(PersistableRecord.tag_sample("PPA.threshold", 91.0, ts))
        self.assertEqual(dropped, 0)
        self.assertEqual(orch.cycle_cache.dropped, 1)
        self.assertEqual(orch.pending_count(), 1)
        orch.flush_sync()
        self.assertEqual(orch.pending_count(), 1)
        self.assertEqual(orch.snapshot()["SAF_CYCLE_DUPES_DROPPED"], 1)
        orch.close()

    def test_cycle_dedupe_keeps_value_change_same_cycle(self):
        orch = PersistenceOrchestrator(config=self.config, remote=FakeRemote())
        ts = datetime(2026, 8, 13, 16, 0, 1, tzinfo=timezone.utc)
        orch.enqueue(PersistableRecord.tag_sample("LDS.leak", 0.0, ts))
        orch.enqueue(PersistableRecord.tag_sample("LDS.leak", 1.0, ts))
        self.assertEqual(orch.cycle_cache.dropped, 0)
        orch.close()

    def test_cycle_dedupe_does_not_filter_alarms(self):
        orch = PersistenceOrchestrator(config=self.config, remote=FakeRemote())
        ts = datetime(2026, 8, 13, 16, 0, 2, tzinfo=timezone.utc)
        first = orch.enqueue(
            PersistableRecord.alarm_create(name="A1", state="Unacknowledged", timestamp=ts)
        )
        second = orch.enqueue(
            PersistableRecord.alarm_create(name="A1", state="Unacknowledged", timestamp=ts)
        )
        self.assertGreater(first, 0)
        self.assertGreater(second, 0)
        orch.close()


class TestAtomicCycleTimestamp(unittest.TestCase):
    def test_stamp_machine_cycle_sets_utc(self):
        from ..workers.state_machine import stamp_machine_cycle

        class FakeMachine:
            pass

        machine = FakeMachine()
        ts = stamp_machine_cycle(machine)
        self.assertEqual(machine.cycle_timestamp, ts)
        self.assertEqual(ts.tzinfo, timezone.utc)
        self.assertEqual(ts.microsecond % 1000, 0)

    def test_cycle_timestamp_wins_over_data_timestamp_and_now(self):
        from ..models import resolve_machine_cycle_timestamp

        class FakeMachine:
            pass

        machine = FakeMachine()
        cycle = datetime(2026, 8, 13, 12, 0, 0, 123456, tzinfo=timezone.utc)
        field = datetime(2026, 8, 13, 12, 0, 1, tzinfo=timezone.utc)
        machine.cycle_timestamp = cycle
        machine.data_timestamp = field
        resolved = resolve_machine_cycle_timestamp(machine)
        self.assertEqual(resolved, datetime(2026, 8, 13, 12, 0, 0, 123000, tzinfo=timezone.utc))

    def test_explicit_timestamp_wins(self):
        from ..models import resolve_machine_cycle_timestamp

        class FakeMachine:
            pass

        machine = FakeMachine()
        machine.cycle_timestamp = datetime(2026, 8, 13, 12, 0, 0, tzinfo=timezone.utc)
        explicit = datetime(2026, 8, 13, 12, 0, 9, 456789, tzinfo=timezone.utc)
        self.assertEqual(
            resolve_machine_cycle_timestamp(machine, timestamp=explicit),
            datetime(2026, 8, 13, 12, 0, 9, 456000, tzinfo=timezone.utc),
        )

    def test_data_timestamp_used_without_cycle_stamp(self):
        from ..models import resolve_machine_cycle_timestamp

        class FakeMachine:
            pass

        machine = FakeMachine()
        field = datetime(2026, 8, 13, 12, 0, 1, 12, tzinfo=timezone.utc)
        machine.data_timestamp = field
        self.assertEqual(
            resolve_machine_cycle_timestamp(machine),
            datetime(2026, 8, 13, 12, 0, 1, 0, tzinfo=timezone.utc),
        )


class TestMillisecondExacto(unittest.TestCase):
    def test_tag_sample_iso_is_millisecond(self):
        ts = datetime(2026, 8, 13, 14, 19, 2, 123456, tzinfo=timezone.utc)
        payload = PersistableRecord.tag_sample("FI_01", 1.0, ts).payload()
        self.assertEqual(payload["timestamp"], "2026-08-13T14:19:02.123+00:00")

    def test_sub_millisecond_rewrites_share_idempotency_key(self):
        a = PersistableRecord.tag_sample(
            "LDS.leak",
            0.0,
            datetime(2026, 8, 13, 12, 0, 0, 74, tzinfo=timezone.utc),
        )
        b = PersistableRecord.tag_sample(
            "LDS.leak",
            0.0,
            datetime(2026, 8, 13, 12, 0, 0, 403, tzinfo=timezone.utc),
        )
        self.assertEqual(a.idempotency_key(), b.idempotency_key())
        self.assertEqual(a.payload()["timestamp"], b.payload()["timestamp"])

    def test_epoch_seconds_accepts_ms_and_us_ticks(self):
        from ..timebase import epoch_seconds_from_db_tick

        us = 1786639193282970
        ms = 1786639193282
        self.assertAlmostEqual(epoch_seconds_from_db_tick(us), us / 1_000_000.0, places=6)
        self.assertAlmostEqual(epoch_seconds_from_db_tick(ms), ms / 1_000.0, places=6)

    def test_tagvalue_field_resolution_is_millis(self):
        from ..dbmodels.tags import TagValue
        from ..timebase import TAGVALUE_TIMESTAMP_RESOLUTION

        self.assertEqual(TAGVALUE_TIMESTAMP_RESOLUTION, 3)
        # Peewee stores constructor resolution=3 as attr resolution=1000 (ms ticks).
        self.assertEqual(TagValue.timestamp.resolution, 1000)
        self.assertEqual(TagValue.timestamp.ticks_to_microsecond, 1000)

    def test_timestamp_where_bound_must_be_datetime_not_ms_int(self):
        """Peewee treats a raw int as seconds and multiplies by resolution."""
        from ..dbmodels.tags import TagValue

        dt = datetime(2026, 8, 13, 17, 24, 0, tzinfo=timezone.utc)
        ms_tick = TagValue.timestamp.db_value(dt)
        self.assertGreater(ms_tick, 1_000_000_000_000)
        self.assertLess(ms_tick, 10_000_000_000_000)
        # Trap that emptied /tags/query_trends after resolution=3:
        self.assertEqual(TagValue.timestamp.db_value(ms_tick), ms_tick * 1000)


class TestCycleSampleCache(unittest.TestCase):
    def test_ttl_releases_stale_entries(self):
        cache = CycleSampleCache(ttl_s=0.01)
        rec = PersistableRecord.tag_sample(
            "FI_01", 1.0, datetime(2026, 8, 13, 16, 0, 3, tzinfo=timezone.utc)
        )
        self.assertFalse(cache.should_drop(rec))
        self.assertTrue(cache.should_drop(rec))
        time.sleep(0.03)
        self.assertFalse(cache.should_drop(rec))

    def test_distinct_tags_same_cycle_are_independent(self):
        cache = CycleSampleCache()
        ts = datetime(2026, 8, 13, 16, 0, 4, tzinfo=timezone.utc)
        a = PersistableRecord.tag_sample("PPA.threshold", 91.0, ts)
        b = PersistableRecord.tag_sample("PPA.leak", 91.0, ts)
        self.assertFalse(cache.should_drop(a))
        self.assertFalse(cache.should_drop(b))
        self.assertTrue(cache.should_drop(a))
        self.assertEqual(cache.dropped, 1)


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
        row = {"tag_id": 7, "timestamp": 1_700_000_000_000, "value": 42.0, "sample_uuid": "tag:P:1"}
        self.assertEqual(inserter.insert_tag_values([row]), 1)
        self.assertEqual(inserter.insert_tag_values([row]), 1)
        self.assertEqual(inserter.insert_tag_values([row]), 1)
        self.assertEqual(RemoteTagValue.select().count(), 1)
        db.close()

    def test_normalize_microseconds_to_millis_collapses_pairs(self):
        from peewee import BigIntegerField, CharField, FloatField, IntegerField, Model, SqliteDatabase

        from ..persistence.idempotent_insert import IdempotentBatchInserter

        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        db = SqliteDatabase(os.path.join(tmp.name, "scale.db"))

        class RemoteTagValue(Model):
            tag_id = IntegerField()
            timestamp = BigIntegerField()
            value = FloatField()
            sample_uuid = CharField(unique=True, null=True)

            class Meta:
                database = db

        db.connect()
        db.create_tables([RemoteTagValue])
        # Legacy µs pair inside the same millisecond → one row after ÷1000
        RemoteTagValue.create(tag_id=1, timestamp=1786639193283422, value=0.0, sample_uuid="a")
        RemoteTagValue.create(tag_id=1, timestamp=1786639193283496, value=0.0, sample_uuid="b")
        inserter = IdempotentBatchInserter(model=RemoteTagValue)
        inserter.ensure_schema(RemoteTagValue)
        rows = list(RemoteTagValue.select().order_by(RemoteTagValue.id))
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].timestamp, 1786639193283)
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
        self.assertEqual(payload["timestamp"], "2026-08-13T14:19:02.123+00:00")
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
        self.assertEqual(rows[0]["timestamp"].microsecond % 1000, 0)
        self.assertEqual(rows[0]["timestamp"].tzinfo is not None, True)

    def test_missing_remote_tag_requests_full_catalog_sync(self):
        from unittest.mock import Mock, patch

        from ..persistence.remote import TagValuePayloadMapper

        worker = Mock()
        mapper = TagValuePayloadMapper(
            resolve_tag=lambda _name: None,
            resolve_unit=lambda _tag: None,
        )
        with patch(
            "automation.catalog.replicator.get_catalog_replicator",
            return_value=worker,
        ):
            rows = mapper.to_rows(
                [{
                    "tag": "missing.FI",
                    "value": 1.0,
                    "timestamp": "2026-08-13T14:19:02+00:00",
                }]
            )
        self.assertEqual(rows, [])
        worker.request_full_sync.assert_called()

    def test_missing_remote_tag_drops_after_three_retries(self):
        from unittest.mock import Mock, patch

        from ..persistence.remote import (
            PeeweeRemoteDB,
            TagValuePayloadMapper,
            reset_missing_tag_tries,
        )

        reset_missing_tag_tries()
        remote = PeeweeRemoteDB(
            tag_mapper=TagValuePayloadMapper(
                resolve_tag=lambda _name: None,
                resolve_unit=lambda _tag: None,
            )
        )
        remote._tag_inserter = Mock()
        payload = {
            "tag": "ghost.FI",
            "value": 1.0,
            "timestamp": "2026-08-13T14:19:02+00:00",
        }
        with patch("automation.catalog.replicator.get_catalog_replicator", return_value=Mock()):
            first = remote.write_batch_outcomes("tag", [payload])
            second = remote.write_batch_outcomes("tag", [payload])
            third = remote.write_batch_outcomes("tag", [payload])
        self.assertEqual(first, [False])
        self.assertEqual(second, [False])
        self.assertEqual(third, [True])
        remote._tag_inserter.insert_tag_values.assert_not_called()
        reset_missing_tag_tries()

    def test_unmappable_timestamp_is_acked_without_retry(self):
        from unittest.mock import Mock
        from types import SimpleNamespace

        from ..persistence.remote import PeeweeRemoteDB, TagValuePayloadMapper

        unit = SimpleNamespace(id=1)
        tag = SimpleNamespace(id=1, display_unit=unit, unit=unit)
        remote = PeeweeRemoteDB(
            tag_mapper=TagValuePayloadMapper(
                resolve_tag=lambda _name: tag,
                resolve_unit=lambda _tag: unit,
            )
        )
        remote._tag_inserter = Mock()
        outcomes = remote.write_batch_outcomes(
            "tag",
            [{"tag": "Supe.Linea2.PI_02", "value": 1.0, "timestamp": None}],
        )
        self.assertEqual(outcomes, [True])
        remote._tag_inserter.insert_tag_values.assert_not_called()


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
        self._scope_patch = patch(
            "automation.persistence.replicator._node_scope",
            return_value=None,
        )
        self._scope_patch.start()

    def tearDown(self):
        self._scope_patch.stop()
        self.journal.stop()
        self.tmp.cleanup()
        reset_persistence_gateway()

    def test_event_zero_rows_does_not_block_tags(self):
        class EventStarvedRemote(FakeRemote):
            def write_batch_outcomes(self, domain, payloads):
                if domain == DOMAIN.EVENT:
                    return [False] * len(payloads)
                return super().write_batch_outcomes(domain, payloads)

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

    def test_missing_tag_does_not_block_events_or_alarms(self):
        """CA-ISOLATION-01: a missing remote tag must not stall events/alarms."""
        from unittest.mock import Mock, patch

        from ..persistence.remote import (
            PeeweeRemoteDB,
            TagValuePayloadMapper,
            reset_missing_tag_tries,
        )

        reset_missing_tag_tries()

        class IsolationRemote(FakeRemote):
            def write_batch_outcomes(self, domain, payloads):
                if domain == DOMAIN.TAG:
                    inner = PeeweeRemoteDB(
                        tag_mapper=TagValuePayloadMapper(
                            resolve_tag=lambda _name: None,
                            resolve_unit=lambda _tag: None,
                        )
                    )
                    return inner.write_batch_outcomes(domain, payloads)
                return super().write_batch_outcomes(domain, payloads)

        now = datetime.now(timezone.utc)
        self.journal.append(PersistableRecord.event(message="ok-event", username="system"))
        self.journal.append(
            PersistableRecord.alarm_create(name="A1", state="Unacknowledged", timestamp=now)
        )
        self.journal.append(PersistableRecord.tag_sample("ghost.FI", 1.0, now))
        self.journal.flush_sync()
        remote = IsolationRemote()
        replicator = RemoteReplicator(self.journal, remote, self.config)
        with patch(
            "automation.catalog.replicator.get_catalog_replicator",
            return_value=Mock(),
        ):
            replicated = replicator.replicate_once()
        self.assertGreaterEqual(replicated, 2)
        domains = {item[0] for item in remote.written}
        self.assertIn(DOMAIN.EVENT, domains)
        self.assertIn(DOMAIN.ALARM_SUMMARY, domains)
        self.assertNotIn(DOMAIN.TAG, domains)
        pending = self.journal.fetch_pending(10)
        self.assertEqual(len(pending), 1)
        self.assertEqual(pending[0]["domain"], DOMAIN.TAG)
        reset_missing_tag_tries()


class TestAlarmSummarySafIdempotency(unittest.TestCase):
    def setUp(self):
        from peewee import SqliteDatabase

        from ..dbmodels.alarms import AlarmStates, AlarmTypes, Alarms, AlarmSummary
        from ..dbmodels.tags import DataTypes, Tags, Units, Variables
        from ..dbmodels import proxy

        self.db = SqliteDatabase(":memory:")
        proxy.initialize(self.db)
        self.db.create_tables(
            [
                Variables,
                Units,
                DataTypes,
                Tags,
                AlarmTypes,
                AlarmStates,
                Alarms,
                AlarmSummary,
            ]
        )
        Variables(name="Adimentional").save()
        Units(name="adim", unit="adim", variable_id=Variables.get(Variables.name == "Adimentional")).save()
        DataTypes(name="int").save()
        unit = Units.get(Units.name == "adim")
        Tags(
            identifier="tag-db",
            name="Linea2.LDS.leak",
            unit=unit,
            data_type=DataTypes.get(DataTypes.name == "int"),
            display_name="Linea2.LDS.leak",
            display_unit=unit,
            description="",
            area="Linea2",
            owner_node="edge-linea2",
        ).save()
        AlarmTypes(name="BOOL").save()
        AlarmStates(
            name="Acknowledged",
            mnemonic="ACK",
            condition="Active",
            status="Ack",
        ).save()
        Alarms(
            identifier="alm-db",
            name="Linea2.ALM.DB.Connection",
            tag=Tags.get(Tags.name == "Linea2.LDS.leak"),
            trigger_type=AlarmTypes.get(AlarmTypes.name == "BOOL"),
            trigger_value=1,
            state=AlarmStates.get(AlarmStates.name == "Acknowledged"),
            description="",
            area="Linea2",
        ).save()

    def tearDown(self):
        self.db.close()

    def test_replay_same_alarm_summary_does_not_duplicate(self):
        from ..persistence.remote import PeeweeRemoteDB

        stamp = datetime(2026, 8, 19, 21, 1, 58, 166000, tzinfo=timezone.utc)
        record = PersistableRecord.alarm_create(
            name="Linea2.ALM.DB.Connection",
            state="Acknowledged",
            timestamp=stamp,
            ack_timestamp=datetime(2026, 8, 19, 21, 6, 26, 144000, tzinfo=timezone.utc),
            area="Linea2",
        )
        payload = dict(record.payload())
        payload["idempotency_key"] = record.idempotency_key()
        remote = PeeweeRemoteDB()
        first = remote.write_batch_outcomes(DOMAIN.ALARM_SUMMARY, [payload])
        second = remote.write_batch_outcomes(DOMAIN.ALARM_SUMMARY, [payload])
        self.assertEqual(first, [True])
        self.assertEqual(second, [True])
        from ..dbmodels.alarms import AlarmSummary

        self.assertEqual(AlarmSummary.select().count(), 1)

    def test_partial_alarm_batch_marks_sent_per_row(self):
        from ..persistence.remote import PeeweeRemoteDB

        stamp = datetime(2026, 8, 19, 21, 1, 58, tzinfo=timezone.utc)
        good = PersistableRecord.alarm_create(
            name="Linea2.ALM.DB.Connection",
            state="Acknowledged",
            timestamp=stamp,
            area="Linea2",
        )
        bad = PersistableRecord.alarm_create(
            name="Linea2.ALM.PERF.SAF_LAG",
            state="Acknowledged",
            timestamp=stamp,
            area="Linea2",
            tag="Linea2.SYS.PERF.SAF_LAG",
            trigger_type="BOOL",
        )
        good_payload = dict(good.payload())
        good_payload["idempotency_key"] = good.idempotency_key()
        bad_payload = dict(bad.payload())
        bad_payload["idempotency_key"] = bad.idempotency_key()
        outcomes = PeeweeRemoteDB().write_batch_outcomes(
            DOMAIN.ALARM_SUMMARY,
            [good_payload, bad_payload],
        )
        self.assertEqual(outcomes[0], True)
        self.assertEqual(outcomes[1], False)
        from ..dbmodels.alarms import AlarmSummary

        self.assertEqual(AlarmSummary.select().count(), 1)

    def test_replicator_partial_alarm_batch_keeps_only_failed_pending(self):
        from unittest.mock import patch

        from ..persistence.remote import PeeweeRemoteDB

        stamp = datetime(2026, 8, 19, 21, 1, 58, tzinfo=timezone.utc)
        good = PersistableRecord.alarm_create(
            name="Linea2.ALM.DB.Connection",
            state="Acknowledged",
            timestamp=stamp,
            area="Linea2",
        )
        bad = PersistableRecord.alarm_create(
            name="Linea2.ALM.PERF.SAF_LAG",
            state="Acknowledged",
            timestamp=stamp,
            area="Linea2",
            tag="Linea2.SYS.PERF.SAF_LAG",
            trigger_type="BOOL",
        )
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        config = SafConfig(
            journal_path=os.path.join(tmp.name, "journal.db"),
            tag_flush_interval_s=0.005,
            replicate_batch_size=100,
            replicate_rate_per_s=10_000,
        )
        journal = JournalWriter(config)
        journal.start()
        self.addCleanup(journal.stop)
        journal.append(good)
        journal.append(bad)
        journal.flush_sync()
        remote = PeeweeRemoteDB()
        replicator = RemoteReplicator(journal, remote, config)
        with patch.object(remote, "is_reachable", return_value=True), patch(
            "automation.persistence.replicator._node_scope", return_value=None
        ):
            replicated = replicator.replicate_once()
        self.assertEqual(replicated, 1)
        pending = journal.fetch_pending(10)
        self.assertEqual(len(pending), 1)
        self.assertIn("SAF_LAG", pending[0]["entity_id"])
        from ..dbmodels.alarms import AlarmSummary

        self.assertEqual(AlarmSummary.select().count(), 1)


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
