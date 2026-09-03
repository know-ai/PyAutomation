# -*- coding: utf-8 -*-
"""Hot controls on /performance — CA-OPS-01…05 (spec CA-PERF-01…05, no clash with ISA-18.2)."""
from __future__ import annotations

import os
import tempfile
import time
import unittest
from unittest.mock import MagicMock, patch

from automation.catalog.replicator import CatalogReplicatorWorker, _PendingOrphan
from automation.persistence.config import SafConfig
from automation.persistence.journal import JournalWriter
from automation.persistence.records import PersistableRecord
from automation.utils.ops_controls import (
    OpsControlError,
    catalog_clean_orphans,
    normalize_worker_name,
    require_control_role,
    require_destructive_role,
    restart_worker,
    saf_reset,
    saf_retry,
    worker_snapshot,
)


def _user(role: str, username: str = "admin@example.com"):
    user = MagicMock()
    user.username = username
    user.role = MagicMock()
    user.role.name = role
    return user


class ImmediateThread:
    def __init__(self, target=None, **_kwargs):
        self.target = target

    def start(self):
        if self.target:
            self.target()


class TestOpsRoles(unittest.TestCase):
    def test_ca_ops_02_operator_cannot_control(self):
        with self.assertRaises(PermissionError):
            require_control_role(_user("operator"))
        with self.assertRaises(PermissionError):
            require_destructive_role(_user("supervisor"))
        require_control_role(_user("supervisor"))
        require_destructive_role(_user("admin"))

    def test_integrator_can_control_and_destroy(self):
        require_control_role(_user("integrator"))
        require_destructive_role(_user("integrator"))

    def test_worker_name_aliases(self):
        self.assertEqual(normalize_worker_name("logger"), "LoggerWorker")
        self.assertEqual(normalize_worker_name("CatalogReplicatorWorker"), "CatalogReplicator")
        with self.assertRaises(OpsControlError):
            normalize_worker_name("WaveletWorker")


class TestWorkerSnapshot(unittest.TestCase):
    def test_ca_ops_01_three_workers(self):
        app = MagicMock()
        logger = MagicMock()
        logger.is_alive.return_value = True
        logger.last_cycle_utc = "2026-08-25T12:00:00+00:00"
        metrics = MagicMock()
        metrics.is_alive.return_value = True
        metrics.last_cycle_utc = "2026-08-25T12:00:01+00:00"
        app.db_worker = logger
        app.metrics_worker = metrics
        catalog = MagicMock()
        catalog.is_alive.return_value = True
        catalog._last_sync = None
        with patch("automation.PyAutomation", return_value=app), patch(
            "automation.catalog.replicator.get_catalog_replicator", return_value=catalog
        ):
            snap = worker_snapshot()
        self.assertEqual(set(snap), {"LoggerWorker", "CatalogReplicator", "MetricsSampler", "ReplicationWorker"})
        self.assertEqual(snap["LoggerWorker"]["state"], "alive")
        self.assertEqual(snap["CatalogReplicator"]["state"], "alive")
        self.assertEqual(snap["MetricsSampler"]["state"], "alive")

    def test_ca_ops_05_restarting_state(self):
        from automation.utils import ops_controls as mod

        app = MagicMock()
        app.db_worker = None
        app.metrics_worker = None
        mod._RESTARTING["LoggerWorker"] = True
        try:
            with patch("automation.PyAutomation", return_value=app), patch(
                "automation.catalog.replicator.get_catalog_replicator", return_value=None
            ):
                snap = worker_snapshot()
            self.assertEqual(snap["LoggerWorker"]["state"], "restarting")
        finally:
            mod._RESTARTING["LoggerWorker"] = False


class TestSafControls(unittest.TestCase):
    def test_ca_ops_03_reset_requires_confirm(self):
        with self.assertRaises(OpsControlError):
            saf_reset(confirm=False, user=_user("admin"))

    def test_ca_ops_04_reset_audits_and_drops(self):
        gw = MagicMock()
        gw.drop_unsent.return_value = 12
        with patch("automation.persistence.get_persistence_gateway", return_value=gw), patch(
            "automation.utils.ops_controls.persist_system_event"
        ) as persist, patch("automation.utils.ops_controls._refresh_metrics"):
            result = saf_reset(confirm=True, user=_user("admin"), reason="queue full")
        self.assertEqual(result["dropped"], 12)
        persist.assert_called_once()
        kwargs = persist.call_args.kwargs
        self.assertEqual(kwargs["message"], "SAF queue emptied")
        self.assertIn("admin@example.com", kwargs["description"])
        self.assertEqual(kwargs["classification"], "System")
        self.assertEqual(kwargs["criticity"], 5)

    def test_saf_retry_audits(self):
        app = MagicMock()
        app.db_worker = MagicMock()
        gw = MagicMock()
        gw.replicate_catchup.return_value = 3
        gw.replicate_once.return_value = 3
        with patch("automation.PyAutomation", return_value=app), patch(
            "automation.persistence.get_persistence_gateway", return_value=gw
        ), patch("automation.utils.ops_controls.persist_system_event") as persist, patch(
            "automation.utils.ops_controls._refresh_metrics"
        ):
            result = saf_retry(user=_user("supervisor"), reason="depth")
        self.assertEqual(result["replicated"], 3)
        app.db_worker.request_cycle.assert_called_once()
        persist.assert_called_once()
        self.assertEqual(persist.call_args.kwargs["message"], "SAF retry requested")


class TestJournalDropUnsent(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.journal = JournalWriter(
            SafConfig(
                journal_path=os.path.join(self.tmp.name, "journal.db"),
                ring_maxsize=8,
                tag_batch_size=4,
                tag_flush_interval_s=0.005,
            )
        )
        self.journal.start()

    def tearDown(self):
        self.journal.stop()
        self.tmp.cleanup()

    def test_drop_unsent_requires_confirm(self):
        with self.assertRaises(ValueError):
            self.journal.drop_unsent(confirm=False)

    def test_drop_unsent_pending_keeps_sent(self):
        pending = PersistableRecord.event(message="keep-me-not", username="system")
        sent = PersistableRecord.event(message="already-sent", username="system")
        pending_id = self.journal.append(pending)
        sent_id = self.journal.append(sent)
        self.journal.mark_sent([sent_id])
        dropped = self.journal.drop_unsent(confirm=True)
        self.assertGreaterEqual(dropped, 1)
        leftover = {row["id"] for row in self.journal.fetch_pending(20)}
        self.assertNotIn(pending_id, leftover)
        self.assertEqual(self.journal.fetch_pending(20), [])


class TestCatalogOrphans(unittest.TestCase):
    def test_drop_orphans_older_than_threshold(self):
        worker = CatalogReplicatorWorker.__new__(CatalogReplicatorWorker)
        worker._pending_loaded = True
        now = time.monotonic()
        worker._pending_orphans = {
            ("tagsmachines", "old"): _PendingOrphan(
                table="tagsmachines", key="old", remote_row={}, first_seen_mono=now - 700
            ),
            ("tagsmachines", "fresh"): _PendingOrphan(
                table="tagsmachines", key="fresh", remote_row={}, first_seen_mono=now - 60
            ),
        }
        with patch.object(worker, "_flush_pending_to_disk"):
            dropped = worker.drop_orphans_older_than(10)
        self.assertEqual(dropped, 1)
        self.assertIn(("tagsmachines", "fresh"), worker._pending_orphans)
        self.assertNotIn(("tagsmachines", "old"), worker._pending_orphans)

    def test_clean_orphans_rejects_bad_age(self):
        with self.assertRaises(OpsControlError):
            catalog_clean_orphans(age_minutes=7, user=_user("admin"))

    def test_clean_orphans_audits(self):
        worker = MagicMock()
        worker.drop_orphans_older_than.return_value = 4
        with patch("automation.catalog.replicator.get_catalog_replicator", return_value=worker), patch(
            "automation.utils.ops_controls.persist_system_event"
        ) as persist, patch("automation.utils.ops_controls._refresh_metrics"):
            result = catalog_clean_orphans(age_minutes=10, user=_user("admin"))
        self.assertEqual(result["dropped"], 4)
        persist.assert_called_once()
        self.assertEqual(persist.call_args.kwargs["message"], "Catalog orphans cleaned")


class TestRestartWorker(unittest.TestCase):
    def test_restart_accepts_and_audits(self):
        with patch("automation.utils.ops_controls.threading.Thread", ImmediateThread), patch(
            "automation.utils.ops_controls._restart_logger", return_value={"state": "alive"}
        ), patch("automation.utils.ops_controls.persist_system_event") as persist, patch(
            "automation.utils.ops_controls._refresh_metrics"
        ), patch("automation.utils.ops_controls.worker_snapshot", return_value={"LoggerWorker": {"state": "alive"}}):
            result = restart_worker("LoggerWorker", user=_user("admin"), reason="high queue")
        self.assertTrue(result["accepted"])
        self.assertEqual(result["worker"], "LoggerWorker")
        persist.assert_called_once()
        self.assertEqual(persist.call_args.kwargs["message"], "Worker restarted: LoggerWorker")
        self.assertIn("admin@example.com", persist.call_args.kwargs["description"])


if __name__ == "__main__":
    unittest.main()
