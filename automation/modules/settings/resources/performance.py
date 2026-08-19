from flask_restx import Namespace, Resource, fields
from .... import PyAutomation
from ....extensions.api import api
from ....extensions import _api as Api

ns = Namespace("SettingsPerformance", description="Node performance alarm thresholds")
app = PyAutomation()

alarm_item_model = api.model(
    "performance_alarm_item",
    {
        "key": fields.String(required=False),
        "enabled": fields.Boolean(required=False),
        "threshold": fields.Float(required=False),
        "debounce": fields.Integer(required=False),
        "debounce_count": fields.Integer(required=False),
    },
)

performance_settings_model = api.model(
    "performance_settings_model",
    {
        "enabled": fields.Boolean(required=False),
        "debounce_count": fields.Integer(required=False, min=1, max=12),
        "debounceCount": fields.Integer(required=False),
        "cpuThreshold": fields.Float(required=False),
        "diskThreshold": fields.Float(required=False),
        "safQueueThreshold": fields.Float(required=False),
        "safLagThreshold": fields.Float(required=False),
        "metricsAgeThreshold": fields.Float(required=False),
        "dbConnThreshold": fields.Float(required=False),
        "http5xxThreshold": fields.Float(required=False),
        "perf_alarms_enabled": fields.Boolean(required=False),
        "perf_debounce_count": fields.Integer(required=False),
        "perf_cpu_enabled": fields.Boolean(required=False),
        "perf_cpu_threshold": fields.Float(required=False),
        "perf_disk_enabled": fields.Boolean(required=False),
        "perf_disk_threshold": fields.Float(required=False),
        "perf_saf_queue_enabled": fields.Boolean(required=False),
        "perf_saf_queue_threshold": fields.Float(required=False),
        "perf_saf_lag_enabled": fields.Boolean(required=False),
        "perf_saf_lag_threshold": fields.Float(required=False),
        "perf_metrics_age_enabled": fields.Boolean(required=False),
        "perf_metrics_age_threshold": fields.Float(required=False),
        "perf_db_conn_enabled": fields.Boolean(required=False),
        "perf_db_conn_threshold": fields.Float(required=False),
        "perf_http_5xx_enabled": fields.Boolean(required=False),
        "perf_http_5xx_threshold": fields.Float(required=False),
        "alarms": fields.List(fields.Nested(alarm_item_model), required=False),
    },
)


@ns.route("/performance")
class SettingsPerformanceResource(Resource):
    @api.doc(security="apikey", description="Returns node performance alarm thresholds.")
    @Api.token_required(auth=True)
    @Api.auth_roles(["admin", "supervisor", "sudo"])
    def get(self):
        try:
            return app.get_performance_alarm_config(), 200
        except Exception as exc:
            return {"message": str(exc)}, 500

    @api.doc(security="apikey", description="Updates node performance alarm thresholds (admin/supervisor).")
    @Api.token_required(auth=True)
    @Api.auth_roles(["admin", "supervisor", "sudo"])
    @ns.expect(performance_settings_model)
    def put(self):
        data = api.payload or {}
        try:
            config = app.update_performance_alarm_config(**data)
            from ....utils.system_event_audit import clip, persist_system_event
            from ....extensions import _api as ApiExt

            user = ApiExt.get_current_user()
            persist_system_event(
                message="Performance alarm settings updated",
                description=clip(
                    f"enabled={config.get('enabled')} debounce={config.get('debounce_count')}",
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
