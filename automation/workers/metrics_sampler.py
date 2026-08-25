# -*- coding: utf-8 -*-
"""Precompute node performance snapshot off the HTTP request path.

The GET /api/health/node handler only copies this dict. Sampling I/O lives here.
"""
from __future__ import annotations

import logging
import os
import threading
import time
from collections import deque
from typing import Any

from .worker import BaseWorker
from ..utils.perf_alarm_evaluator import PerfAlarmEvaluator
from ..utils.performance_alarm_config import load_performance_alarm_config
from ..utils.performance_alarms import catalog_for_snapshot, ensure_performance_alarms

_LOGGER = logging.getLogger("pyautomation.metrics")

_DEFAULT_INTERVAL_S = 5.0
_MIN_INTERVAL_S = 5.0
_MAX_INTERVAL_S = 30.0
TREND_WINDOW_S = 300.0
TREND_FIELDS = (
    ("cpu", "HOST_CPU_PERCENT"),
    ("rss", "HOST_RSS_MB"),
    ("disk", "HOST_DISK_USED_PERCENT"),
    ("http", "HTTP_REQUESTS_1M"),
    ("saf", "SAF_QUEUE_DEPTH"),
)


def sample_interval_s(environ: dict | None = None) -> float:
    env = os.environ if environ is None else environ
    raw = env.get("AUTOMATION_METRICS_SAMPLE_INTERVAL_S")
    try:
        value = float(raw) if raw not in (None, "") else _DEFAULT_INTERVAL_S
    except (TypeError, ValueError):
        value = _DEFAULT_INTERVAL_S
    return max(_MIN_INTERVAL_S, min(_MAX_INTERVAL_S, value))


class MetricsSamplerWorker(BaseWorker):
    """Daemon thread; writes a process-local snapshot for O(1) HTTP polls."""

    def __init__(self, interval_seconds: float | None = None):
        super().__init__()
        self.name = "MetricsSamplerWorker"
        self.daemon = True
        self._interval_s = sample_interval_s() if interval_seconds is None else float(interval_seconds)
        self._interval_s = max(_MIN_INTERVAL_S, min(_MAX_INTERVAL_S, self._interval_s))
        self._lock = threading.Lock()
        self._snapshot: dict[str, Any] = {}
        self._sampled_at = 0.0
        self._started_at = time.monotonic()
        self._txn_prev: tuple[int, int] | None = None
        self._txn_prev_at = 0.0
        self._cpu_primed = False
        self._alarms_ready = False
        self._tags_persisted = False
        self._evaluator = PerfAlarmEvaluator(config_provider=self._app_config)
        self._trend_buffers: dict[str, deque] = {key: deque() for key, _field in TREND_FIELDS}

    def get_snapshot(self) -> dict[str, Any]:
        now = time.monotonic()
        with self._lock:
            payload = dict(self._snapshot)
            sampled_at = self._sampled_at
        age_ms = None if sampled_at <= 0 else round((now - sampled_at) * 1000.0, 1)
        payload.setdefault("status", "ok" if sampled_at > 0 else "warming")
        payload["METRICS_AGE_MS"] = age_ms
        payload["uptime_s"] = round(now - self._started_at, 1)
        return payload

    def _app_config(self) -> dict:
        try:
            from .. import PyAutomation

            return PyAutomation().get_app_config() or {}
        except Exception:
            return {}

    def reconfigure(self) -> None:
        """Hot-reload thresholds; evaluate the last snapshot in this cycle."""
        self._evaluator.reload()
        self._alarms_ready = False
        self._tags_persisted = False
        with self._lock:
            snap = dict(self._snapshot)
        if snap:
            try:
                self._ensure_alarms()
                self._evaluator.evaluate(snap)
                snap["PERF_ALARMS"] = catalog_for_snapshot(self._evaluator.config)
                self._publish(snap)
            except Exception:
                _LOGGER.warning("Performance alarm reconfigure evaluate skipped", exc_info=True)

    def _ensure_alarms(self) -> None:
        if self._alarms_ready and self._tags_persisted:
            return
        try:
            persisted = bool(ensure_performance_alarms(self._evaluator.config))
            self._alarms_ready = True
            self._tags_persisted = persisted
        except Exception:
            _LOGGER.debug("performance alarms ensure skipped", exc_info=True)

    def run(self) -> None:
        _LOGGER.info("MetricsSamplerWorker started interval_s=%s", self._interval_s)
        self._prime_cpu()
        self._evaluator.reload()
        self._ensure_alarms()
        while not self.stop_event.is_set():
            try:
                self._publish(self._sample())
            except Exception:
                _LOGGER.warning("Metrics sampler tick failed", exc_info=True)
            self.stop_event.wait(self._interval_s)
        _LOGGER.info("MetricsSamplerWorker stopped")

    def _prime_cpu(self) -> None:
        try:
            import psutil

            psutil.cpu_percent(interval=None)
            psutil.Process().cpu_percent(interval=None)
            self._cpu_primed = True
        except Exception:
            self._cpu_primed = False

    def _publish(self, partial: dict[str, Any]) -> None:
        with self._lock:
            merged = dict(self._snapshot)
            for key, value in partial.items():
                if value is not None or key not in merged:
                    merged[key] = value
            merged["status"] = "ok"
            self._snapshot = merged
            self._sampled_at = time.monotonic()

    def _sample(self) -> dict[str, Any]:
        payload: dict[str, Any] = {}
        self._sample_identity(payload)
        self._sample_host(payload)
        self._sample_http(payload)
        self._sample_hmi(payload)
        self._sample_db(payload)
        self._sample_saf(payload)
        self._sample_acquisition(payload)
        self._sample_clock(payload)
        self._sample_perf_alarms(payload)
        self._record_trends(payload)
        return payload

    def _trend_maxlen(self) -> int:
        return max(16, int(TREND_WINDOW_S / max(self._interval_s, 1.0)) + 8)

    def _record_trends(self, payload: dict[str, Any]) -> None:
        """Ring of the last 5 min, filled from process start. Copied into the snapshot (O(1) GET)."""
        now_ms = int(time.time() * 1000)
        cut = now_ms - int(TREND_WINDOW_S * 1000)
        maxlen = self._trend_maxlen()
        out: dict[str, list[dict[str, float]]] = {}
        for key, field in TREND_FIELDS:
            buf = self._trend_buffers[key]
            raw = payload.get(field)
            if raw is not None:
                try:
                    buf.append({"t": now_ms, "v": round(float(raw), 4)})
                except (TypeError, ValueError):
                    pass
            while buf and buf[0]["t"] < cut:
                buf.popleft()
            while len(buf) > maxlen:
                buf.popleft()
            out[key] = list(buf)
        payload["TRENDS"] = out

    def _sample_perf_alarms(self, payload: dict[str, Any]) -> None:
        try:
            now = time.monotonic()
            age_ms = None if self._sampled_at <= 0 else round((now - self._sampled_at) * 1000.0, 1)
            payload["METRICS_AGE_MS"] = age_ms
            self._ensure_alarms()
            self._evaluator.evaluate(payload)
            cfg = self._evaluator.config or load_performance_alarm_config(self._app_config())
            payload["PERF_ALARMS"] = catalog_for_snapshot(cfg)
        except Exception:
            _LOGGER.debug("metrics performance alarms skipped", exc_info=True)

    def _sample_identity(self, payload: dict[str, Any]) -> None:
        try:
            from ..node_scope import get_node_scope

            scope = get_node_scope()
            payload["NODE_ID"] = scope.node_id if scope.is_valid else None
            payload["NODE_AREA"] = scope.area if scope.enabled else None
            payload["NODE_SITE"] = scope.site if scope.enabled else None
            payload["MULTI_EDGE_ENABLED"] = bool(scope.enabled)
        except Exception:
            _LOGGER.debug("metrics identity skipped", exc_info=True)

    def _sample_host(self, payload: dict[str, Any]) -> None:
        try:
            import psutil

            proc = psutil.Process()
            rss = proc.memory_info().rss / (1024 * 1024)
            disk = psutil.disk_usage("/")
            payload["HOST_RSS_MB"] = round(rss, 2)
            payload["HOST_CPU_PERCENT"] = round(float(psutil.cpu_percent(interval=None)), 1)
            payload["HOST_DISK_FREE_GB"] = round(disk.free / (1024 ** 3), 2)
            payload["HOST_DISK_USED_PERCENT"] = round(float(disk.percent), 1)
            payload["HOST_THREADS"] = int(proc.num_threads())
        except Exception:
            _LOGGER.debug("metrics host (psutil) skipped", exc_info=True)
            try:
                import resource
                import threading

                payload["HOST_RSS_MB"] = round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024, 2)
                payload["HOST_THREADS"] = int(threading.active_count())
            except Exception:
                pass

    def _sample_http(self, payload: dict[str, Any]) -> None:
        try:
            from ..utils.http_metrics import snapshot

            payload.update(snapshot())
        except Exception:
            _LOGGER.debug("metrics http skipped", exc_info=True)

    def _sample_hmi(self, payload: dict[str, Any]) -> None:
        started = time.monotonic()
        try:
            from ..utils.hmi_session_store import count_sessions
            from ..utils.redis_client import get_redis, redis_url

            payload["HMI_ACTIVE_CLIENTS"] = int(count_sessions())
            payload["HMI_SESSIONS_SAMPLE_AGE_MS"] = round((time.monotonic() - started) * 1000.0, 1)
            payload["REDIS_CONFIGURED"] = bool(redis_url())
            payload["REDIS_AVAILABLE"] = get_redis() is not None
        except Exception:
            _LOGGER.debug("metrics hmi sessions skipped", exc_info=True)

    def _sample_db(self, payload: dict[str, Any]) -> None:
        try:
            from .. import PyAutomation
            from ..health import get_database_health_service
            from ..utils.db_connections import query_pg_txn_counters, snapshot_connection_metrics

            app = PyAutomation()
            payload["DB_CONNECTED"] = bool(app.is_db_connected())
            health = get_database_health_service().snapshot()
            payload["DB_LATENCY_MS"] = health.latency_ms
            db = getattr(app, "_db", None)
            conn = snapshot_connection_metrics(db)
            payload["DB_ACTIVE_CONNECTIONS"] = conn.get("DB_ACTIVE_CONNECTIONS")
            payload["DB_CONNECTIONS_LOCAL"] = conn.get("DB_CONNECTIONS_COUNT")
            payload["DB_DISK_FREE_GB"] = None
            counters = query_pg_txn_counters(db)
            now = time.monotonic()
            if counters is None:
                return
            commits, rollbacks = counters
            total = commits + rollbacks
            if self._txn_prev is not None and self._txn_prev_at > 0:
                elapsed = max(0.001, now - self._txn_prev_at)
                delta = max(0, total - (self._txn_prev[0] + self._txn_prev[1]))
                payload["DB_TXN_PER_MIN"] = round(delta * (60.0 / elapsed), 1)
            else:
                payload["DB_TXN_PER_MIN"] = None
            self._txn_prev = (commits, rollbacks)
            self._txn_prev_at = now
        except Exception:
            _LOGGER.debug("metrics db skipped", exc_info=True)

    def _sample_saf(self, payload: dict[str, Any]) -> None:
        try:
            from ..persistence import get_persistence_gateway

            snap = get_persistence_gateway().snapshot()
            payload["SAF_QUEUE_DEPTH"] = int(snap.get("SAF_QUEUE_DEPTH") or 0)
            lag_s = snap.get("SAF_REPLICATION_LAG")
            payload["SAF_REPLICATION_LAG_MS"] = (
                None if lag_s is None else round(float(lag_s) * 1000.0, 1)
            )
            payload["SAF_DISK_BYTES"] = int(snap.get("SAF_DISK_BYTES") or 0)
        except Exception:
            _LOGGER.debug("metrics saf skipped", exc_info=True)

    def _sample_acquisition(self, payload: dict[str, Any]) -> None:
        try:
            from .. import PyAutomation
            from ..state_machine_timing import snapshot_timing_metrics

            app = PyAutomation()
            payload["ACQUISITION_READY"] = bool(getattr(app, "acquisition_ready", False))
            try:
                payload["OPC_MONITORED_COUNT"] = int(app.das.monitored_count())
            except Exception:
                payload["OPC_MONITORED_COUNT"] = 0
            try:
                payload["CVT_TAG_COUNT"] = int(app.cvt.tag_count())
                payload["CVT_LOCK_CONTENTION"] = int(app.cvt.lock_contention())
            except Exception:
                payload["CVT_TAG_COUNT"] = 0
                payload["CVT_LOCK_CONTENTION"] = 0
            timing = snapshot_timing_metrics()
            payload["SAMPLE_LAG_MS"] = timing.get("SAMPLE_LAG_MS")
        except Exception:
            _LOGGER.debug("metrics acquisition skipped", exc_info=True)

    def _sample_clock(self, payload: dict[str, Any]) -> None:
        try:
            from .. import PyAutomation

            worker = getattr(PyAutomation(), "ntp_worker", None)
            if worker is None:
                payload["clock"] = {"synced": False, "offset_ms": None, "enabled": False}
                return
            status = worker.get_status()
            payload["clock"] = {
                "enabled": bool(status.get("enabled")),
                "synced": bool(status.get("synced")),
                "warn": bool(status.get("warn")),
                "offset_ms": status.get("offset_ms"),
            }
        except Exception:
            _LOGGER.debug("metrics clock skipped", exc_info=True)
