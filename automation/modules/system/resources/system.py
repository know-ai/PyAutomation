# -*- coding: utf-8 -*-
from flask_restx import Namespace, Resource

from .... import PyAutomation
from ....extensions.api import api
from ....extensions import _api as Api
from ...health.require_db import require_remote_db
from ....health import get_database_health_service
from ....health.interfaces import IReconnectionHandler

app = PyAutomation()

ns = Namespace("System", description="Operator system actions")


def plant_timezone_payload():
    """Plant timezone for HMI presentation. Storage and logic stay UTC."""
    from .... import _TIMEZONE
    return {
        "timezone": _TIMEZONE,
        "role": "plant",
        "description": (
            "Plant timezone (AUTOMATION_TIMEZONE). Presentation default only; "
            "storage and business logic remain UTC."
        ),
    }


@ns.route("/timezone")
class SystemTimezoneResource(Resource):
    @api.doc(
        security=None,
        description="Returns AUTOMATION_TIMEZONE (plant timezone) for HMI presentation.",
    )
    @api.response(200, "Plant timezone")
    def get(self):
        """HMI display default: plant timezone. Does not affect historian UTC."""
        return plant_timezone_payload(), 200


@ns.route("/nodes")
class SystemNodesResource(Resource):
    @api.doc(
        security="apikey",
        description="Registered edge nodes and areas for plant-wide historical filters.",
    )
    @api.response(200, "Node list")
    @api.response(503, "Remote database unavailable")
    @require_remote_db
    @Api.token_required(auth=True)
    def get(self):
        """Plant topology: node_id, area, site. Not a runtime catalog."""
        return {"data": app.get_plant_nodes()}, 200


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
        try:
            from ....extensions import _api as Api
            from ....utils.system_event_audit import clip, persist_system_event

            user = Api.get_current_user()
            persist_system_event(
                message="Database reconnection attempted",
                description=clip(
                    f"source=hmi result={'ok' if snapshot.connected else 'failed'}",
                    256,
                ),
                classification="Database",
                priority=3,
                criticity=4 if not snapshot.connected else 2,
                user=user,
            )
        except Exception:
            pass
        return snapshot.as_dict(), 200 if snapshot.connected else 503
