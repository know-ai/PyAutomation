# -*- coding: utf-8 -*-
"""IRemoteDB adapter over the existing Peewee historian models.

Insert dialect logic lives in IdempotentBatchInserter (OCP). Tag JSON → SQL
rows live in TagValuePayloadMapper so the inserter stays generic.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Callable, Mapping, Sequence

from .idempotent_insert import IdempotentBatchInserter, IIdempotentInserter
from .records import DOMAIN, canonical_sample_uuid

VALUE_KEYS = ("value", "val", "v", "magnitude", "value_str")
TIMESTAMP_KEYS = ("timestamp", "ts", "time")
SECONDS_CEILING = 10_000_000_000


def coerce_tag_value(raw: Any) -> float | None:
    if raw is None:
        return None
    if hasattr(raw, "value"):
        raw = raw.value
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


def extract_tag_value(payload: Mapping[str, Any]) -> float | None:
    for key in VALUE_KEYS:
        if key in payload and payload[key] is not None:
            return coerce_tag_value(payload[key])
    return None


def coerce_tag_timestamp(raw: Any) -> datetime | None:
    if raw is None or raw == "":
        return None
    if isinstance(raw, datetime):
        if raw.tzinfo is None:
            return raw.replace(tzinfo=timezone.utc)
        return raw.astimezone(timezone.utc)
    if isinstance(raw, (int, float)):
        numeric = float(raw)
        if numeric > SECONDS_CEILING:
            numeric /= 1_000_000.0
        return datetime.fromtimestamp(numeric, tz=timezone.utc)
    try:
        parsed = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def extract_tag_timestamp(payload: Mapping[str, Any]) -> datetime | None:
    for key in TIMESTAMP_KEYS:
        if key in payload and payload[key] is not None:
            return coerce_tag_timestamp(payload[key])
    return None


class TagValuePayloadMapper:
    """Journal JSON → TagValue insert dicts. Open for new tag schemas; closed for the inserter."""

    def __init__(
        self,
        resolve_tag: Callable[[Any], Any] | None = None,
        resolve_unit: Callable[[Any], Any] | None = None,
    ):
        self._resolve_tag = resolve_tag
        self._resolve_unit = resolve_unit

    def to_rows(self, payloads: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
        logger = logging.getLogger("pyautomation")
        rows: list[dict[str, Any]] = []
        for item in payloads:
            row = self._map_one(item, logger)
            if row is not None:
                rows.append(row)
        if rows:
            sample = {
                "tag": getattr(rows[0].get("tag"), "name", rows[0].get("tag")),
                "value": rows[0].get("value"),
                "timestamp": rows[0].get("timestamp"),
                "sample_uuid": rows[0].get("sample_uuid"),
            }
            logger.debug("SAF TagValuePayloadMapper mapped_row=%s count=%s", sample, len(rows))
        return rows

    def _map_one(self, item: Mapping[str, Any], logger) -> dict[str, Any] | None:
        tag_name = item.get("tag") or item.get("tag_name")
        tag = self._lookup_tag(tag_name)
        if not tag:
            logger.warning("SAF skip tag payload: tag %s not in remote Tags", tag_name)
            return None
        unit = self._lookup_unit(tag)
        if unit is None:
            logger.warning("SAF skip tag %s: missing unit/display_unit", tag_name)
            return None
        value = extract_tag_value(item)
        if value is None:
            logger.warning(
                "SAF skip tag %s: value missing or not numeric (%r)",
                tag_name,
                item.get("value"),
            )
            return None
        timestamp = extract_tag_timestamp(item)
        if timestamp is None:
            logger.warning(
                "SAF skip tag %s: timestamp missing or unparsable (%r)",
                tag_name,
                item.get("timestamp"),
            )
            return None
        return {
            "tag": tag,
            "value": value,
            "timestamp": timestamp,
            "unit": unit,
            "sample_uuid": canonical_sample_uuid(
                item.get("sample_uuid") or item.get("idempotency_key")
            ),
        }

    def _lookup_tag(self, name):
        if self._resolve_tag is not None:
            return self._resolve_tag(name)
        from ..dbmodels.tags import Tags

        return Tags.read_by_name(name)

    def _lookup_unit(self, tag):
        if self._resolve_unit is not None:
            return self._resolve_unit(tag)
        from ..dbmodels.tags import Units

        unit = Units.get_or_none(id=tag.display_unit.id) if getattr(tag, "display_unit", None) else None
        if unit is None and getattr(tag, "unit", None) is not None:
            unit = tag.unit
        return unit


class PeeweeRemoteDB:
    """Distribution plane. Never owns durability — that is the local journal."""

    def __init__(self, tag_inserter: IIdempotentInserter | None = None, tag_mapper=None):
        self._tag_inserter = tag_inserter or IdempotentBatchInserter()
        self._tag_mapper = tag_mapper or TagValuePayloadMapper()

    def is_reachable(self) -> bool:
        try:
            from ..logger.datalogger import DataLoggerEngine

            logger = DataLoggerEngine().logger
            return bool(logger.check_connectivity())
        except Exception:
            return False

    def write_batch(self, domain: str, payloads: Sequence[Mapping]) -> int:
        if not payloads:
            return 0
        if domain == DOMAIN.TAG:
            return self.batch_insert_with_dedupe(payloads)
        if domain == DOMAIN.EVENT:
            return self._write_events(payloads)
        if domain == DOMAIN.ALARM_SUMMARY:
            return self._write_alarm_creates(payloads)
        if domain == DOMAIN.ALARM_SUMMARY_UPDATE:
            return self._write_alarm_updates(payloads)
        if domain == DOMAIN.LOG:
            return self._write_logs(payloads)
        raise ValueError(f"Unsupported SAF domain: {domain}")

    def batch_insert_with_dedupe(self, payloads: Sequence[Mapping]) -> int:
        rows = self._tag_mapper.to_rows(payloads)
        if not rows:
            return 0
        return self._tag_inserter.insert_tag_values(rows)

    def _write_events(self, payloads: Sequence[Mapping]) -> int:
        from ..dbmodels.events import Events

        written = 0
        for item in payloads:
            user = _user_for_username(item.get("username") or "system")
            if user is None:
                continue
            created, _ = Events.create(
                message=item.get("message"),
                user=user,
                description=item.get("description"),
                classification=item.get("classification"),
                priority=item.get("priority"),
                criticity=item.get("criticity"),
                timestamp=_parse_dt(item.get("timestamp")),
            )
            if created is not None:
                written += 1
        return written

    def _write_alarm_creates(self, payloads: Sequence[Mapping]) -> int:
        from ..dbmodels.alarms import AlarmSummary

        written = 0
        for item in payloads:
            created = AlarmSummary.create(
                name=item.get("name"),
                state=item.get("state"),
                timestamp=_parse_dt(item.get("timestamp")),
                ack_timestamp=_parse_dt(item.get("ack_timestamp")),
            )
            if created is not None:
                written += 1
        return written

    def _write_alarm_updates(self, payloads: Sequence[Mapping]) -> int:
        from ..dbmodels.alarms import AlarmStates, AlarmSummary

        written = 0
        for item in payloads:
            alarm = AlarmSummary.read_by_name(name=item.get("name"))
            if not alarm:
                continue
            fields = {}
            if item.get("ack_timestamp"):
                fields["ack_time"] = _parse_dt(item.get("ack_timestamp"))
            if item.get("state"):
                alarm_state = AlarmStates.get_or_none(name=item["state"])
                if alarm_state:
                    fields["state"] = alarm_state
            if fields:
                AlarmSummary.put(id=alarm.id, **fields)
                written += 1
        return written

    def _write_logs(self, payloads: Sequence[Mapping]) -> int:
        from ..dbmodels.logs import Logs

        written = 0
        for item in payloads:
            user = _user_for_username(item.get("username") or "system")
            if user is None:
                continue
            created, _ = Logs.create(
                message=item.get("message"),
                user=user,
                description=item.get("description"),
                classification=item.get("classification"),
                alarm_summary_id=item.get("alarm_summary_id"),
                event_id=item.get("event_id"),
                timestamp=_parse_dt(item.get("timestamp")),
            )
            if created is not None:
                written += 1
        return written


def _user_for_username(username: str):
    from ..dbmodels.users import Users
    from ..modules.users.roles import Role
    from ..modules.users.users import User, Users as UsersService

    memory_user = UsersService().get_by_username(username=username)
    if memory_user is not None:
        return memory_user
    db_user = Users.read_by_username(username=username)
    if db_user is None:
        return None
    role_name = getattr(getattr(db_user, "role", None), "name", "sudo") or "sudo"
    role_level = getattr(getattr(db_user, "role", None), "level", 0) or 0
    return User(
        username=db_user.username,
        role=Role(name=role_name, level=int(role_level)),
        email=getattr(db_user, "email", "") or "system@local",
        password="journal-replay",
        name=getattr(db_user, "name", "") or "",
        lastname=getattr(db_user, "lastname", "") or "",
    )


def _parse_dt(value):
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        logging.getLogger("pyautomation").warning("SAF remote datetime parse failed: %s", value)
        return None
