"""Registro de identidad de nodos edge."""
from __future__ import annotations

import socket
from datetime import datetime, timezone

from peewee import CharField, TimestampField

from .core import BaseModel


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Nodes(BaseModel):
    id = CharField(primary_key=True, max_length=64)
    area = CharField(max_length=64)
    site = CharField(max_length=64, null=True)
    hostname = CharField(max_length=255, null=True)
    version = CharField(max_length=32, null=True)
    last_seen = TimestampField(utc=True, default=utc_now)
    created_at = TimestampField(utc=True, default=utc_now)
    updated_at = TimestampField(utc=True, default=utc_now)

    @classmethod
    def register(
        cls,
        node_id: str,
        area: str,
        *,
        site: str | None = None,
        hostname: str | None = None,
        version: str | None = None,
        now: datetime | None = None,
    ) -> "Nodes":
        """UPSERT idempotente sin asignar propietarios a otras tablas."""
        if not node_id or not area:
            raise ValueError("node_id and area are required")
        if len(node_id) > 64 or len(area) > 64:
            raise ValueError("node_id and area must not exceed 64 characters")
        existing = cls.get_or_none(cls.id == node_id)
        if existing is not None and existing.area != area:
            raise ValueError(
                f"node_id '{node_id}' is already registered for area '{existing.area}'"
            )
        timestamp = now or utc_now()
        values = {
            "area": area,
            "site": site,
            "hostname": hostname or socket.gethostname(),
            "version": version,
            "last_seen": timestamp,
            "updated_at": timestamp,
        }
        update_values = {
            cls.area: area,
            cls.site: site,
            cls.hostname: values["hostname"],
            cls.version: version,
            cls.last_seen: timestamp,
            cls.updated_at: timestamp,
        }
        cls.insert(
            id=node_id,
            created_at=timestamp,
            **values,
        ).on_conflict(
            conflict_target=[cls.id],
            update=update_values,
        ).execute()
        return cls.get_by_id(node_id)

    def serialize(self) -> dict:
        return {
            "id": self.id,
            "area": self.area,
            "site": self.site,
            "hostname": self.hostname,
            "version": self.version,
            "last_seen": self.last_seen,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }
