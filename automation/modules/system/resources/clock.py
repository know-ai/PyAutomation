from flask_restx import Namespace, Resource
from datetime import datetime, timezone
from .... import PyAutomation
from ....extensions.api import api
from ....extensions import _api as Api

ns = Namespace("SystemClock", description="Edge clock synchronization status")
app = PyAutomation()


def _clock_snapshot() -> dict:
    worker = getattr(app, "ntp_worker", None)
    status = worker.get_status() if worker is not None else {}
    config = app.get_ntp_config()
    return {
        **status,
        "config": {
            "ntp_servers": config.get("ntp_servers_list") or [],
            "ntp_check_interval_s": config.get("ntp_check_interval_s"),
            "ntp_warn_offset_ms": config.get("ntp_warn_offset_ms"),
            "ntp_alarm_offset_ms": config.get("ntp_alarm_offset_ms"),
            "ntp_fail_closed": config.get("ntp_fail_closed"),
            "ntp_enabled": config.get("ntp_enabled"),
            "effective_enabled": config.get("effective_enabled"),
        },
        "host_time_utc": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
    }


@ns.route("/clock")
class SystemClockResource(Resource):
    @api.doc(security="apikey", description="Full NTP monitor snapshot for the edge.")
    @Api.token_required(auth=True)
    def get(self):
        try:
            return _clock_snapshot(), 200
        except Exception as exc:
            return {"message": str(exc)}, 500


@ns.route("/clock/check")
class SystemClockCheckResource(Resource):
    @api.doc(security="apikey", description="Force an immediate NTP check (rate-limited).")
    @Api.token_required(auth=True)
    @Api.auth_roles(["admin", "supervisor"])
    def post(self):
        worker = getattr(app, "ntp_worker", None)
        if worker is None:
            return {"message": "NTP monitor worker is not running"}, 503
        try:
            result = worker.check_now(force=False)
            code = 200 if result.get("ok") else 429
            return result, code
        except Exception as exc:
            return {"message": str(exc)}, 500
