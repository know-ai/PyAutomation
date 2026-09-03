# -*- coding: utf-8 -*-
"""Persisted ACL grants: subject × resource × action → allow|deny."""
from peewee import CharField

from .core import BaseModel


class AuthzGrant(BaseModel):
    """One grant row. Unique on (subject_type, subject_id, resource_key, action)."""

    subject_type = CharField(max_length=8)
    subject_id = CharField(max_length=32)
    resource_key = CharField(max_length=512)
    effect = CharField(max_length=8)
    action = CharField(max_length=8)

    class Meta:
        table_name = "authz_grants"
        indexes = (
            (("subject_type", "subject_id", "resource_key", "action"), True),
        )

    def serialize(self) -> dict:
        return {
            "id": getattr(self, "id", None),
            "subject_type": self.subject_type,
            "subject_id": self.subject_id,
            "resource_key": self.resource_key,
            "effect": self.effect,
            "action": self.action,
        }
