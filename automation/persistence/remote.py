# -*- coding: utf-8 -*-
"""IRemoteDB adapter over the existing Peewee historian models.

Insert dialect logic lives in IdempotentBatchInserter (OCP). Tag JSON → SQL
rows live in TagValuePayloadMapper so the inserter stays generic.
"""
from __future__ import annotations

import logging
import inspect
import threading
from datetime import datetime, timezone
from typing import Any, Callable, Mapping, Sequence

from .idempotent_insert import AlarmSummaryInserter, IdempotentBatchInserter, IIdempotentInserter
from .records import DOMAIN, canonical_sample_uuid
from ..timebase import epoch_seconds_from_db_tick, quantize_datetime_ms

VALUE_KEYS = ("value", "val", "v", "magnitude", "value_str")
TIMESTAMP_KEYS = ("timestamp", "ts", "time")
_MISSING_TAG_DROP_AFTER = 3
_MISSING_TAG_LOCK = threading.Lock()
_MISSING_TAG_TRIES: dict[str, int] = {}


def missing_tag_drop_after() -> int:
    return _MISSING_TAG_DROP_AFTER


def set_missing_tag_drop_after(value: int) -> int:
    global _MISSING_TAG_DROP_AFTER
    _MISSING_TAG_DROP_AFTER = max(1, min(20, int(value)))
    return _MISSING_TAG_DROP_AFTER


def reset_missing_tag_tries() -> None:
    with _MISSING_TAG_LOCK:
        _MISSING_TAG_TRIES.clear()


def _nudge_local_tag_push(tag_name: str) -> None:
    """If the edge already has the tag, dirty it so the catalog worker can PUSH."""
    if not tag_name:
        return
    try:
        from ..catalog.local_provider import LocalCatalogProvider
        from ..catalog.versions import now_ms, touch_local

        row = LocalCatalogProvider().find_one("tags", field="name", value=tag_name)
        if not row:
            return
        pk = row.get("_pk") or row.get("id")
        if pk is None:
            return
        touch_local("tags", str(pk), version=now_ms(), resolved=False)
    except Exception:
        logging.getLogger("pyautomation").debug(
            "catalog nudge for missing remote tag skipped name=%s", tag_name, exc_info=True
        )


def _missing_tag_should_drop(tag_name: str) -> bool:
    """True after N consecutive SAF misses: ACK the sample so the journal drains."""
    key = str(tag_name or "")
    with _MISSING_TAG_LOCK:
        tries = _MISSING_TAG_TRIES.get(key, 0) + 1
        _MISSING_TAG_TRIES[key] = tries
    _request_catalog_full_sync("tag not in remote Tags")
    _nudge_local_tag_push(key)
    if tries >= _MISSING_TAG_DROP_AFTER:
        logging.getLogger("pyautomation").warning(
            "Dropping sample for missing tag %s after %s retries",
            key,
            tries,
        )
        return True
    return False


def _clear_missing_tag(tag_name: str) -> None:
    with _MISSING_TAG_LOCK:
        _MISSING_TAG_TRIES.pop(str(tag_name or ""), None)


def _request_catalog_full_sync(reason: str) -> None:
    """Ask the catalog worker for a full pull. Never blocks the SAF hot path."""
    try:
        from ..catalog.replicator import get_catalog_replicator

        worker = get_catalog_replicator()
        if worker is not None:
            worker.request_full_sync(reason=reason)
    except Exception:
        logging.getLogger("pyautomation").debug(
            "catalog full-sync request skipped", exc_info=True
        )


def _partition_kwargs(model, item: Mapping[str, Any]) -> dict[str, Any]:
    """Forward-compatible: emit partition fields only when the model accepts them."""
    fields = getattr(getattr(model, "_meta", None), "fields", {}) or {}
    try:
        signature = inspect.signature(model.create)
        accepts_kwargs = any(
            parameter.kind == inspect.Parameter.VAR_KEYWORD
            for parameter in signature.parameters.values()
        )
        accepted = set(signature.parameters)
    except (TypeError, ValueError):
        accepts_kwargs = False
        accepted = set()
    result = {}
    for name in ("area", "owner_node"):
        if name in fields and (accepts_kwargs or name in accepted):
            result[name] = item.get(name)
    return result


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
            raw = raw.replace(tzinfo=timezone.utc)
        else:
            raw = raw.astimezone(timezone.utc)
        return quantize_datetime_ms(raw)
    if isinstance(raw, (int, float)):
        seconds = epoch_seconds_from_db_tick(raw)
        return quantize_datetime_ms(datetime.fromtimestamp(seconds, tz=timezone.utc))
    try:
        parsed = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return quantize_datetime_ms(parsed.astimezone(timezone.utc))


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
        tag_cache: dict[Any, Any] = {}
        unit_cache: dict[Any, Any] = {}
        for item in payloads:
            row = self._map_one(item, logger, tag_cache, unit_cache)
            if row is not None:
                rows.append(row)
                _clear_missing_tag(str(item.get("tag") or item.get("tag_name") or ""))
        if rows:
            sample = {
                "tag": getattr(rows[0].get("tag"), "name", rows[0].get("tag")),
                "value": rows[0].get("value"),
                "timestamp": rows[0].get("timestamp"),
                "sample_uuid": rows[0].get("sample_uuid"),
            }
            logger.debug("SAF TagValuePayloadMapper mapped_row=%s count=%s", sample, len(rows))
        return rows

    def _map_one(self, item: Mapping[str, Any], logger, tag_cache=None, unit_cache=None) -> dict[str, Any] | None:
        tag_name = item.get("tag") or item.get("tag_name")
        tag = self._lookup_tag(tag_name, tag_cache)
        if not tag:
            logger.warning("SAF skip tag payload: tag %s not in remote Tags", tag_name)
            _request_catalog_full_sync("tag not in remote Tags")
            return None
        unit = self._lookup_unit(tag, unit_cache)
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
            **self._tag_value_partition(item),
        }

    @staticmethod
    def _tag_value_partition(item: Mapping[str, Any]) -> dict[str, Any]:
        try:
            from ..dbmodels.tags import TagValue

            fields = getattr(TagValue._meta, "fields", {}) or {}
        except Exception:
            fields = {}
        return {
            name: item.get(name)
            for name in ("area", "owner_node")
            if name in fields
        }

    def _lookup_tag(self, name, cache=None):
        if name is None:
            return None
        if cache is not None and name in cache:
            return cache[name]
        if self._resolve_tag is not None:
            tag = self._resolve_tag(name)
        else:
            from ..dbmodels.tags import Tags
            tag = Tags.read_by_name(name)
        if cache is not None:
            cache[name] = tag
        return tag

    def _lookup_unit(self, tag, cache=None):
        cache_key = getattr(tag, "id", None) or id(tag)
        if cache is not None and cache_key in cache:
            return cache[cache_key]
        if self._resolve_unit is not None:
            unit = self._resolve_unit(tag)
        else:
            from ..dbmodels.tags import Units
            unit = Units.get_or_none(id=tag.display_unit.id) if getattr(tag, "display_unit", None) else None
            if unit is None and getattr(tag, "unit", None) is not None:
                unit = tag.unit
        if cache is not None:
            cache[cache_key] = unit
        return unit


class PeeweeRemoteDB:
    """Distribution plane. Never owns durability — that is the local journal."""

    def __init__(
        self,
        tag_inserter: IIdempotentInserter | None = None,
        tag_mapper=None,
        alarm_inserter: AlarmSummaryInserter | None = None,
    ):
        self._tag_inserter = tag_inserter or IdempotentBatchInserter()
        self._tag_mapper = tag_mapper or TagValuePayloadMapper()
        self._alarm_inserter = alarm_inserter or AlarmSummaryInserter()

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

    def write_batch_outcomes(self, domain: str, payloads: Sequence[Mapping]) -> list[bool]:
        if not payloads:
            return []
        if domain == DOMAIN.TAG:
            return self._tag_value_outcomes(payloads)
        if domain == DOMAIN.EVENT:
            return self._write_event_outcomes(payloads)
        if domain == DOMAIN.ALARM_SUMMARY:
            return self._write_alarm_create_outcomes(payloads)
        if domain == DOMAIN.ALARM_SUMMARY_UPDATE:
            return self._write_alarm_update_outcomes(payloads)
        if domain == DOMAIN.LOG:
            return self._write_log_outcomes(payloads)
        raise ValueError(f"Unsupported SAF domain: {domain}")

    def _tag_value_outcomes(self, payloads: Sequence[Mapping]) -> list[bool]:
        """Per-sample ACK. Missing remote tags drop after 3 misses so the SAF ring drains."""
        logger = logging.getLogger("pyautomation")
        tag_cache: dict[Any, Any] = {}
        unit_cache: dict[Any, Any] = {}
        outcomes: list[bool] = [False] * len(payloads)
        to_insert: list[dict[str, Any]] = []
        insert_at: list[int] = []
        for index, item in enumerate(payloads):
            try:
                tag_name = item.get("tag") or item.get("tag_name")
                row = self._tag_mapper._map_one(item, logger, tag_cache, unit_cache)
                if row is None:
                    if tag_name in tag_cache and tag_cache.get(tag_name) is None:
                        outcomes[index] = _missing_tag_should_drop(str(tag_name or ""))
                    else:
                        # Unmappable payload (no timestamp / value / unit) must
                        # drain. Retrying it 5× only dead-letters the journal.
                        outcomes[index] = True
                    continue
                _clear_missing_tag(str(tag_name or ""))
                insert_at.append(index)
                to_insert.append(row)
            except Exception as exc:
                logger.warning("SAF tag sample map failed: %s", exc)
        if not to_insert:
            return outcomes
        try:
            self._tag_inserter.insert_tag_values(to_insert)
            for index in insert_at:
                outcomes[index] = True
            return outcomes
        except Exception:
            logger.debug("SAF tag batch insert failed; retrying per sample", exc_info=True)
        for index, row in zip(insert_at, to_insert):
            try:
                self._tag_inserter.insert_tag_values([row])
                outcomes[index] = True
            except Exception as exc:
                logger.warning("SAF tag sample insert failed: %s", exc)
        return outcomes

    def batch_insert_with_dedupe(self, payloads: Sequence[Mapping]) -> int:
        rows = self._tag_mapper.to_rows(payloads)
        if not rows:
            return 0
        return self._tag_inserter.insert_tag_values(rows)

    def _write_events(self, payloads: Sequence[Mapping]) -> int:
        return sum(self._write_event_outcomes(payloads))

    def _write_event_outcomes(self, payloads: Sequence[Mapping]) -> list[bool]:
        from ..dbmodels.events import Events

        outcomes: list[bool] = []
        logger = logging.getLogger("pyautomation")
        for item in payloads:
            try:
                user = _user_for_username(item.get("username") or "system")
                if user is None:
                    outcomes.append(False)
                    continue
                kwargs = dict(
                    message=item.get("message"),
                    user=user,
                    description=item.get("description"),
                    classification=item.get("classification"),
                    priority=item.get("priority"),
                    criticity=item.get("criticity"),
                    timestamp=_parse_dt(item.get("timestamp")),
                )
                kwargs.update(_partition_kwargs(Events, item))
                created, _ = Events.create(**kwargs)
                outcomes.append(created is not None)
            except Exception as exc:
                logger.warning("SAF event sample failed: %s", exc)
                outcomes.append(False)
        return outcomes

    def _write_alarm_creates(self, payloads: Sequence[Mapping]) -> int:
        outcomes = self._write_alarm_create_outcomes(payloads)
        skipped = sum(1 for ok in outcomes if not ok)
        if skipped:
            logging.getLogger("pyautomation").error(
                "SAF alarm_summary skipped %s/%s (catalog or insert failed)",
                skipped,
                len(payloads),
            )
        return sum(outcomes)

    def _alarm_summary_row(self, item: Mapping) -> dict[str, Any] | None:
        from ..dbmodels.alarms import AlarmStates, AlarmSummary, Alarms

        name = item.get("name")
        state_name = item.get("state")
        area = item.get("area")
        alarm = Alarms.read_by_name(name=name, area=area)
        state = AlarmStates.read_by_name(name=state_name) if state_name else None
        if not alarm or not state:
            return None
        timestamp = _parse_dt(item.get("timestamp"))
        if timestamp is None:
            return None
        timestamp = quantize_datetime_ms(timestamp)
        ack_timestamp = _parse_dt(item.get("ack_timestamp"))
        if ack_timestamp is not None:
            ack_timestamp = quantize_datetime_ms(ack_timestamp)
        row = dict(
            alarm=alarm.id,
            state=state.id,
            alarm_time=timestamp,
            ack_time=ack_timestamp,
            area=area or getattr(alarm, "area", None),
            sample_uuid=canonical_sample_uuid(
                item.get("sample_uuid") or item.get("idempotency_key")
            ),
        )
        row.update(_partition_kwargs(AlarmSummary, item))
        return row

    def _write_alarm_create_outcomes(self, payloads: Sequence[Mapping]) -> list[bool]:
        outcomes: list[bool] = []
        logger = logging.getLogger("pyautomation")
        for item in payloads:
            try:
                if _ensure_alarm_catalog(item) is None:
                    outcomes.append(False)
                    continue
                row = self._alarm_summary_row(item)
                if row is None:
                    outcomes.append(False)
                    continue
                outcomes.append(self._alarm_inserter.insert_one(row))
            except Exception as exc:
                logger.warning("SAF alarm_summary sample failed: %s", exc)
                outcomes.append(False)
        return outcomes

    def _write_alarm_updates(self, payloads: Sequence[Mapping]) -> int:
        return sum(self._write_alarm_update_outcomes(payloads))

    def _write_alarm_update_outcomes(self, payloads: Sequence[Mapping]) -> list[bool]:
        from ..dbmodels.alarms import AlarmStates, AlarmSummary

        outcomes: list[bool] = []
        skipped = []
        logger = logging.getLogger("pyautomation")
        for item in payloads:
            try:
                _ensure_alarm_catalog(item)
                alarm = AlarmSummary.read_by_name(
                    name=item.get("name"),
                    area=item.get("area"),
                )
                if not alarm:
                    skipped.append(item.get("name"))
                    outcomes.append(False)
                    continue
                fields = {}
                if item.get("ack_timestamp"):
                    ack_stamp = _parse_dt(item.get("ack_timestamp"))
                    if ack_stamp is not None:
                        fields["ack_time"] = quantize_datetime_ms(ack_stamp)
                if item.get("state"):
                    alarm_state = AlarmStates.get_or_none(name=item["state"])
                    if alarm_state:
                        fields["state"] = alarm_state
                if fields:
                    AlarmSummary.put(id=alarm.id, **fields)
                    outcomes.append(True)
                else:
                    skipped.append(item.get("name"))
                    outcomes.append(False)
            except Exception as exc:
                logger.warning("SAF alarm_summary_update sample failed: %s", exc)
                skipped.append(item.get("name"))
                outcomes.append(False)
        if skipped:
            logging.getLogger("pyautomation").error(
                "SAF alarm_summary_update skipped %s/%s (summary missing): %s",
                len(skipped),
                len(payloads),
                skipped[:20],
            )
        return outcomes

    def _write_logs(self, payloads: Sequence[Mapping]) -> int:
        return sum(self._write_log_outcomes(payloads))

    def _write_log_outcomes(self, payloads: Sequence[Mapping]) -> list[bool]:
        from ..dbmodels.logs import Logs

        outcomes: list[bool] = []
        logger = logging.getLogger("pyautomation")
        for item in payloads:
            try:
                username = item.get("username") or item.get("user_name") or "system"
                user = _user_for_username(username)
                kwargs = dict(
                    message=item.get("message"),
                    user=user,
                    user_name=item.get("user_name") or username,
                    description=item.get("description"),
                    classification=item.get("classification"),
                    alarm_summary_id=item.get("alarm_summary_id"),
                    event_id=item.get("event_id"),
                    timestamp=_parse_dt(item.get("timestamp")),
                    shift=item.get("shift"),
                    area=item.get("area"),
                    handover=bool(item.get("handover")),
                )
                kwargs.update(_partition_kwargs(Logs, item))
                created, _ = Logs.create(**kwargs)
                outcomes.append(created is not None)
            except Exception as exc:
                logger.warning("SAF log sample failed: %s", exc)
                outcomes.append(False)
        return outcomes


def _runtime_alarm(name: str):
    if not name:
        return None
    try:
        from .. import PyAutomation

        return PyAutomation().alarm_manager.get_alarm_by_name(name)
    except Exception:
        return None


def _tag_name(tag) -> str | None:
    if tag is None:
        return None
    if isinstance(tag, str):
        return tag
    name = getattr(tag, "name", None)
    if name:
        return name
    getter = getattr(tag, "get_name", None)
    if callable(getter):
        return getter() or None
    return None


def _alarm_catalog_fields(item: Mapping[str, Any]) -> dict[str, Any] | None:
    name = item.get("name")
    tag = item.get("tag") or item.get("tag_name")
    identifier = item.get("id") or item.get("identifier")
    trigger_type = item.get("trigger_type") or item.get("alarm_type")
    trigger_value = item.get("trigger_value")
    description = item.get("description")
    area = item.get("area")
    state = item.get("state")
    runtime = _runtime_alarm(name)
    if runtime is not None:
        tag = tag or _tag_name(getattr(runtime, "tag", None))
        identifier = identifier or getattr(runtime, "identifier", None)
        description = description or getattr(runtime, "description", None)
        payload = getattr(runtime, "catalog_payload", None)
        extra = payload() if callable(payload) else {}
        tag = tag or extra.get("tag")
        identifier = identifier or extra.get("identifier")
        trigger_type = trigger_type or extra.get("trigger_type")
        if trigger_value is None:
            trigger_value = extra.get("trigger_value")
        description = description or extra.get("description")
        area = area or extra.get("area")
        state = state or extra.get("state")
    if not name or not tag:
        return None
    payload = {
        "identifier": identifier,
        "name": name,
        "tag": tag,
        "trigger_type": trigger_type or "BOOL",
        "trigger_value": 0.0 if trigger_value is None else trigger_value,
        "description": description or "",
        "area": area,
    }
    if state:
        payload["state"] = state
    return payload


def _ensure_alarm_catalog(item: Mapping[str, Any]):
    from ..dbmodels.alarms import Alarms

    name = item.get("name")
    area = item.get("area")
    existing = Alarms.read_by_name(name=name, area=area)
    if existing is not None:
        return existing
    fields = _alarm_catalog_fields(item)
    if not fields:
        logging.getLogger("pyautomation").error(
            "SAF cannot materialize alarm catalog name=%s area=%s (missing tag/runtime)",
            name,
            area,
        )
        return None
    if not fields.get("identifier"):
        import secrets

        fields["identifier"] = secrets.token_hex(4)
    created = Alarms.create(**fields)
    if created is not None:
        return created
    return Alarms.read_by_name(name=name, area=area)


def _user_for_username(username: str):
    from ..dbmodels.users import Users
    from ..modules.users.roles import Role
    from ..modules.users.users import User, Users as UsersService

    memory_user = UsersService().get_by_username(username=username)
    if memory_user is not None:
        try:
            from ..catalog.ensure_historian import ensure_historian_user

            ensure_historian_user(memory_user)
        except Exception:
            logging.getLogger("pyautomation").debug(
                "SAF ensure historian user skipped username=%s",
                username,
                exc_info=True,
            )
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
