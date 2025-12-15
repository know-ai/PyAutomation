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


