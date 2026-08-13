# -*- coding: utf-8 -*-
from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Mapping

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
    if value is None:
        return None
    if isinstance(value, str):
        return value
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat()


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
    def tag_sample(cls, tag: str, value: Any, timestamp: datetime) -> "PersistableRecord":
        ts = iso(timestamp)
        key = f"tag:{tag}:{ts}"
        return cls(
            domain_name=DOMAIN.TAG,
            entity=str(tag),
            body={
                "tag": tag,
                "value": _json_safe(value),
                "timestamp": ts,
                "sample_uuid": canonical_sample_uuid(key),
            },
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
    ) -> "PersistableRecord":
        ts = iso(timestamp or utc_now())
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
    ) -> "PersistableRecord":
        ts = iso(timestamp)
        return cls(
            domain_name=DOMAIN.ALARM_SUMMARY,
            entity=name,
            body={
                "name": name,
                "state": state,
                "timestamp": ts,
                "ack_timestamp": iso(ack_timestamp),
            },
            key=f"alarm:{name}:{ts}:{state}",
            critical=True,
        )

    @classmethod
    def alarm_update(
        cls,
        *,
        name: str,
        state: str | None = None,
        ack_timestamp: datetime | None = None,
    ) -> "PersistableRecord":
        ts = iso(utc_now())
        return cls(
            domain_name=DOMAIN.ALARM_SUMMARY_UPDATE,
            entity=name,
            body={
                "name": name,
                "state": state,
                "ack_timestamp": iso(ack_timestamp),
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
    ) -> "PersistableRecord":
        ts = iso(timestamp or utc_now())
        return cls(
            domain_name=DOMAIN.LOG,
            entity=username or "system",
            body={
                "message": message,
                "username": username,
                "description": description,
                "classification": classification,
                "alarm_summary_id": alarm_summary_id,
                "event_id": event_id,
                "timestamp": ts,
            },
            key=f"log:{username}:{ts}:{message}",
            critical=True,
        )


class JournaledEnvelope:
    """In-memory stand-in so Socket.IO can emit before remote ACK."""

    def __init__(self, payload: Mapping[str, Any]):
        self.id = None
        self.payload = dict(payload)

    def serialize(self, timezone=None) -> dict:
        return {
            "id": None,
            "timestamp": self.payload.get("timestamp"),
            "user": {"username": self.payload.get("username")},
            "message": self.payload.get("message"),
            "description": self.payload.get("description"),
            "classification": self.payload.get("classification"),
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
