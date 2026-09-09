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
_SMART_INTERVAL_S = 60.0
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
        self._txn_cluster_prev: int | None = None
        self._txn_cluster_prev_at = 0.0
        self._cpu_primed = False
        self._alarms_ready = False
        self._tags_persisted = False
        self.last_cycle_utc = None
        self._evaluator = PerfAlarmEvaluator(config_provider=self._app_config)
        self._trend_buffers: dict[str, deque] = {key: deque() for key, _field in TREND_FIELDS}
        self._saf_rate_prev: tuple[int, int] | None = None
        self._saf_rate_at = 0.0
        self._disk_was_critical = False
        self._smart_sample: dict[str, Any] = {}
        self._smart_at = 0.0
        self._ssd_was_alarm = False

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

    def request_sample(self) -> None:
        """Refresh the snapshot immediately (operator action, not the HTTP poll)."""
        try:
            self._publish(self._sample())
        except Exception:
            _LOGGER.debug("metrics request_sample skipped", exc_info=True)

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
        self.release_historian_socket()
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
            from datetime import datetime, timezone

            self.last_cycle_utc = datetime.now(timezone.utc).isoformat()

    def _sample(self) -> dict[str, Any]:
        payload: dict[str, Any] = {}
        self._sample_identity(payload)
        self._sample_host(payload)
        self._sample_http(payload)
        self._sample_hmi(payload)
        self._sample_db(payload)
        self._sample_saf(payload)
        self._sample_field(payload)
        self._sample_hub(payload)
        self._sample_catalog(payload)
        self._sample_acquisition(payload)
        self._sample_workers(payload)
        self._sample_clock(payload)
        self._sample_peers(payload)
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
            disk = self._disk_usage(psutil)
            payload["HOST_RSS_MB"] = round(rss, 2)
            payload["HOST_CPU_PERCENT"] = round(float(psutil.cpu_percent(interval=None)), 1)
            payload["HOST_DISK_FREE_GB"] = round(disk.free / (1024 ** 3), 2)
            payload["HOST_DISK_USED_PERCENT"] = round(float(disk.percent), 1)
            payload["HOST_THREADS"] = int(proc.num_threads())
            self._apply_disk_critical(payload, disk)
        except Exception:
            _LOGGER.debug("metrics host (psutil) skipped", exc_info=True)
            try:
                import resource
                import threading

                payload["HOST_RSS_MB"] = round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024, 2)
                payload["HOST_THREADS"] = int(threading.active_count())
                payload.setdefault("HOST_DISK_CRITICAL", False)
            except Exception:
                pass
        self._sample_disk_mount(payload)
        self._sample_ssd(payload)

    def _host_data_dir(self) -> str:
        env = os.environ.get("AUTOMATION_DATA_DIR", "").strip()
        if env:
            return env
        try:
            from ..persistence.config import SafConfig

            cfg = SafConfig.from_app_config(self._app_config())
            return os.path.dirname(os.path.abspath(cfg.journal_path)) or "."
        except Exception:
            return os.path.abspath(os.path.join(".", "db"))

    def _disk_usage(self, psutil_mod):
        data_dir = self._host_data_dir()
        target = data_dir if os.path.isdir(data_dir) else os.path.dirname(data_dir) or "/"
        try:
            return psutil_mod.disk_usage(target or "/")
        except Exception:
            return psutil_mod.disk_usage("/")

    def _disk_critical_percent(self) -> float:
        try:
            from ..persistence.config import SafConfig

            return float(SafConfig.from_app_config(self._app_config()).host_disk_critical_percent)
        except Exception:
            return 85.0

    def _apply_disk_critical(self, payload: dict[str, Any], disk) -> None:
        used_percent = round(float(getattr(disk, "percent", 0.0) or 0.0), 1)
        threshold = self._disk_critical_percent()
        is_critical = used_percent > threshold
        payload["HOST_DISK_USED_PERCENT"] = used_percent
        payload["HOST_DISK_CRITICAL"] = bool(is_critical)
        if is_critical and not self._disk_was_critical:
            self._emit_disk_critical(used_percent, threshold)
        self._disk_was_critical = bool(is_critical)

    def _emit_disk_critical(self, used_percent: float, threshold: float) -> None:
        try:
            from ..utils.audit_metrics import cooldown_allows
            from ..utils.system_event_audit import persist_system_event

            if not cooldown_allows("host:disk_critical", 3600.0):
                return
            persist_system_event(
                message="Disk usage critical",
                description=f"used_percent={used_percent} threshold={threshold}",
                classification="System",
                priority=4,
                criticity=4,
            )
        except Exception:
            _LOGGER.debug("host disk critical event skipped", exc_info=True)

    def _sample_disk_mount(self, payload: dict[str, Any]) -> None:
        try:
            from ..utils.disk_mount import snapshot as mount_snapshot, warn_if_missing_noatime

            payload.update(mount_snapshot(self._host_data_dir()))
            warn_if_missing_noatime(self._host_data_dir())
        except Exception:
            _LOGGER.debug("metrics disk mount skipped", exc_info=True)
            payload.setdefault("HOST_DISK_NOATIME", None)

    def _sample_ssd(self, payload: dict[str, Any]) -> None:
        try:
            from ..utils import ssd_health

            now = time.monotonic()
            if now - self._smart_at >= _SMART_INTERVAL_S or not self._smart_sample:
                self._smart_sample = ssd_health.collect()
                self._smart_at = now
            sample = self._smart_sample or {}
            wear = sample.get("wear_percent")
            temp = sample.get("temp_c")
            available = bool(sample.get("available"))
            payload["HOST_SSD_SMART_AVAILABLE"] = available
            payload["HOST_SSD_DEVICE"] = sample.get("device")
            payload["HOST_SSD_WEAR_PERCENT"] = None if wear is None else round(float(wear), 1)
            payload["HOST_SSD_TEMP_C"] = None if temp is None else round(float(temp), 1)
            wear_warn = ssd_health.wear_warn_percent()
            temp_warn = ssd_health.temp_warn_c()
            payload["HOST_SSD_WEAR_WARN"] = wear_warn
            payload["HOST_SSD_TEMP_WARN"] = temp_warn
            is_alarm = ssd_health.alarm_active(sample, wear_warn=wear_warn, temp_warn=temp_warn)
            payload["HOST_SSD_ALARM"] = 1.0 if is_alarm else 0.0
            if is_alarm and not self._ssd_was_alarm:
                self._emit_ssd_alarm(payload, wear_warn, temp_warn)
            self._ssd_was_alarm = bool(is_alarm)
        except Exception:
            _LOGGER.debug("metrics SSD SMART skipped", exc_info=True)
            payload.setdefault("HOST_SSD_ALARM", 0.0)
            payload.setdefault("HOST_SSD_SMART_AVAILABLE", False)

    def _emit_ssd_alarm(self, payload: dict[str, Any], wear_warn: float, temp_warn: float) -> None:
        try:
            from ..utils.audit_metrics import cooldown_allows
            from ..utils.system_event_audit import persist_system_event

            if not cooldown_allows("host:ssd_smart", 3600.0):
                return
            persist_system_event(
                message="SSD SMART warning",
                description=(
                    f"wear={payload.get('HOST_SSD_WEAR_PERCENT')} "
                    f"wear_warn={wear_warn} temp={payload.get('HOST_SSD_TEMP_C')} "
                    f"temp_warn={temp_warn}"
                ),
                classification="System",
                priority=3,
                criticity=3,
            )
        except Exception:
            _LOGGER.debug("host SSD SMART event skipped", exc_info=True)

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
            from ..utils.db_connections import (
                REGISTRY,
                idle_socket_budget_s,
                local_txn_commit_count,
                query_pg_txn_counters,
                snapshot_connection_metrics,
            )

            app = PyAutomation()
            payload["DB_CONNECTED"] = bool(app.is_db_connected())
            health = get_database_health_service().snapshot()
            payload["DB_LATENCY_MS"] = health.latency_ms
            db = getattr(app, "_db", None)
            # Sockets whose greenlet is gone cannot close themselves. This is the
            # only periodic sweep, so the census stays honest between restarts.
            REGISTRY.reap_abandoned()
            # Second net: a socket whose owner is still alive but has not used it
            # inside the idle budget. Returning it here beats letting the server's
            # idle_session_timeout close it behind the owner's back.
            REGISTRY.reap_idle(idle_socket_budget_s())
            conn = snapshot_connection_metrics(db)
            payload["DB_ACTIVE_CONNECTIONS"] = conn.get("DB_ACTIVE_CONNECTIONS")
            payload["DB_CONNECTIONS_LOCAL"] = conn.get("DB_CONNECTIONS_COUNT")
            payload["DB_CONNECTIONS_MAX"] = conn.get("DB_CONNECTIONS_MAX")
            payload["DB_CONNECTIONS_REAPED"] = conn.get("DB_CONNECTIONS_REAPED")
            payload["DB_CONNECTIONS_IDLE_REAPED"] = conn.get("DB_CONNECTIONS_IDLE_REAPED")
            payload["DB_CONNECTIONS_LEAKED"] = conn.get("DB_CONNECTIONS_LEAKED")
            payload["DB_CONNECTIONS_ABANDONED"] = conn.get("DB_CONNECTIONS_ABANDONED")
            payload["DB_CONNECTIONS_OVERSTAYING"] = conn.get("DB_CONNECTIONS_OVERSTAYING")
            payload["DB_CONNECTIONS_HIGH_WATER"] = conn.get("DB_CONNECTIONS_HIGH_WATER")
            payload["DB_DISK_FREE_GB"] = None
            now = time.monotonic()
            local_commits = local_txn_commit_count()
            if self._txn_prev is not None and self._txn_prev_at > 0:
                elapsed = max(0.001, now - self._txn_prev_at)
                delta = max(0, local_commits - self._txn_prev[0])
                payload["DB_TXN_PER_MIN"] = round(delta * (60.0 / elapsed), 1)
            else:
                payload["DB_TXN_PER_MIN"] = None
            self._txn_prev = (local_commits, 0)
            self._txn_prev_at = now
            counters = query_pg_txn_counters(db)
            if counters is not None:
                cluster = int(counters[0] or 0) + int(counters[1] or 0)
                prev_cluster = getattr(self, "_txn_cluster_prev", None)
                prev_cluster_at = getattr(self, "_txn_cluster_prev_at", 0.0)
                if prev_cluster is not None and prev_cluster_at > 0:
                    elapsed_c = max(0.001, now - prev_cluster_at)
                    payload["DB_TXN_PER_MIN_CLUSTER"] = round(
                        max(0, cluster - prev_cluster) * (60.0 / elapsed_c), 1
                    )
                else:
                    payload["DB_TXN_PER_MIN_CLUSTER"] = None
                self._txn_cluster_prev = cluster
                self._txn_cluster_prev_at = now
        except Exception:
            _LOGGER.debug("metrics db skipped", exc_info=True)

    def _sample_saf(self, payload: dict[str, Any]) -> None:
        try:
            from ..persistence import get_persistence_gateway

            gateway = get_persistence_gateway()
            snap = gateway.snapshot()
            payload["SAF_QUEUE_DEPTH"] = int(snap.get("SAF_QUEUE_DEPTH") or 0)
            lag_s = snap.get("SAF_REPLICATION_LAG")
            payload["SAF_REPLICATION_LAG_MS"] = (
                None if lag_s is None else round(float(lag_s) * 1000.0, 1)
            )
            payload["SAF_DISK_BYTES"] = int(snap.get("SAF_DISK_BYTES") or 0)
            payload["SAF_PENDING_CAP_HITS"] = int(snap.get("SAF_PENDING_CAP_HITS") or 0)
            payload["SAF_DEADLETTER_COUNT"] = int(snap.get("SAF_DEADLETTER_COUNT") or 0)
            payload["SAF_SHED"] = 1.0 if snap.get("SAF_SHED") else 0.0
            payload["SAF_SHED_DROPPED"] = int(snap.get("SAF_SHED_DROPPED") or 0)
            self._sample_saf_rates(payload, gateway, snap)
            self._sample_ingest_age(payload, gateway, snap)
        except Exception:
            _LOGGER.debug("metrics saf skipped", exc_info=True)

    def _sample_saf_rates(self, payload: dict[str, Any], gateway, snap: dict[str, Any]) -> None:
        journal = getattr(gateway, "journal", None)
        enqueued = int(getattr(journal, "enqueued", 0) or 0)
        replicated = int(getattr(journal, "total_replicated", 0) or 0)
        now = time.monotonic()
        ingest_rate = 0.0
        drain_rate = 0.0
        if self._saf_rate_prev is not None and self._saf_rate_at > 0:
            elapsed = max(0.001, now - self._saf_rate_at)
            ingest_rate = max(0.0, enqueued - self._saf_rate_prev[0]) / elapsed
            drain_rate = max(0.0, replicated - self._saf_rate_prev[1]) / elapsed
        payload["SAF_INGEST_RATE"] = round(ingest_rate, 3)
        payload["SAF_DRAIN_RATE"] = round(drain_rate, 3)
        pending = int(snap.get("SAF_QUEUE_DEPTH") or payload.get("SAF_QUEUE_DEPTH") or 0)
        low = int(getattr(getattr(gateway, "config", None), "shed_low", 10_000) or 10_000)
        mismatch = pending > low and drain_rate < ingest_rate and ingest_rate > 0
        payload["SAF_RATE_MISMATCH"] = 1.0 if mismatch else 0.0
        self._saf_rate_prev = (enqueued, replicated)
        self._saf_rate_at = now

    def _sample_ingest_age(self, payload: dict[str, Any], gateway, snap: dict[str, Any]) -> None:
        from .. import PyAutomation

        app = PyAutomation()
        running = self._acquisition_running(app)
        ingest_age_s = float(snap.get("SAF_TAG_INGEST_AGE_S") or 0.0)
        mono = float(getattr(getattr(gateway, "journal", None), "last_tag_ingest_mono", 0.0) or 0.0)
        if not running:
            payload["SAF_INGEST_AGE_MS"] = 0.0
            return
        if mono <= 0:
            payload["SAF_INGEST_AGE_MS"] = round((time.monotonic() - self._started_at) * 1000.0, 1)
        else:
            payload["SAF_INGEST_AGE_MS"] = round(ingest_age_s * 1000.0, 1)

    def _acquisition_running(self, app) -> bool:
        try:
            manager = getattr(app, "machine_manager", None)
            machines = manager.get_machines() if manager is not None else []
            for machine in machines or []:
                state = getattr(machine, "current_state", None)
                value = getattr(state, "value", state)
                if str(value or "").lower() == "running":
                    return True
        except Exception:
            _LOGGER.debug("metrics acquisition running probe skipped", exc_info=True)
        return False

    def _sample_field(self, payload: dict[str, Any]) -> None:
        try:
            from datetime import datetime, timezone

            from .. import PyAutomation
            from ..timebase import ensure_utc

            app = PyAutomation()
            cvt = getattr(app, "cvt", None)
            engine = getattr(cvt, "_cvt", cvt)
            tags = getattr(engine, "_tags", None) or {}
            now = datetime.now(timezone.utc)
            max_age_ms = 0.0
            stale = False
            for tag in tags.values():
                namespace = getattr(tag, "node_namespace", None)
                scan = getattr(tag, "scan_time", None)
                if not namespace or not scan:
                    continue
                name = str(getattr(tag, "name", "") or "")
                if name.startswith("SYS."):
                    continue
                stamp = getattr(tag, "timestamp", None)
                if stamp is None:
                    continue
                try:
                    stamp = ensure_utc(stamp)
                    age_ms = max(0.0, (now - stamp).total_seconds() * 1000.0)
                except Exception:
                    continue
                try:
                    scan_ms = float(scan)
                except (TypeError, ValueError):
                    continue
                threshold_ms = max(5000.0, 3.0 * scan_ms)
                if age_ms > max_age_ms:
                    max_age_ms = age_ms
                if age_ms > threshold_ms:
                    stale = True
            payload["FIELD_MAX_AGE_MS"] = round(max_age_ms, 1)
            payload["FIELD_STALE"] = 1.0 if stale else 0.0
        except Exception:
            _LOGGER.debug("metrics field stale skipped", exc_info=True)

    def _sample_hub(self, payload: dict[str, Any]) -> None:
        try:
            from ..utils.hub_lag import snapshot_hub_lag_ms

            payload["HUB_LAG_MS"] = snapshot_hub_lag_ms()
        except Exception:
            payload.setdefault("HUB_LAG_MS", 0.0)

    def _sample_catalog(self, payload: dict[str, Any]) -> None:
        try:
            from ..catalog.metrics import snapshot as catalog_snapshot
            from ..catalog.replicator import get_catalog_replicator

            worker = get_catalog_replicator()
            if worker is not None:
                payload.update(worker.sync_status())
            else:
                snap = catalog_snapshot()
                payload["CATALOG_PENDING_ROWS"] = int(snap.get("CATALOG_PENDING_ROWS") or 0)
                payload["CATALOG_LAST_SYNC"] = snap.get("CATALOG_LAST_SYNC")
                payload["CATALOG_SYNC_ERRORS"] = int(snap.get("CATALOG_SYNC_ERRORS") or 0)
                payload["CATALOG_ORPHAN_ALARM"] = bool(snap.get("CATALOG_ORPHAN_ALARM"))
            payload["CATALOG_ORPHAN_ROWS"] = int(payload.get("CATALOG_PENDING_ROWS") or 0)
        except Exception:
            payload.setdefault("CATALOG_PENDING_ROWS", 0)
            payload.setdefault("CATALOG_LAST_SYNC", None)
            payload.setdefault("CATALOG_SYNC_ERRORS", 0)
            payload.setdefault("CATALOG_ORPHAN_ALARM", False)
            payload.setdefault("CATALOG_ORPHAN_ROWS", 0)

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
            derived = 0
            try:
                for row in app.cvt.get_tags() or []:
                    name = str((row or {}).get("name") or "")
                    if name.endswith(".f"):
                        derived += 1
            except Exception:
                derived = 0
            payload["DERIVED_TAGS_COUNT"] = derived
        except Exception:
            _LOGGER.debug("metrics acquisition skipped", exc_info=True)
            payload.setdefault("DERIVED_TAGS_COUNT", 0)

    def _sample_workers(self, payload: dict[str, Any]) -> None:
        try:
            from ..utils.ops_controls import worker_snapshot

            payload["WORKERS"] = worker_snapshot()
        except Exception:
            payload.setdefault("WORKERS", {})

    def _sample_clock(self, payload: dict[str, Any]) -> None:
        try:
            from .. import PyAutomation

            worker = getattr(PyAutomation(), "ntp_worker", None)
            if worker is None:
                payload["clock"] = {"synced": False, "offset_ms": None, "enabled": False}
                payload["HOST_NTP_OFFSET_MS"] = None
                payload["HOST_NTP_ABS_OFFSET_MS"] = None
                payload["HOST_NTP_SYNCED"] = 0.0
                return
            status = worker.get_status()
            offset = status.get("offset_ms")
            abs_offset = None
            if offset is not None:
                try:
                    abs_offset = abs(float(offset))
                except (TypeError, ValueError):
                    abs_offset = None
            payload["clock"] = {
                "enabled": bool(status.get("enabled")),
                "synced": bool(status.get("synced")),
                "warn": bool(status.get("warn")),
                "offset_ms": offset,
            }
            payload["HOST_NTP_OFFSET_MS"] = offset
            payload["HOST_NTP_ABS_OFFSET_MS"] = abs_offset
            payload["HOST_NTP_SYNCED"] = 1.0 if status.get("synced") else 0.0
        except Exception:
            _LOGGER.debug("metrics clock skipped", exc_info=True)

    def _sample_peers(self, payload: dict[str, Any]) -> None:
        payload.setdefault("HOST_PEER_DOWN", 0.0)
        payload.setdefault("HOST_PEER_DOWN_COUNT", 0)
        payload.setdefault("HOST_PEER_DOWN_IDS", [])
        try:
            from .. import PyAutomation
            from ..node_scope import get_node_scope

            app = PyAutomation()
            if not app.is_db_connected():
                return
            scope = get_node_scope()
            if scope is None or not getattr(scope, "is_valid", False):
                return
            stale_s = 90.0
            raw = os.environ.get("AUTOMATION_PEER_STALE_S")
            if raw not in (None, ""):
                try:
                    stale_s = max(15.0, float(raw))
                except (TypeError, ValueError):
                    stale_s = 90.0
            app.db_manager.heartbeat_node(scope.node_id)
            ids = app.db_manager.list_stale_peer_ids(
                scope.node_id, older_than_s=stale_s
            )
            payload["HOST_PEER_DOWN_COUNT"] = len(ids)
            payload["HOST_PEER_DOWN_IDS"] = ids
            payload["HOST_PEER_DOWN"] = 1.0 if ids else 0.0
        except Exception:
            _LOGGER.debug("metrics peers skipped", exc_info=True)
