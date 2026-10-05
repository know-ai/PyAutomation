# -*- coding: utf-8 -*-
"""Station policy: ask for operator credentials before selected HMI actions."""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from typing import Any

PATH = os.path.join(".", "db", "hmi_operator_confirmation.json")


def load_operator_confirmation(path: str | None = None) -> dict[str, Any]:
    """Missing file means the policy is off. Never raises."""
    target = path or PATH
    document = {
        "enabled": False,
        "updatedAt": None,
    }
    if not os.path.isfile(target):
        return document
    try:
        with open(target, "r", encoding="utf-8") as handle:
            raw = json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        logging.getLogger("pyautomation").warning(
            "Cannot read operator confirmation policy: %s", exc
        )
        return document
    if isinstance(raw, dict):
        document["enabled"] = bool(raw.get("enabled"))
        updated = raw.get("updatedAt")
        if isinstance(updated, str) and updated.strip():
            document["updatedAt"] = updated.strip()
    return document


def save_operator_confirmation(enabled: bool, path: str | None = None) -> dict[str, Any]:
    target = path or PATH
    document = {
        "enabled": bool(enabled),
        "updatedAt": datetime.now(timezone.utc).isoformat(),
    }
    directory = os.path.dirname(target) or "."
    os.makedirs(directory, exist_ok=True)
    tmp_path = f"{target}.tmp"
    with open(tmp_path, "w", encoding="utf-8") as handle:
        json.dump(document, handle, indent=2)
    os.replace(tmp_path, target)
    return document
