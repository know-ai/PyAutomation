# -*- coding: utf-8 -*-
from flask_restx import Namespace, Resource

from ....extensions.api import api
from ....health import get_database_health_service
from ....health.interfaces import IReconnectionHandler

ns = Namespace("System", description="Operator system actions")


@ns.route("/reconnect_db")
class SystemReconnectDbResource(Resource):
    @api.doc(
        security=None,
        description="Rebind the remote historian using the stored configuration. Does not accept credentials in the body.",
    )
    @api.response(200, "Reconnect succeeded")
    @api.response(503, "Remote database still unreachable")
    def post(self):
        """HMI 'Reconnect now' button. SAF journal is not reset."""
        provider = get_database_health_service()
        if not isinstance(provider, IReconnectionHandler):
            return {
                "status": "error",
                "connected": False,
                "latency_ms": None,
                "message": "Reconnect is not available",
            }, 503
        snapshot = provider.reconnect()
        return snapshot.as_dict(), 200 if snapshot.connected else 503
