# -*- coding: utf-8 -*-
"""History / TagValue query endpoints (reconnect backfill, etc.)."""
from __future__ import annotations

from flask_restx import Namespace, Resource, reqparse

from .... import PyAutomation
from ....extensions.api import api
from ....extensions import _api as Api
from ...health.require_db import require_remote_db

ns = Namespace("History", description="Historical TagValue queries")
app = PyAutomation()

backfill_parser = reqparse.RequestParser()
backfill_parser.add_argument(
    "tags",
    type=str,
    location="args",
    required=True,
    help="Comma-separated tag names",
)
backfill_parser.add_argument(
    "from",
    type=str,
    location="args",
    required=True,
    dest="from_ts",
    help="Range start (epoch milliseconds or ISO-8601)",
)
backfill_parser.add_argument(
    "to",
    type=str,
    location="args",
    required=True,
    dest="to_ts",
    help="Range end (epoch milliseconds or ISO-8601)",
)
backfill_parser.add_argument(
    "limit",
    type=int,
    location="args",
    required=False,
    default=1000,
    help="Max points per tag (default 1000, max 5000)",
)


def _parse_bound_ms(raw: str) -> int | None:
    if raw is None:
        return None
    text = str(raw).strip()
    if not text:
        return None
    try:
        if text.isdigit() or (text.startswith("-") and text[1:].isdigit()):
            return int(text)
        as_float = float(text)
        # Heuristic: values below year-2001 seconds are treated as seconds.
        if as_float < 1e12:
            return int(as_float * 1000)
        return int(as_float)
    except (TypeError, ValueError):
        pass
    from datetime import datetime, timezone

    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return int(parsed.timestamp() * 1000)


@ns.route("/backfill")
class HistoryBackfillResource(Resource):
    @api.doc(
        security="apikey",
        description=(
            "Raw TagValue samples for HMI Socket.IO reconnect backfill. "
            "Timestamps are ISO-8601 UTC (same format as on.tag)."
        ),
    )
    @api.response(200, "Success")
    @api.response(400, "Invalid parameters")
    @api.response(503, "Remote database unavailable")
    @require_remote_db
    @Api.token_required(auth=True)
    @ns.expect(backfill_parser)
    def get(self):
        args = backfill_parser.parse_args()
        tags = [t.strip() for t in str(args.get("tags") or "").split(",") if t.strip()]
        if not tags:
            return {"message": "tags is required"}, 400
        if len(tags) > 64:
            return {"message": "too many tags (max 64)"}, 400

        start_ms = _parse_bound_ms(args.get("from_ts"))
        stop_ms = _parse_bound_ms(args.get("to_ts"))
        if start_ms is None or stop_ms is None:
            return {"message": "from/to must be epoch ms or ISO-8601"}, 400

        limit = args.get("limit") or 1000
        data = app.logger_engine.read_backfill(
            tags,
            start_ms,
            stop_ms,
            limit_per_tag=limit,
        )
        return {"data": data}, 200
