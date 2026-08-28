# -*- coding: utf-8 -*-
"""CA-LR long-run hardening: DLQ cap, catalog compact, host disk critical."""
from __future__ import annotations

import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from ..catalog import local_db
from ..persistence.config import SafConfig
from ..persistence.journal import STATUS_DEAD_LETTER, JournalWriter
from ..persistence.records import PersistableRecord
from ..workers.metrics_sampler import MetricsSamplerWorker


class TestDeadLetterBounds(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.tmp.cleanup()

    def _writer(self, **kwargs) -> JournalWriter:
        defaults = dict(
            journal_path=os.path.join(self.tmp.name, "journal.db"),
            dead_letter_attempts=1,
            dead_letter_max_rows=10_000,
            dead_letter_ttl_s=7 * 86400,
            tag_flush_interval_s=60.0,
            ring_maxsize=64,
        )
        defaults.update(kwargs)
        writer = JournalWriter(SafConfig(**defaults))
        writer.start()
        return writer

    def _poison(self, writer: JournalWriter, n: int) -> None:
        ts = datetime(2026, 1, 7, tzinfo=timezone.utc)
        for i in range(n):
            writer.append(
                PersistableRecord.event(
                    message=f"poison-{i}",
                    username="system",
                    timestamp=ts + timedelta(milliseconds=i),
                )
            )
        writer.flush_sync()
        rows = writer.fetch_pending(n + 5)
        writer.mark_pending([int(row["id"]) for row in rows], error="rejected")

    def test_prune_dead_letters_caps_max_rows(self):
        writer = self._writer(dead_letter_max_rows=2, dead_letter_ttl_s=86_400 * 365)
        try:
            self._poison(writer, 5)
            writer._last_dlq_prune_mono = 0.0
            deleted = writer.prune_dead_letters()
            self.assertGreaterEqual(deleted, 3)
            with writer._lock:
                row = writer._conn.execute(
                    "SELECT COUNT(*) FROM persistence_journal WHERE status = ?",
                    (STATUS_DEAD_LETTER,),
                ).fetchone()
            self.assertEqual(int(row[0]), 2)
            self.assertEqual(writer.deadletter_count, 2)
        finally:
            writer.stop()

    def test_prune_dead_letters_ttl(self):
        writer = self._writer(dead_letter_max_rows=10_000, dead_letter_ttl_s=3600.0)
        try:
            self._poison(writer, 2)
            old = (datetime.now(timezone.utc) - timedelta(days=8)).isoformat()
            with writer._lock:
                writer._conn.execute(
                    "UPDATE persistence_journal SET created_at = ? WHERE status = ?",
                    (old, STATUS_DEAD_LETTER),
                )
                writer._commit_locked()
            writer._last_dlq_prune_mono = 0.0
            deleted = writer.prune_dead_letters()
            self.assertEqual(deleted, 2)
            self.assertEqual(writer.deadletter_count, 0)
        finally:
            writer.stop()


class TestCatalogCompact(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = os.path.join(self.tmp.name, "catalog.db")
        local_db.close_catalog_db()
        local_db._last_catalog_compact_mono = 0.0
        local_db._last_catalog_checkpoint_mono = 0.0

    def tearDown(self):
        local_db.close_catalog_db()
        self.tmp.cleanup()

    def test_compact_catalog_idle_vacuums_freelist(self):
        db = local_db.open_catalog_db(self.path)
        db.execute_sql("CREATE TABLE IF NOT EXISTS noise (id INTEGER PRIMARY KEY, blob TEXT)")
        for _ in range(80):
            db.execute_sql("INSERT INTO noise (blob) VALUES (?)", ("x" * 256,))
        db.execute_sql("DELETE FROM noise")
        local_db.close_catalog_db()
        local_db._last_catalog_compact_mono = 0.0
        local_db._last_catalog_checkpoint_mono = 0.0
        result = local_db.compact_catalog_idle(min_freelist_bytes=1, min_interval_s=0.0)
        self.assertEqual(result["skipped"], 0)
        self.assertIn(result["vacuumed"], (0, 1))
        self.assertIn("checkpointed", result)

    def test_catalog_temp_store_memory(self):
        db = local_db.open_catalog_db(self.path)
        row = db.execute_sql("PRAGMA temp_store").fetchone()
        self.assertEqual(int(row[0]), 2)


class TestHostDiskCritical(unittest.TestCase):
    def test_host_disk_critical_rising_edge_emits_event(self):
        worker = MetricsSamplerWorker(interval_seconds=5)
        disk = type("Disk", (), {"percent": 90.0, "free": 1, "total": 10, "used": 9})()
        payload = {}
        with patch(
            "automation.utils.audit_metrics.cooldown_allows", return_value=True
        ), patch(
            "automation.utils.system_event_audit.persist_system_event"
        ) as persist:
            worker._apply_disk_critical(payload, disk)
            persist.assert_called_once()
            self.assertTrue(payload["HOST_DISK_CRITICAL"])
            worker._apply_disk_critical(payload, disk)
            self.assertEqual(persist.call_count, 1)

    def test_host_disk_below_threshold_is_not_critical(self):
        worker = MetricsSamplerWorker(interval_seconds=5)
        disk = type("Disk", (), {"percent": 84.0, "free": 2, "total": 10, "used": 8})()
        payload = {}
        with patch.object(worker, "_disk_critical_percent", return_value=85.0), patch(
            "automation.utils.system_event_audit.persist_system_event"
        ) as persist:
            worker._apply_disk_critical(payload, disk)
        self.assertFalse(payload["HOST_DISK_CRITICAL"])
        persist.assert_not_called()


if __name__ == "__main__":
    unittest.main()
