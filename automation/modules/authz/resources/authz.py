from flask import request
from flask_restx import Namespace, Resource, reqparse

from ....extensions.api import api
from ....extensions import _api as Api
from ....authz.catalog import catalog_tree
from ....authz.engine import permissions_for
from ....authz.grants import list_grants, upsert_grant
from ....authz.invalidate import notify_authz_invalidated
from ....authz.store import cache_version, reload_cache
from ....modules.users.users import Users as CVTUsers
from ....modules.users.roles import roles as cvt_roles
from ....utils.system_user import is_system_username

ns = Namespace("Authz", description="Granular authorization (ACL)")
users = CVTUsers()

_grants_parser = reqparse.RequestParser()
_grants_parser.add_argument("subject_type", type=str, location="args", required=False)
_grants_parser.add_argument("subject_id", type=str, location="args", required=False)


def _preview_subject(subject_type: str, subject_id: str):
    stype = str(subject_type or "").strip().lower()
    sid = str(subject_id or "").strip()
    if stype == "user":
        return users.get(identifier=sid) or users.get_by_username(username=sid)
    if stype == "role":
        role = cvt_roles.get(id=sid) or cvt_roles.get_by_name(name=sid)
        if role is None:
            return None
        from ....modules.users.users import User

        return User(
            username=f"preview:{role.name}",
            role=role,
            email="",
            password="",
            identifier="preview",
        )
    return None


@ns.route("/me")
class AuthzMeResource(Resource):
    @api.doc(security="apikey", description="Effective HMI views and REST keys for the current session.")
    @api.response(200, "Success")
    @Api.token_required(auth=True)
    def get(self):
        current_user = Api.get_current_user()
        if current_user is None:
            return {"message": "Invalid token", "code": "SESSION_INVALID"}, 401
        from flask import current_app

        payload = permissions_for(current_user, current_app._get_current_object())
        payload["username"] = getattr(current_user, "username", None)
        role = getattr(current_user, "role", None)
        payload["role"] = getattr(role, "name", None)
        payload["is_system"] = is_system_username(getattr(current_user, "username", None))
        return payload, 200


@ns.route("/catalog")
class AuthzCatalogResource(Resource):
    @api.doc(security="apikey", description="ACL catalog tree for the administration panel.")
    @api.response(200, "Success")
    @Api.token_required(auth=True)
    @Api.authorize(resource_key="hmi:view.authz", action="view")
    def get(self):
        from flask import current_app

        return catalog_tree(current_app._get_current_object()), 200


@ns.route("/grants")
class AuthzGrantsResource(Resource):
    @api.doc(security="apikey", description="List grants for a role or user.")
    @api.response(200, "Success")
    @ns.expect(_grants_parser)
    @Api.token_required(auth=True)
    @Api.authorize(resource_key="hmi:view.authz", action="view")
    def get(self):
        args = _grants_parser.parse_args()
        return {
            "data": list_grants(
                subject_type=args.get("subject_type"),
                subject_id=args.get("subject_id"),
            )
        }, 200

    @api.doc(security="apikey", description="Upsert ACL grants. effect=default deletes the row.")
    @api.response(200, "Success")
    @Api.token_required(auth=True)
    @Api.authorize(resource_key="hmi:view.authz", action="use")
    def put(self):
        payload = request.get_json(silent=True) or {}
        subject_type = str(payload.get("subject_type") or "").strip().lower()
        subject_id = str(payload.get("subject_id") or "").strip()
        grants = payload.get("grants") or []
        if subject_type not in {"role", "user"} or not subject_id:
            return {"message": "subject_type and subject_id are required"}, 400
        if not isinstance(grants, list):
            return {"message": "grants must be a list"}, 400
        saved = []
        for item in grants:
            if not isinstance(item, dict):
                continue
            resource_key = item.get("resource_key")
            action = item.get("action")
            effect = item.get("effect")
            if not resource_key or not action:
                continue
            saved.append(upsert_grant(subject_type, subject_id, resource_key, action, effect))
        reload_cache(reason="put")
        version = notify_authz_invalidated(cache_version())
        return {"data": saved, "version": version}, 200


@ns.route("/preview")
class AuthzPreviewResource(Resource):
    @api.doc(security="apikey", description="Evaluate the ACL engine for an arbitrary subject.")
    @api.response(200, "Success")
    @Api.token_required(auth=True)
    @Api.authorize(resource_key="hmi:view.authz", action="view")
    def post(self):
        payload = request.get_json(silent=True) or {}
        subject_type = payload.get("subject_type")
        subject_id = payload.get("subject_id")
        subject = _preview_subject(subject_type, subject_id)
        if subject is None:
            return {"message": "Subject not found"}, 404
        from flask import current_app

        result = permissions_for(subject, current_app._get_current_object())
        result["subject_type"] = subject_type
        result["subject_id"] = subject_id
        return result, 200
