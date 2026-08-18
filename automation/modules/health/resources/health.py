from flask_restx import Namespace, Resource
from .... import PyAutomation
from ....extensions.api import api

ns = Namespace("Health", description="Service health and readiness checks")
app = PyAutomation()


def _event_rate_metrics() -> dict:
    try:
        from ....utils.audit_metrics import snapshot

        return snapshot()
    except Exception:
        return {
            "EVENTS_RATE_PER_MIN": 0.0,
            "EVENTS_RATE_ALERT": False,
            "EVENTS_RATE_ALERT_THRESHOLD": 30.0,
            "LOGS_RATE_PER_MIN": 0.0,
            "LOGS_RATE_ALERT": False,
            "LOGS_RATE_ALERT_THRESHOLD": 30.0,
        }


def _log_error_metrics() -> dict:
    try:
        from ....utils.log_filters import get_dedupe_filter

        filt = get_dedupe_filter()
        if filt is None:
            return {
                "LOG_ERROR_RATE_PER_MIN": 0.0,
                "LOG_ERROR_SUPPRESSED_PER_MIN": 0.0,
                "LOG_ERROR_ALERT": False,
            }
        return filt.snapshot()
    except Exception:
        return {
            "LOG_ERROR_RATE_PER_MIN": 0.0,
            "LOG_ERROR_SUPPRESSED_PER_MIN": 0.0,
            "LOG_ERROR_ALERT": False,
        }


@ns.route("/ping")
class HealthPingResource(Resource):
    @api.doc(description="Lightweight healthcheck endpoint used by container orchestrators.")
    @api.response(200, "Service is healthy")
    def get(self):
        """
        Returns a simple 200 OK payload indicating that the HTTP stack and
        core application are up and responding.

        This endpoint is intentionally lightweight and unauthenticated so it
        can be safely used by Docker/Kubernetes health checks.
        """
        return {
            "status": "ok",
            "service": "pyautomation",
            "detail": "HTTP stack and core application are responding"
        }, 200


def _system_rss_mb() -> float:
    try:
        import psutil
        return psutil.Process().memory_info().rss / (1024 * 1024)
    except Exception:
        pass
    try:
        import resource
        # Linux reports ru_maxrss in kilobytes.
        return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024
    except Exception:
        return 0.0


@ns.route("/system")
class HealthSystemResource(Resource):
    @api.doc(description="Process RSS, thread count, OPC monitored items, CVT tag count and observer counts.")
    @api.response(200, "System snapshot")
    def get(self):
        """Continuous health snapshot for soak / leak detection."""
        import threading

        rss_mb = _system_rss_mb()
        opc_monitored = 0
        opc_subscriptions = 0
        cvt_tag_count = 0
        pending_rows = 0
        alarm_count = 0
        pool_used = 0
        pending_cap_hits = 0
        lock_contention = 0
        tag_observer_count = 0
        machine_observer_count = 0
        try:
            opc_monitored = app.das.monitored_count()
            opc_subscriptions = len(getattr(app.das, "client_subscriptions", {}) or {})
        except Exception:
            pass
        try:
            cvt_tag_count = app.cvt.tag_count()
            lock_contention = app.cvt.lock_contention()
        except Exception:
            pass
        try:
            counts = app.cvt.observer_counts()
            tag_observer_count = int(counts.get("TAG_OBSERVER_COUNT") or 0)
            machine_observer_count = int(counts.get("MACHINE_OBSERVER_COUNT") or 0)
        except Exception:
            pass
        try:
            from ....persistence import get_persistence_gateway
            snapshot = get_persistence_gateway().snapshot()
            pending_rows = int(snapshot.get("SAF_QUEUE_DEPTH") or 0)
            pending_cap_hits = int(snapshot.get("SAF_PENDING_CAP_HITS") or 0)
        except Exception:
            pass
        try:
            alarm_count = app.alarm_manager.alarm_count()
        except Exception:
            pass
        try:
            db = getattr(app, "_db", None)
            in_use = getattr(db, "_in_use", None)
            if in_use is not None:
                pool_used = len(in_use)
        except Exception:
            pass
        try:
            from ....utils.db_connections import snapshot_connection_metrics

            conn_metrics = snapshot_connection_metrics(getattr(app, "_db", None))
        except Exception:
            conn_metrics = {
                "DB_CONNECTIONS_COUNT": 0,
                "DB_ACTIVE_CONNECTIONS": 0,
                "DB_NAMED_CONNECTIONS": None,
                "DB_CONNECTIONS_EXPECTED_MAX": 4,
                "DB_CONNECTIONS_ALERT": False,
                "DB_CONNECTIONS_ALERT_THRESHOLD": 10,
                "DB_INSTANCE_ID": None,
                "DB_APPLICATION_NAME": "PyAutomationIO",
            }
        try:
            db_connected = bool(app.is_db_connected())
        except Exception:
            db_connected = False
        return {
            "status": "ok",
            "service": "pyautomation",
            "is_db_connected": db_connected,
            "RSS_MB": round(rss_mb, 2),
            "THREAD_COUNT": threading.active_count(),
            "OPC_MONITORED_COUNT": opc_monitored,
            "CVT_TAG_COUNT": cvt_tag_count,
            "OPC_SUBSCRIPTION_COUNT": opc_subscriptions,
            "PENDING_ROWS": pending_rows,
            "ALARM_COUNT": alarm_count,
            "POOL_CONNECTIONS_USED": pool_used,
            "SAF_PENDING_CAP_HITS": pending_cap_hits,
            "CVT_LOCK_CONTENTION": lock_contention,
            "TAG_OBSERVER_COUNT": tag_observer_count,
            "MACHINE_OBSERVER_COUNT": machine_observer_count,
            **conn_metrics,
            **_log_error_metrics(),
            **_event_rate_metrics(),
        }, 200


@ns.route("/db")
class HealthDatabaseResource(Resource):
    @api.doc(description="Remote historian reachability (SELECT 1, short timeout). Unauthenticated so the HMI can poll while PostgreSQL is down.")
    @api.response(200, "Probe executed")
    def get(self):
        """UI visibility probe. Always HTTP 200; ``connected`` carries the truth.

        Returning 503 here would collide with historian 503 handling and with
        orchestrator liveness (use ``/health/ping`` / ``/health/saf`` for that).
        """
        from ....health import get_database_health_service

        snapshot = get_database_health_service().snapshot()
        return snapshot.as_dict(), 200


@ns.route("/saf")
class HealthSafResource(Resource):
    @api.doc(description="Store-and-Forward journal health (depth, lag, disk, circuit).")
    @api.response(200, "SAF probe executed")
    @api.response(503, "SAF backpressure or disk-full")
    def get(self):
        """Nuclear durability probe. Red if history cannot be journaled."""
        from ....persistence import get_persistence_gateway

        snapshot = dict(get_persistence_gateway().snapshot())
        status_code = 503 if snapshot.get("status") == "critical" else 200
        return snapshot, status_code


