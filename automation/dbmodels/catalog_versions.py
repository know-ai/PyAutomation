# -*- coding: utf-8 -*-
"""Historian-side catalog_versions sidecar (Peewee proxy, never rebound)."""
from peewee import BigIntegerField, BooleanField, CharField, CompositeKey

from .core import BaseModel


class CatalogVersions(BaseModel):
    table_name = CharField(max_length=64)
    row_id = CharField(max_length=64)
    version = BigIntegerField()
    node_id = CharField(max_length=64, null=True)
    conflict_resolved = BooleanField(default=False)

    class Meta:
        table_name = "catalog_versions"
        primary_key = CompositeKey("table_name", "row_id")
        indexes = ((("table_name", "version"), False),)
