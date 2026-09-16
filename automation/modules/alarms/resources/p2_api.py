# -*- coding: utf-8 -*-
"""P2 API routes on the Alarms namespace. Context: API. Complexity: O(1)/O(1000)."""
from flask_restx import Resource, reqparse

from ....alarms.pagination import clamp_history_page_size
from ....alarms.p2.kpi import KPIComputer
from ....alarms.p2.suppression_types import SilenceType
from ....alarms.runtime import get_alarm_runtime
from ....extensions import _api as Api
from ....extensions.api import api
from .alarms import app, ns

priority_parser = reqparse.RequestParser()
priority_parser.add_argument("priority", type=int, required=True)
priority_parser.add_argument("reason", type=str, required=True)
priority_parser.add_argument("operator_id", type=int, required=False, default=0)

silence_parser = reqparse.RequestParser()
silence_parser.add_argument("duration_min", type=int, required=False, default=30)
silence_parser.add_argument("reason", type=str, required=True)
silence_parser.add_argument("operator_id", type=int, required=False, default=0)

kpi_hist_parser = reqparse.RequestParser()
kpi_hist_parser.add_argument("limit", type=int, location="args", default=100)


def _runtime():
    return get_alarm_runtime()


@ns.route("/kpi")
class AlarmsKpiResource(Resource):
    @api.doc(security="apikey", description="Incremental ISA 18.2 KPIs. Context: API. O(1000).")
    @Api.token_required(auth=True)
    def get(self):
        runtime = _runtime()
        snap = KPIComputer().compute(runtime.kpi)
        return snap, 200


@ns.route("/kpi/history")
class AlarmsKpiHistoryResource(Resource):
    @api.doc(security="apikey", description="KPI snapshots. page_size ≤ 1000.")
    @ns.expect(kpi_hist_parser)
    @Api.token_required(auth=True)
    def get(self):
        args = kpi_hist_parser.parse_args()
        limit = clamp_history_page_size(args.get("limit") or 100, default=100)
        limit = min(limit, 1000)
        hist = getattr(_runtime(), "kpi_history", None)
        rows = hist.get_history(limit) if hist is not None else []
        return {"items": rows[:limit], "page_size": limit}, 200


@ns.route("/<alarm_id>/priority")
class AlarmPriorityResource(Resource):
    @api.doc(security="apikey")
    @ns.expect(priority_parser)
    @Api.token_required(auth=True)
    def patch(self, alarm_id):
        args = priority_parser.parse_args()
        runtime = _runtime()
        try:
            runtime.priority.set_priority(
                alarm_id, int(args["priority"]), int(args.get("operator_id") or 0), args["reason"]
            )
        except ValueError as exc:
            return {"message": str(exc)}, 400
        alarm = app.alarm_manager.peek_alarm(id=alarm_id) or app.alarm_manager.peek_alarm(name=alarm_id)
        if alarm is not None:
            alarm.priority = int(args["priority"])
        return {"alarm_id": alarm_id, "priority": int(args["priority"])}, 200


def _apply_type(alarm_id, type_name, args):
    runtime = _runtime()
    reason = args.get("reason") or ""
    try:
        rec_id = runtime.suppression.apply(
            alarm_id,
            type_name,
            reason=reason,
            duration_min=args.get("duration_min") or 30,
            duration_h=24,
        )
    except ValueError as exc:
        return {"message": str(exc)}, 400
    return {"alarm_id": alarm_id, "suppression_id": rec_id, "type": type_name}, 200


@ns.route("/<alarm_id>/silence")
class AlarmSilenceResource(Resource):
    @api.doc(security="apikey")
    @ns.expect(silence_parser)
    @Api.token_required(auth=True)
    def post(self, alarm_id):
        args = silence_parser.parse_args()
        try:
            SilenceType().validate(duration_min=args.get("duration_min") or 30, reason=args.get("reason") or "")
        except ValueError as exc:
            return {"message": str(exc)}, 400
        return _apply_type(alarm_id, "silence", args)


@ns.route("/<alarm_id>/shelve")
class AlarmP2ShelveResource(Resource):
    @api.doc(security="apikey")
    @ns.expect(silence_parser)
    @Api.token_required(auth=True)
    def post(self, alarm_id):
        return _apply_type(alarm_id, "shelve", silence_parser.parse_args())


@ns.route("/<alarm_id>/disable")
class AlarmDisableResource(Resource):
    @api.doc(security="apikey")
    @ns.expect(silence_parser)
    @Api.token_required(auth=True)
    def post(self, alarm_id):
        return _apply_type(alarm_id, "disable", silence_parser.parse_args())


@ns.route("/<alarm_id>/oos")
class AlarmOosResource(Resource):
    @api.doc(security="apikey")
    @ns.expect(silence_parser)
    @Api.token_required(auth=True)
    def post(self, alarm_id):
        args = silence_parser.parse_args()
        if not str(args.get("reason") or "").strip():
            return {"message": "reason required"}, 400
        return _apply_type(alarm_id, "oos", args)


@ns.route("/<alarm_id>/suppression")
class AlarmSuppressionDeleteResource(Resource):
    @api.doc(security="apikey")
    @Api.token_required(auth=True)
    def delete(self, alarm_id):
        _runtime().suppression.release(alarm_id)
        return {"alarm_id": alarm_id, "suppressed": False}, 200
