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
