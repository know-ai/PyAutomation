from flask_restx import Namespace, Resource, fields
from .... import PyAutomation
from ....extensions.api import api
from ....extensions import _api as Api

ns = Namespace("SettingsClock", description="NTP clock monitor configuration")
app = PyAutomation()

clock_settings_model = api.model(
    "clock_settings_model",
    {
        "ntp_servers": fields.String(required=False, description="CSV list of NTP servers"),
        "ntp_check_interval_s": fields.Integer(required=False, min=60, max=86400),
        "ntp_warn_offset_ms": fields.Integer(required=False, min=1),
        "ntp_alarm_offset_ms": fields.Integer(required=False, min=1),
        "ntp_step_threshold_ms": fields.Integer(required=False, min=100),
        "ntp_fail_closed": fields.Boolean(required=False),
        "ntp_enabled": fields.Boolean(required=False),
        "ntp_auth_type": fields.String(
            required=False,
            description="none | symmetric | nts (symmetric/nts not yet supported in probe)",
        ),
    },
)


@ns.route("/clock")
class SettingsClockResource(Resource):
    @api.doc(security="apikey", description="Returns NTP monitor configuration.")
    @Api.token_required(auth=True)
    def get(self):
        try:
            return app.get_ntp_config(), 200
        except Exception as exc:
            return {"message": str(exc)}, 500

    @api.doc(security="apikey", description="Updates NTP monitor configuration (admin).")
    @Api.token_required(auth=True)
    @Api.auth_roles(["admin"])
    @ns.expect(clock_settings_model)
    def put(self):
        data = api.payload or {}
        try:
            config = app.update_ntp_config(**data)
            from ....utils.system_event_audit import clip, persist_system_event
            from ....extensions import _api as ApiExt

            user = ApiExt.get_current_user()
            persist_system_event(
                message="NTP settings updated",
                description=clip(
                    f"servers={config.get('ntp_servers_list')} interval={config.get('ntp_check_interval_s')}s",
                    256,
                ),
                classification="System",
                priority=2,
                criticity=2,
                user=user,
            )
            return config, 200
        except ValueError as exc:
            return {"message": str(exc)}, 400
        except Exception as exc:
            return {"message": str(exc)}, 500
