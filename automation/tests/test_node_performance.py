import time
import unittest
from unittest.mock import MagicMock, patch

from flask import Flask

from automation.utils import http_metrics
from automation.workers.metrics_sampler import MetricsSamplerWorker, sample_interval_s


class TestHttpMetrics(unittest.TestCase):
    def setUp(self) -> None:
        http_metrics.reset_http_metrics()

    def tearDown(self) -> None:
        http_metrics.reset_http_metrics()

    def test_request_window_increments(self):
        http_metrics.on_request()
        http_metrics.on_response(200)
        http_metrics.on_request()
        http_metrics.on_response(500)
        snap = http_metrics.snapshot()
        self.assertEqual(snap["HTTP_REQUESTS_TOTAL"], 2)
        self.assertEqual(snap["HTTP_REQUESTS_1M"], 2)
        self.assertEqual(snap["HTTP_5XX_TOTAL"], 1)
        self.assertEqual(snap["HTTP_5XX_1M"], 1)
        self.assertEqual(snap["HTTP_IN_FLIGHT"], 0)

    def test_in_flight_tracks_open_requests(self):
        http_metrics.on_request()
        self.assertEqual(http_metrics.snapshot()["HTTP_IN_FLIGHT"], 1)
        http_metrics.on_response(204)
        self.assertEqual(http_metrics.snapshot()["HTTP_IN_FLIGHT"], 0)

    def test_flask_middleware_counts(self):
        app = Flask(__name__)
        http_metrics.install_http_metrics(app)

        @app.route("/ok")
        def ok():
            return "ok", 200

        with app.test_client() as client:
            client.get("/ok")
            client.get("/ok")
        snap = http_metrics.snapshot()
        self.assertGreaterEqual(snap["HTTP_REQUESTS_TOTAL"], 2)
        self.assertGreaterEqual(snap["HTTP_REQUESTS_1M"], 2)

    def test_middleware_exception_does_not_leak_in_flight(self):
        app = Flask(__name__)
        app.testing = True
        http_metrics.install_http_metrics(app)

        @app.route("/boom")
        def boom():
            raise RuntimeError("synthetic")

        with app.test_client() as client:
            with self.assertRaises(RuntimeError):
                client.get("/boom")
        self.assertEqual(http_metrics.snapshot()["HTTP_IN_FLIGHT"], 0)


class TestMetricsSampler(unittest.TestCase):
    def test_sample_interval_clamped(self):
        self.assertEqual(sample_interval_s({"AUTOMATION_METRICS_SAMPLE_INTERVAL_S": "1"}), 5.0)
        self.assertEqual(sample_interval_s({"AUTOMATION_METRICS_SAMPLE_INTERVAL_S": "30"}), 30.0)
        self.assertEqual(sample_interval_s({"AUTOMATION_METRICS_SAMPLE_INTERVAL_S": "99"}), 30.0)
        self.assertEqual(sample_interval_s({}), 5.0)

    def test_get_snapshot_is_o1_copy(self):
        worker = MetricsSamplerWorker(interval_seconds=5)
        worker._publish(
            {
                "HOST_CPU_PERCENT": 12.0,
                "HTTP_REQUESTS_1M": 4,
                "HMI_ACTIVE_CLIENTS": 1,
            }
        )
        with patch.object(worker, "_sample", side_effect=AssertionError("poll must not sample")):
            snap = worker.get_snapshot()
        self.assertEqual(snap["HOST_CPU_PERCENT"], 12.0)
        self.assertEqual(snap["HTTP_REQUESTS_1M"], 4)
        self.assertIsInstance(snap["METRICS_AGE_MS"], float)
        self.assertLess(snap["METRICS_AGE_MS"], 5000)

    def test_get_snapshot_p95_under_5ms(self):
        worker = MetricsSamplerWorker(interval_seconds=5)
        worker._publish({"HOST_CPU_PERCENT": 1.0, "NODE_ID": "edge-a"})
        times = []
        for _ in range(200):
            started = time.perf_counter()
            worker.get_snapshot()
            times.append((time.perf_counter() - started) * 1000.0)
        times.sort()
        p95 = times[int(len(times) * 0.95) - 1]
        self.assertLess(p95, 5.0)

    def test_psutil_fields_when_available(self):
        worker = MetricsSamplerWorker(interval_seconds=5)
        payload = {}
        worker._sample_host(payload)
        try:
            import psutil  # noqa: F401
        except ImportError:
            self.skipTest("psutil not installed")
        self.assertIn("HOST_CPU_PERCENT", payload)
        self.assertIn("HOST_DISK_FREE_GB", payload)
        self.assertIn("HOST_DISK_USED_PERCENT", payload)
        self.assertIn("HOST_DISK_CRITICAL", payload)
        self.assertIn("HOST_RSS_MB", payload)

    def test_survives_db_outage(self):
        worker = MetricsSamplerWorker(interval_seconds=5)
        worker._publish({"DB_TXN_PER_MIN": 10.0, "DB_CONNECTED": True})
        with patch(
            "automation.PyAutomation",
            side_effect=RuntimeError("down"),
        ):
            payload = {}
            worker._sample_db(payload)
        worker._publish(payload)
        snap = worker.get_snapshot()
        self.assertEqual(snap["DB_TXN_PER_MIN"], 10.0)

    def test_hmi_active_clients_uses_store_count(self):
        worker = MetricsSamplerWorker(interval_seconds=5)
        with patch(
            "automation.utils.hmi_session_store.count_sessions",
            return_value=3,
        ):
            payload = {}
            worker._sample_hmi(payload)
        self.assertEqual(payload["HMI_ACTIVE_CLIENTS"], 3)

    def test_sample_catalog_exposes_pending_and_last_sync(self):
        worker = MetricsSamplerWorker(interval_seconds=5)
        payload = {}
        catalog = {
            "CATALOG_PENDING_ROWS": 3,
            "CATALOG_LAST_SYNC": "2026-08-25T12:00:00+00:00",
            "CATALOG_SYNC_ERRORS": 1,
            "CATALOG_ORPHAN_ALARM": True,
        }
        fake = type("W", (), {"sync_status": lambda self: catalog})()
        with patch(
            "automation.catalog.replicator.get_catalog_replicator",
            return_value=fake,
        ):
            worker._sample_catalog(payload)
        self.assertEqual(payload["CATALOG_PENDING_ROWS"], 3)
        self.assertEqual(payload["CATALOG_LAST_SYNC"], "2026-08-25T12:00:00+00:00")
        self.assertEqual(payload["CATALOG_SYNC_ERRORS"], 1)
        self.assertTrue(payload["CATALOG_ORPHAN_ALARM"])

    def test_sample_db_txn_rate_uses_process_local_commits(self):
        from automation.utils.db_connections import note_local_commit, reset_local_txn_commit_count

        reset_local_txn_commit_count()
        worker = MetricsSamplerWorker(interval_seconds=5)
        worker._txn_prev = (0, 0)
        worker._txn_prev_at = __import__("time").monotonic() - 60.0
        for _ in range(10):
            note_local_commit()
        payload = {}
        with patch("automation.PyAutomation") as app_cls, patch(
            "automation.health.get_database_health_service"
        ) as health, patch(
            "automation.utils.db_connections.snapshot_connection_metrics",
            return_value={},
        ), patch(
            "automation.utils.db_connections.query_pg_txn_counters",
            return_value=None,
        ):
            app_cls.return_value.is_db_connected.return_value = True
            app_cls.return_value._db = None
            health.return_value.snapshot.return_value.latency_ms = 4.0
            worker._sample_db(payload)
        self.assertEqual(payload["DB_TXN_PER_MIN"], 10.0)
        reset_local_txn_commit_count()


class TestHealthNodeEndpoint(unittest.TestCase):
    def test_node_endpoint_reads_snapshot_only(self):
        from automation.modules.health.resources import health as health_mod

        worker = MagicMock()
        worker.get_snapshot.return_value = {
            "status": "ok",
            "METRICS_AGE_MS": 12,
            "HOST_CPU_PERCENT": 8.0,
        }
        health_mod.app.metrics_worker = worker
        body = health_mod.node_metrics_payload()
        self.assertEqual(body["HOST_CPU_PERCENT"], 8.0)
        worker.get_snapshot.assert_called_once()

    def test_system_endpoint_still_present(self):
        from automation.modules.health.resources.health import HealthSystemResource

        self.assertTrue(callable(HealthSystemResource.get))

    def test_sampler_does_not_use_peewee_pool(self):
        from pathlib import Path

        source = Path(__file__).resolve().parents[1] / "workers" / "metrics_sampler.py"
        text = source.read_text(encoding="utf-8")
        self.assertNotIn("PooledPostgresql", text)
        self.assertNotIn("PooledMySQL", text)

    def test_hmi_poll_hidden_contract(self):
        focus_ms, hidden_ms = 3000, 30000

        def interval(hidden: bool) -> int:
            return hidden_ms if hidden else focus_ms

        self.assertEqual(interval(False), 3000)
        self.assertEqual(interval(True), 30000)

    def test_trends_fill_from_first_sample(self):
        worker = MetricsSamplerWorker(interval_seconds=5)
        payload = {
            "HOST_CPU_PERCENT": 12.5,
            "HOST_RSS_MB": 220.0,
            "HOST_DISK_USED_PERCENT": 41.0,
            "HTTP_REQUESTS_1M": 8,
            "SAF_QUEUE_DEPTH": 0,
        }
        worker._record_trends(payload)
        worker._record_trends(payload)
        trends = payload["TRENDS"]
        self.assertEqual(len(trends["cpu"]), 2)
        self.assertEqual(trends["cpu"][-1]["v"], 12.5)
        self.assertEqual(set(trends), {"cpu", "rss", "disk", "http", "saf"})

    def test_trends_drop_points_older_than_window(self):
        worker = MetricsSamplerWorker(interval_seconds=5)
        worker._trend_buffers["cpu"].append({"t": 1, "v": 1.0})
        with patch("automation.workers.metrics_sampler.time.time", return_value=400.0):
            payload = {"HOST_CPU_PERCENT": 9.0}
            worker._record_trends(payload)
        self.assertEqual(len(payload["TRENDS"]["cpu"]), 1)
        self.assertEqual(payload["TRENDS"]["cpu"][0]["v"], 9.0)

    def test_get_snapshot_does_not_sample_trends(self):
        worker = MetricsSamplerWorker(interval_seconds=5)
        worker._publish({"HOST_CPU_PERCENT": 3.0, "TRENDS": {"cpu": [{"t": 1, "v": 3.0}]}})
        with patch.object(worker, "_record_trends", side_effect=AssertionError("GET must not record")):
            snap = worker.get_snapshot()
        self.assertEqual(snap["TRENDS"]["cpu"][0]["v"], 3.0)


if __name__ == "__main__":
    unittest.main()
