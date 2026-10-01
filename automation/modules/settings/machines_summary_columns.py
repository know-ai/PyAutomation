# -*- coding: utf-8 -*-
"""Station-scoped columns for /hmi/machines/summary. Survives a process restart."""
from __future__ import annotations

import json
import logging
import os
import re
from datetime import datetime, timezone
from typing import Any

KIND = "machines-summary"
SCHEMA_VERSION = 1
SCOPE = "station"
PATH = os.path.join(".", "db", "hmi_workspace_machines_summary.json")

LOCKED_COLUMNS = ("name", "state")
DEFAULT_COLUMNS = ("name", "state", "criticity", "description", "classification")
MAX_COLUMNS = 80
_KEY = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _clean_key(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    key = value.strip()
    if not key or not _KEY.match(key):
        return None
    return key


def sanitize_columns(raw: Any) -> list[str]:
    incoming: list[Any] = []
    if isinstance(raw, dict):
        maybe = raw.get("columns")
        if isinstance(maybe, list):
            incoming = maybe
    elif isinstance(raw, list):
        incoming = raw

    columns: list[str] = list(LOCKED_COLUMNS)
    seen = set(columns)
    for item in incoming:
        key = _clean_key(item)
        if key is None or key in seen:
            continue
        seen.add(key)
        columns.append(key)
        if len(columns) >= MAX_COLUMNS:
            break
    return columns


def empty_document() -> dict[str, Any]:
    return {
        "schemaVersion": SCHEMA_VERSION,
        "kind": KIND,
        "scope": SCOPE,
        "updatedAt": datetime.now(timezone.utc).isoformat(),
        "columns": list(DEFAULT_COLUMNS),
    }


def load_machines_summary_columns() -> dict[str, Any]:
    if not os.path.isfile(PATH):
        return empty_document()
    try:
        with open(PATH, "r", encoding="utf-8") as handle:
            raw = json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        logging.warning("Cannot read machines-summary columns: %s", exc)
        return empty_document()
    document = empty_document()
    document["columns"] = sanitize_columns(raw)
    if isinstance(raw, dict) and isinstance(raw.get("updatedAt"), str) and raw["updatedAt"].strip():
        document["updatedAt"] = raw["updatedAt"].strip()
    return document


def save_machines_summary_columns(raw: Any) -> dict[str, Any]:
    document = empty_document()
    document["columns"] = sanitize_columns(raw)
    document["updatedAt"] = datetime.now(timezone.utc).isoformat()
    directory = os.path.dirname(PATH) or "."
    os.makedirs(directory, exist_ok=True)
    tmp_path = f"{PATH}.tmp"
    with open(tmp_path, "w", encoding="utf-8") as handle:
        json.dump(document, handle, indent=2)
    os.replace(tmp_path, PATH)
    return document
