# -*- coding: utf-8 -*-
"""Peewee clones bound to catalog_proxy. Foreign keys become integer/char columns."""
from __future__ import annotations

from peewee import (
    BigIntegerField,
    BooleanField,
    CharField,
    CompositeKey,
    DateTimeField,
    Field,
    ForeignKeyField,
    IntegerField,
    Model,
    TextField,
)

from .local_db import catalog_proxy

LOCAL_MODELS: dict[str, type[Model]] = {}


class CatalogBase(Model):
    class Meta:
        database = catalog_proxy


class CatalogVersionsLocal(CatalogBase):
    table_name = CharField(max_length=64)
    row_id = CharField(max_length=64)
    version = BigIntegerField()
    node_id = CharField(max_length=64, null=True)
    conflict_resolved = BooleanField(default=False)

    class Meta:
        database = catalog_proxy
        table_name = "catalog_versions"
        primary_key = CompositeKey("table_name", "row_id")
        indexes = ((("table_name", "version"), False),)


class CatalogPendingRows(CatalogBase):
    """Child catalog rows waiting for a parent FK. Survives edge restarts."""

    table_name = CharField(max_length=64)
    row_id = CharField(max_length=64)
    row_data = TextField()
    retries = IntegerField(default=0)
    first_seen = DateTimeField(null=True)

    class Meta:
        database = catalog_proxy
        table_name = "pending_rows"
        primary_key = CompositeKey("table_name", "row_id")


def _clone_field(field: Field) -> Field:
    if isinstance(field, ForeignKeyField):
        rel_pk = field.rel_model._meta.primary_key
        null = bool(field.null)
        column = field.column_name
        if isinstance(rel_pk, (CharField,)):
            return CharField(max_length=getattr(rel_pk, "max_length", 64) or 64, null=null, column_name=column)
        return IntegerField(null=null, column_name=column)
    cloned = field.clone()
    return cloned


def clone_historian_model(source_cls) -> type[Model]:
    attrs: dict = {}
    for name, field in source_cls._meta.fields.items():
        attrs[name] = _clone_field(field)
    meta_dict = {
        "database": catalog_proxy,
        "table_name": source_cls._meta.table_name,
    }
    if getattr(source_cls._meta, "indexes", None):
        meta_dict["indexes"] = source_cls._meta.indexes
    attrs["Meta"] = type("Meta", (), meta_dict)
    return type(f"Local{source_cls.__name__}", (CatalogBase,), attrs)


def build_local_models() -> dict[str, type[Model]]:
    if LOCAL_MODELS:
        return LOCAL_MODELS
    from .schema import historian_models

    for table, cls in historian_models().items():
        LOCAL_MODELS[table] = clone_historian_model(cls)
    return LOCAL_MODELS


def local_model(table: str) -> type[Model] | None:
    return build_local_models().get(table)


def all_local_tables() -> list[type[Model]]:
    models = list(build_local_models().values())
    models.append(CatalogVersionsLocal)
    models.append(CatalogPendingRows)
    return models
