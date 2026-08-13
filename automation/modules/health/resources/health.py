from flask_restx import Namespace, Resource
from .... import PyAutomation
from ....extensions.api import api

ns = Namespace("Health", description="Service health and readiness checks")
app = PyAutomation()


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


