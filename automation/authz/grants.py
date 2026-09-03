# -*- coding: utf-8 -*-
"""Read/write AuthzGrant rows (historian + local catalog + memory cache)."""
from __future__ import annotations

import logging

from . import store

_LOGGER = logging.getLogger("pyautomation")


def _persist_local(row: dict) -> None:
    try:
        from ..catalog.local_provider import LocalCatalogProvider
        from ..catalog.versions import edge_node_id, now_ms

        LocalCatalogProvider().upsert(
            "authz_grants",
            row,
            node_id=edge_node_id(),
            version=now_ms(),
        )
    except Exception:
        _LOGGER.debug("authz grant local upsert skipped", exc_info=True)


def _delete_local(row: dict) -> None:
    try:
        from ..catalog.local_provider import LocalCatalogProvider, local_model
        from ..catalog.local_db import get_catalog_database

        model = local_model("authz_grants")
        if model is None or get_catalog_database() is None:
            return
        q = model.delete().where(
            (model.subject_type == row["subject_type"])
            & (model.subject_id == row["subject_id"])
            & (model.resource_key == row["resource_key"])
            & (model.action == row["action"])
        )
        q.execute()
    except Exception:
        _LOGGER.debug("authz grant local delete skipped", exc_info=True)


def list_grants(subject_type: str | None = None, subject_id: str | None = None) -> list[dict]:
    rows: list[dict] = []
    try:
        from automation import PyAutomation
        from ..dbmodels.authz import AuthzGrant

        if bool(PyAutomation().is_db_connected()):
            query = AuthzGrant.select()
            if subject_type:
                query = query.where(AuthzGrant.subject_type == subject_type)
            if subject_id:
                query = query.where(AuthzGrant.subject_id == subject_id)
            return [row.serialize() for row in query.iterator()]
    except Exception:
        _LOGGER.debug("authz grants historian list skipped", exc_info=True)
    try:
        from ..catalog.local_provider import LocalCatalogProvider

        for row in LocalCatalogProvider().read_all("authz_grants"):
            if subject_type and str(row.get("subject_type")) != subject_type:
                continue
            if subject_id and str(row.get("subject_id")) != subject_id:
                continue
            rows.append(row)
    except Exception:
        _LOGGER.debug("authz grants local list skipped", exc_info=True)
    if rows:
        return rows
    snap = store.snapshot()
    for (stype, sid, key, action), effect in snap.items():
        if subject_type and stype != str(subject_type).lower():
            continue
        if subject_id and sid != str(subject_id).lower():
            continue
        rows.append(
            {
                "subject_type": stype,
                "subject_id": sid,
                "resource_key": key,
                "action": action,
                "effect": effect,
            }
        )
    return rows


def upsert_grant(subject_type: str, subject_id: str, resource_key: str, action: str, effect: str) -> dict:
    effect_norm = str(effect or "").strip().lower()
    if effect_norm not in {"allow", "deny"}:
        delete_grant(subject_type, subject_id, resource_key, action)
        return {
            "subject_type": subject_type,
            "subject_id": subject_id,
            "resource_key": resource_key,
            "action": action,
            "effect": "default",
        }
    row = {
        "subject_type": str(subject_type).strip().lower(),
        "subject_id": str(subject_id).strip(),
        "resource_key": str(resource_key).strip(),
        "action": str(action).strip().lower(),
        "effect": effect_norm,
    }
    try:
        from ..dbmodels.authz import AuthzGrant

        existing = AuthzGrant.get_or_none(
            (AuthzGrant.subject_type == row["subject_type"])
            & (AuthzGrant.subject_id == row["subject_id"])
            & (AuthzGrant.resource_key == row["resource_key"])
            & (AuthzGrant.action == row["action"])
        )
        if existing is None:
            AuthzGrant.create(**row)
        else:
            existing.effect = effect_norm
            existing.save()
    except Exception:
        _LOGGER.debug("authz grant historian upsert skipped", exc_info=True)
    _persist_local(row)
    store.put_grant(row["subject_type"], row["subject_id"], row["resource_key"], row["action"], effect_norm)
    return row


def delete_grant(subject_type: str, subject_id: str, resource_key: str, action: str) -> None:
    row = {
        "subject_type": str(subject_type).strip().lower(),
        "subject_id": str(subject_id).strip(),
        "resource_key": str(resource_key).strip(),
        "action": str(action).strip().lower(),
    }
    try:
        from ..dbmodels.authz import AuthzGrant

        AuthzGrant.delete().where(
            (AuthzGrant.subject_type == row["subject_type"])
            & (AuthzGrant.subject_id == row["subject_id"])
            & (AuthzGrant.resource_key == row["resource_key"])
            & (AuthzGrant.action == row["action"])
        ).execute()
    except Exception:
        _LOGGER.debug("authz grant historian delete skipped", exc_info=True)
    _delete_local(row)
    store.delete_grant(row["subject_type"], row["subject_id"], row["resource_key"], row["action"])
