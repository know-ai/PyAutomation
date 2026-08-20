# -*- coding: utf-8 -*-
from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Mapping

from ..timebase import iso_millis, quantize_datetime_ms

SAMPLE_UUID_MAX_LEN = 64


def canonical_sample_uuid(value: str | None) -> str | None:
    """Fit TagValue.sample_uuid (VARCHAR(64)). SHA-256 hex is exactly 64 chars."""
    if not value:
        return value
    if len(value) <= SAMPLE_UUID_MAX_LEN:
        return value
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


class DOMAIN:
    TAG = "tag"
    ALARM_SUMMARY = "alarm_summary"
    ALARM_SUMMARY_UPDATE = "alarm_summary_update"
    EVENT = "event"
    LOG = "log"


_CRITICAL = {
    DOMAIN.ALARM_SUMMARY,
    DOMAIN.ALARM_SUMMARY_UPDATE,
    DOMAIN.EVENT,
    DOMAIN.LOG,
}


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def iso(value: datetime | str | None) -> str | None:
    """Full-precision ISO for alarms/events/logs (and generic payloads)."""
    if value is None:
        return None
    if isinstance(value, str):
        return value
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat()


def iso_tag(value: datetime | str | None) -> str | None:
    """Tag historian ISO — millisecond resolution (Operación Milisegundo Exacto)."""
    return iso_millis(value)


def _scope_metadata(
    area=None,
    owner_node=None,
    *,
    plant_wide: bool = False,
) -> tuple[str | None, str | None]:
    try:
        from ..node_scope import get_node_scope

        scope = get_node_scope()
    except (ImportError, AttributeError):
        return (None if plant_wide else area), owner_node
    if getattr(scope, "enabled", False) and getattr(scope, "is_valid", False):
        if area is None and not plant_wide:
            area = getattr(scope, "area", None)
        if owner_node is None:
            owner_node = getattr(scope, "node_id", None)
    if plant_wide:
        area = None
    return area, owner_node


@dataclass(frozen=True)
class PersistableRecord:
    """Canonical IPersistable implemented by all history producers."""

    domain_name: str
    entity: str
    body: Mapping[str, Any]
    key: str = ""
    critical: bool | None = None
    created_at: datetime = field(default_factory=utc_now)

    def __post_init__(self):
        if not self.key:
            object.__setattr__(self, "key", str(uuid.uuid4()))
        if self.critical is None:
            object.__setattr__(self, "critical", self.domain_name in _CRITICAL)

    def domain(self) -> str:
        return self.domain_name

    def entity_id(self) -> str:
        return self.entity

    def idempotency_key(self) -> str:
        return self.key

    def payload(self) -> Mapping[str, Any]:
        return self.body

    def is_critical(self) -> bool:
        return bool(self.critical)

    @classmethod
    def tag_sample(
        cls,
        tag: str,
        value: Any,
        timestamp: datetime,
        *,
        area: str | None = None,
        owner_node: str | None = None,
        quality: float | None = None,
    ) -> "PersistableRecord":
        if isinstance(timestamp, datetime):
            timestamp = quantize_datetime_ms(timestamp)
        ts = iso_tag(timestamp)
        key = f"tag:{tag}:{ts}"
        area, owner_node = _scope_metadata(area, owner_node)
        body = {
            "tag": tag,
            "value": _json_safe(value),
            "timestamp": ts,
            "sample_uuid": canonical_sample_uuid(key),
            "area": area,
            "owner_node": owner_node,
        }
        if quality is not None:
            body["quality"] = quality
        return cls(
            domain_name=DOMAIN.TAG,
            entity=str(tag),
            body=body,
            key=key,
            critical=False,
        )

    @classmethod
    def event(
        cls,
        *,
        message: str,
        username: str,
        description: str | None = None,
        classification: str | None = None,
        priority: int | None = None,
        criticity: int | None = None,
        timestamp: datetime | None = None,
        area: str | None = None,
        owner_node: str | None = None,
        plant_wide: bool = False,
    ) -> "PersistableRecord":
        ts = iso(timestamp or utc_now())
        area, owner_node = _scope_metadata(area, owner_node, plant_wide=plant_wide)
        return cls(
            domain_name=DOMAIN.EVENT,
            entity=username or "system",
            body={
                "message": message,
                "username": username,
                "description": description,
                "classification": classification,
                "priority": priority,
                "criticity": criticity,
                "timestamp": ts,
                "area": area,
                "owner_node": owner_node,
            },
            key=f"event:{username}:{ts}:{message}",
            critical=True,
        )

    @classmethod
    def alarm_create(
        cls,
        *,
        name: str,
        state: str,
        timestamp: datetime,
        ack_timestamp: datetime | None = None,
        area: str | None = None,
        owner_node: str | None = None,
        identifier: str | None = None,
        tag: str | None = None,
        trigger_type: str | None = None,
        trigger_value: Any = None,
        description: str | None = None,
    ) -> "PersistableRecord":
        ts = iso(timestamp)
        key = f"alarm:{name}:{ts}:{state}"
        area, owner_node = _scope_metadata(area, owner_node)
        return cls(
            domain_name=DOMAIN.ALARM_SUMMARY,
            entity=name,
            body={
                "name": name,
                "state": state,
                "timestamp": ts,
                "ack_timestamp": iso(ack_timestamp),
                "area": area,
                "owner_node": owner_node,
                "identifier": identifier,
                "tag": tag,
                "trigger_type": trigger_type,
                "trigger_value": trigger_value,
                "description": description,
                "sample_uuid": canonical_sample_uuid(key),
            },
            key=key,
            critical=True,
        )

    @classmethod
    def alarm_update(
        cls,
        *,
        name: str,
        state: str | None = None,
        ack_timestamp: datetime | None = None,
        area: str | None = None,
        owner_node: str | None = None,
        identifier: str | None = None,
        tag: str | None = None,
    ) -> "PersistableRecord":
        ts = iso(utc_now())
        area, owner_node = _scope_metadata(area, owner_node)
        return cls(
            domain_name=DOMAIN.ALARM_SUMMARY_UPDATE,
            entity=name,
            body={
                "name": name,
                "state": state,
                "ack_timestamp": iso(ack_timestamp),
                "area": area,
                "owner_node": owner_node,
                "identifier": identifier,
                "tag": tag,
            },
            key=f"alarm-update:{name}:{ts}:{state}:{iso(ack_timestamp)}",
            critical=True,
        )

    @classmethod
    def log(
        cls,
        *,
        message: str,
        username: str,
        description: str | None = None,
        classification: str | None = None,
        alarm_summary_id: int | None = None,
        event_id: int | None = None,
        timestamp: datetime | None = None,
        shift: str | None = None,
        area: str | None = None,
        owner_node: str | None = None,
        handover: bool = False,
        user_name: str | None = None,
    ) -> "PersistableRecord":
        ts = iso(timestamp or utc_now())
        author = user_name or username or "system"
        area, owner_node = _scope_metadata(area, owner_node)
        return cls(
            domain_name=DOMAIN.LOG,
            entity=author,
            body={
                "message": message,
                "username": username,
                "user_name": author,
                "description": description,
                "classification": classification,
                "alarm_summary_id": alarm_summary_id,
                "event_id": event_id,
                "timestamp": ts,
                "shift": shift,
                "area": area,
                "owner_node": owner_node,
                "handover": bool(handover),
            },
            key=f"log:{author}:{ts}:{message}",
            critical=True,
        )


class JournaledEnvelope:
    """In-memory stand-in so Socket.IO can emit before remote ACK."""

    def __init__(self, payload: Mapping[str, Any]):
        self.id = None
        self.payload = dict(payload)

    def serialize(self, timezone=None) -> dict:
        username = self.payload.get("user_name") or self.payload.get("username")
        return {
            "id": None,
            "timestamp": self.payload.get("timestamp"),
            "user": {"username": username},
            "user_name": username,
            "message": self.payload.get("message"),
            "description": self.payload.get("description"),
            "classification": self.payload.get("classification"),
            "shift": self.payload.get("shift"),
            "area": self.payload.get("area"),
            "segment": self.payload.get("area"),
            "handover": bool(self.payload.get("handover")),
            "priority": self.payload.get("priority"),
            "criticity": self.payload.get("criticity"),
            "journaled": True,
        }


def _json_safe(value: Any) -> Any:
    if hasattr(value, "value"):
        try:
            return float(value.value)
        except (TypeError, ValueError):
            return str(value.value)
    if isinstance(value, datetime):
        return iso(value)
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    try:
        return float(value)
    except (TypeError, ValueError):
        return str(value)
