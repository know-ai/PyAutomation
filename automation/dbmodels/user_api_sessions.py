# -*- coding: utf-8 -*-
"""API tokens activos por edge (multi-edge con historiador compartido)."""
from __future__ import annotations

from datetime import datetime, timezone

from peewee import CharField, TextField, TimestampField

from .core import BaseModel


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class UserApiSession(BaseModel):
    """Un token de sesión HMI/API emitido por un edge concreto."""

    token = TextField(primary_key=True)
    username = CharField(max_length=64, index=True)
    node_id = CharField(max_length=64, index=True)
    area = CharField(max_length=64)
    created_at = TimestampField(utc=True, default=utc_now)

    class Meta:
        table_name = "user_api_sessions"
        indexes = ((("username", "node_id"), False),)
