# -*- coding: utf-8 -*-
"""Active HMI Socket.IO sessions (global state across Gunicorn workers)."""
from __future__ import annotations

from datetime import datetime, timezone

from peewee import CharField, TimestampField

from .core import BaseModel


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class HMISession(BaseModel):
    sid = CharField(primary_key=True, max_length=64)
    node_id = CharField(max_length=64)
    username = CharField(max_length=64)
    origin = CharField(max_length=45)
    area = CharField(max_length=64)
    connected_at = TimestampField(utc=True, default=utc_now)
    last_heartbeat = TimestampField(utc=True, default=utc_now)

    class Meta:
        table_name = "hmi_sessions"
        indexes = ((("node_id", "last_heartbeat"), False),)

    @classmethod
    def upsert_batch(cls, *, node_id: str, sessions: list[dict]) -> int:
        """Replace this edge's snapshot rows. Never called from Socket.IO handlers."""
        node_id = str(node_id or "local")[:64]
        now = utc_now()
        active: set[str] = set()
        written = 0
        for record in sessions or []:
            sid = str(record.get("sid") or "")[:64]
            if not sid:
                continue
            active.add(sid)
            cls.insert(
                sid=sid,
                node_id=node_id,
                username=str(record.get("username") or "unknown")[:64],
                origin=str(record.get("origin") or "")[:45],
                area=str(record.get("area") or "local")[:64],
                connected_at=now,
                last_heartbeat=now,
            ).on_conflict(
                conflict_target=[cls.sid],
                update={
                    cls.node_id: node_id,
                    cls.username: str(record.get("username") or "unknown")[:64],
                    cls.origin: str(record.get("origin") or "")[:45],
                    cls.area: str(record.get("area") or "local")[:64],
                    cls.last_heartbeat: now,
                },
            ).execute()
            written += 1
        stale_ids = [row.sid for row in cls.select().where(cls.node_id == node_id)]
        for sid in stale_ids:
            if sid not in active:
                cls.delete().where(cls.sid == sid).execute()
        return written
