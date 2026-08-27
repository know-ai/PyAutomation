from flask_restx import Namespace, Resource, fields
from flask import request
from .... import PyAutomation
from ....extensions.api import api
from ....extensions import _api as Api
from ....utils.ops_controls import (
    OpsControlError,
    catalog_clean_orphans,
    catalog_sync,
    rebuild_derived_tags,
    require_control_role,
    require_destructive_role,
    restart_worker,
    saf_reset,
    saf_retry,
    update_runtime_settings,
)

ns = Namespace("Admin", description="Hot operational controls for the node performance view")
app = PyAutomation()

restart_model = api.model(
    "admin_worker_restart",
    {
        "name": fields.String(required=False, description="LoggerWorker | CatalogReplicator | MetricsSampler | ReplicationWorker"),
        "reason": fields.String(required=False),
    },
)

saf_reset_model = api.model(
    "admin_saf_reset",
    {
        "confirm": fields.Boolean(required=True),
        "reason": fields.String(required=False),
    },
)

saf_retry_model = api.model(
    "admin_saf_retry",
    {"reason": fields.String(required=False)},
)

orphan_model = api.model(
    "admin_catalog_orphans",
    {
        "age_minutes": fields.Integer(required=False, default=10),
        "reason": fields.String(required=False),
    },
)

settings_model = api.model(
    "admin_runtime_settings",
    {
        "SAF_RING_MAXSIZE": fields.Integer(required=False),
        "saf_ring_maxsize": fields.Integer(required=False),
        "REPLICATE_RETRY_LIMIT": fields.Integer(required=False),
        "replicate_retry_limit": fields.Integer(required=False),
        "reason": fields.String(required=False),
    },
)


def _user():
    return Api.get_current_user()


def _payload() -> dict:
    return dict(api.payload or request.get_json(silent=True) or {})


def _handle(exc):
    if isinstance(exc, OpsControlError):
        return {"message": str(exc)}, 400
    if isinstance(exc, PermissionError):
        return {"message": str(exc)}, 403
    return {"message": str(exc)}, 500


@ns.route("/workers/restart")
class AdminWorkerRestartResource(Resource):
    @api.doc(security="apikey", description="Restart LoggerWorker, CatalogReplicator, MetricsSampler or ReplicationWorker.")
    @Api.token_required(auth=True)
    @Api.auth_roles(["admin", "supervisor", "sudo"])
    @ns.expect(restart_model)
    def post(self):
        user = _user()
        try:
            require_control_role(user)
            data = _payload()
            name = data.get("name") or request.args.get("name")
            return restart_worker(name, user=user, reason=data.get("reason")), 202
        except Exception as exc:
            return _handle(exc)


@ns.route("/saf/retry")
class AdminSafRetryResource(Resource):
    @api.doc(security="apikey", description="Force one SAF replication cycle.")
    @Api.token_required(auth=True)
    @Api.auth_roles(["admin", "supervisor", "sudo"])
    @ns.expect(saf_retry_model)
    def post(self):
        user = _user()
        try:
            require_control_role(user)
            data = _payload()
            return saf_retry(user=user, reason=data.get("reason")), 202
        except Exception as exc:
            return _handle(exc)


@ns.route("/saf/reset")
class AdminSafResetResource(Resource):
    @api.doc(security="apikey", description="Drop PENDING SAF samples. Requires confirm=true.")
    @Api.token_required(auth=True)
    @Api.auth_roles(["admin", "sudo"])
    @ns.expect(saf_reset_model)
    def post(self):
        user = _user()
        try:
            require_destructive_role(user)
            data = _payload()
            return saf_reset(
                confirm=bool(data.get("confirm")),
                user=user,
                reason=data.get("reason"),
            ), 200
        except Exception as exc:
            return _handle(exc)


@ns.route("/catalog/sync")
class AdminCatalogSyncResource(Resource):
    @api.doc(security="apikey", description="Force a catalog replicator cycle.")
    @Api.token_required(auth=True)
    @Api.auth_roles(["admin", "supervisor", "sudo"])
    def post(self):
        user = _user()
        try:
            require_control_role(user)
            data = _payload()
            return catalog_sync(user=user, reason=data.get("reason")), 202
        except Exception as exc:
            return _handle(exc)


@ns.route("/catalog/clean-orphans")
class AdminCatalogOrphansResource(Resource):
    @api.doc(security="apikey", description="Drop pending catalog orphans older than N minutes.")
    @Api.token_required(auth=True)
    @Api.auth_roles(["admin", "sudo"])
    @ns.expect(orphan_model)
    def post(self):
        user = _user()
        try:
            require_destructive_role(user)
            data = _payload()
            return catalog_clean_orphans(
                age_minutes=int(data.get("age_minutes") or 10),
                user=user,
                reason=data.get("reason"),
            ), 200
        except Exception as exc:
            return _handle(exc)


@ns.route("/tags/rebuild-derived")
class AdminRebuildDerivedResource(Resource):
    @api.doc(security="apikey", description="Ensure wavelet .f tags and drop orphans.")
    @Api.token_required(auth=True)
    @Api.auth_roles(["admin", "supervisor", "sudo"])
    def post(self):
        user = _user()
        try:
            require_control_role(user)
            data = _payload()
            return rebuild_derived_tags(user=user, reason=data.get("reason")), 202
        except Exception as exc:
            return _handle(exc)


@ns.route("/settings/update")
class AdminSettingsUpdateResource(Resource):
    @api.doc(security="apikey", description="Hot-update SAF ring size or replicate retry limit.")
    @Api.token_required(auth=True)
    @Api.auth_roles(["admin", "supervisor", "sudo"])
    @ns.expect(settings_model)
    def post(self):
        user = _user()
        try:
            require_control_role(user)
            return update_runtime_settings(_payload(), user=user), 200
        except Exception as exc:
            return _handle(exc)
