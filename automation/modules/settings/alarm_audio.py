# -*- coding: utf-8 -*-
"""Persisted alarm-audio profile. One document for the station."""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from typing import Any

from ...alarms.audio_profile import default_document, normalize_profiles

PATH = os.path.join(".", "db", "hmi_alarm_audio.json")


def load_alarm_audio(path: str | None = None) -> dict[str, Any]:
    """Missing or unreadable file returns the built-in profile. Never raises."""
    document = default_document()
    target = path or PATH
    if not os.path.isfile(target):
        return document
    try:
        with open(target, "r", encoding="utf-8") as handle:
            raw = json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        logging.getLogger("pyautomation").warning("Cannot read alarm audio profile: %s", exc)
        return document
    if not isinstance(raw, dict):
        return document
    try:
        document["profiles"] = normalize_profiles(raw.get("profiles"))
    except ValueError:
        document["profiles"] = default_document()["profiles"]
    document["muted"] = bool(raw.get("muted"))
    updated = raw.get("updatedAt")
    if isinstance(updated, str) and updated.strip():
        document["updatedAt"] = updated.strip()
    return document


def save_alarm_audio(payload: dict, path: str | None = None) -> dict[str, Any]:
    profiles = normalize_profiles((payload or {}).get("profiles"))
    document = {
        "muted": bool((payload or {}).get("muted")),
        "profiles": profiles,
        "updatedAt": datetime.now(timezone.utc).isoformat(),
    }
    target = path or PATH
    directory = os.path.dirname(target) or "."
    os.makedirs(directory, exist_ok=True)
    tmp_path = f"{target}.tmp"
    with open(tmp_path, "w", encoding="utf-8") as handle:
        json.dump(document, handle, indent=2)
    os.replace(tmp_path, target)
    return document
