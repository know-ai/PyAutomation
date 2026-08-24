# -*- coding: utf-8 -*-
"""Business-content fingerprints for catalog sync (ignore audit timestamps / PKs).

Industrial rule: two rows with the same configuration are the same row even when
``updated_at`` or autoincrement ``id`` differ across local SQLite and remote PG.
"""
from __future__ import annotations

import hashlib
import json
import math
from datetime import date, datetime
from typing import Any

from .identity import FK_SPECS, _fk_value, _parent_identity_from_source, identity_key

# Audit / wire-only keys never participate in divergence detection.
_AUDIT_KEYS = frozenset(
    {
        "id",
        "_pk",
        "sid",
        "updated_at",
        "created_at",
        "last_updated",
        "last_seen",
        "modified_at",
        "synced_at",
        "timestamp",
        "version",
        "node_id",
        "conflict_resolved",
    }
)


def _is_audit_key(name: str) -> bool:
    key = str(name or "")
    if not key or key.startswith("_"):
        return True
    lower = key.lower()
    if lower in _AUDIT_KEYS:
        return True
    # Generic audit suffixes (not business KP / setpoint fields).
    if lower.endswith("_at") and lower in {
        "updated_at",
        "created_at",
        "modified_at",
        "synced_at",
        "last_updated_at",
    }:
        return True
    return False


def _json_safe(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    if isinstance(value, float):
        if math.isnan(value) or math.isinf(value):
            return None
        # Stabilize 1.0 vs 1 for JSON equality across drivers.
        if value.is_integer():
            return int(value)
        return round(value, 12)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, bytes):
        return value.hex()
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in sorted(value.items(), key=lambda item: str(item[0]))}
    if isinstance(value, (list, tuple)):
        return [_json_safe(v) for v in value]
    text = str(value).strip()
    if text.lower() in {"true", "false"} and not isinstance(value, str):
        return text.lower() == "true"
    return text


def canonicalize_business_row(
    table: str,
    row: dict | None,
    *,
    table_index: dict[str, dict] | None = None,
) -> dict[str, Any]:
    """Return a stable business payload: FKs → parent natural keys, no audit fields."""
    if not row:
        return {}
    index = table_index or {}
    payload: dict[str, Any] = {}
    specs = FK_SPECS.get(table) or ()
    fk_fields = {field for field, _, _ in specs}
    fk_columns = {f"{field}_id" for field, _, _ in specs}

    for field, parent_table, lookup_fields in specs:
        fk_value = _fk_value(row, field)
        if fk_value is None or fk_value == "":
            payload[field] = None
            continue
        parents = index.get(parent_table) or {}
        parent_key = _parent_identity_from_source(parent_table, fk_value, parents, lookup_fields)
        if parent_key is None:
            # Already a natural token or unresolved — keep normalized text.
            parent_key = identity_key(parent_table, {lookup_fields[0]: fk_value}) if lookup_fields else _norm_token(fk_value)
        payload[field] = parent_key

    for key, value in row.items():
        if _is_audit_key(key):
            continue
        if key in fk_fields or key in fk_columns:
            continue
        payload[key] = _json_safe(value)

    return {k: payload[k] for k in sorted(payload.keys())}


def _norm_token(value: Any) -> str:
    return str(value).strip()


def content_hash(
    table: str,
    row: dict | None,
    *,
    table_index: dict[str, dict] | None = None,
) -> str:
    """SHA-256 hex digest of canonical business fields."""
    canonical = canonicalize_business_row(table, row, table_index=table_index)
    blob = json.dumps(canonical, separators=(",", ":"), ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def contents_equal(
    table: str,
    left: dict | None,
    right: dict | None,
    *,
    left_index: dict[str, dict] | None = None,
    right_index: dict[str, dict] | None = None,
) -> bool:
    """True when business configuration matches (audit timestamps ignored)."""
    return content_hash(table, left, table_index=left_index) == content_hash(
        table, right, table_index=right_index
    )
