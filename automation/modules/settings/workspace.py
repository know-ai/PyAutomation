# -*- coding: utf-8 -*-
"""Station-scoped HMI workspace persistence (survives host power cycle)."""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from typing import Any

WORKSPACE_KIND = "real-time-trends"
WORKSPACE_SCHEMA_VERSION = 1
WORKSPACE_SCOPE = "station"
MAX_STATION_CHARTS = 24
TITLE_MAX_LEN = 80
MAX_TAGS_PER_CHART = 16
BUFFER_SIZE_MIN = 120
BUFFER_SIZE_MAX = 360
MIN_GRID_W = 4
MAX_GRID_W = 12
MIN_GRID_H = 6

WORKSPACE_PATH = os.path.join(".", "db", "hmi_workspace_realtime_trends.json")


def _clamp_int(value: Any, minimum: int, maximum: int, fallback: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return fallback
    return min(maximum, max(minimum, parsed))


def _sanitize_title(value: Any, fallback: str) -> str:
    if not isinstance(value, str):
        return fallback
    trimmed = "".join(ch for ch in value if ord(ch) >= 32).strip()
    if not trimmed:
        return fallback
    return trimmed[:TITLE_MAX_LEN]


def _sanitize_tag_names(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    names: list[str] = []
    seen: set[str] = set()
    for item in value:
        if not isinstance(item, str):
            continue
        name = item.strip()
        if not name or name in seen:
            continue
        seen.add(name)
        names.append(name)
        if len(names) >= MAX_TAGS_PER_CHART:
            break
    return names


def _sanitize_chart(raw: Any, index: int) -> dict[str, Any] | None:
    if not isinstance(raw, dict):
        return None
    chart_id = raw.get("id")
    if not isinstance(chart_id, str) or not chart_id.strip():
        chart_id = f"stripchart-{index + 1}"
    else:
        chart_id = chart_id.strip()[:80]
    return {
        "id": chart_id,
        "title": _sanitize_title(raw.get("title"), f"Chart {index + 1}"),
        "tagNames": _sanitize_tag_names(raw.get("tagNames")),
        "bufferSize": _clamp_int(raw.get("bufferSize"), BUFFER_SIZE_MIN, BUFFER_SIZE_MAX, BUFFER_SIZE_MIN),
        "x": _clamp_int(raw.get("x"), 0, MAX_GRID_W - MIN_GRID_W, 0),
        "y": _clamp_int(raw.get("y"), 0, 10_000, 0),
        "w": _clamp_int(raw.get("w"), MIN_GRID_W, MAX_GRID_W, 6),
        "h": _clamp_int(raw.get("h"), MIN_GRID_H, 48, MIN_GRID_H),
    }


def sanitize_workspace(raw: Any) -> dict[str, Any]:
    charts_in: list[Any] = []
    updated_at = datetime.now(timezone.utc).isoformat()
    if isinstance(raw, dict):
        maybe_charts = raw.get("charts")
        if isinstance(maybe_charts, list):
            charts_in = maybe_charts
        if isinstance(raw.get("updatedAt"), str) and raw["updatedAt"].strip():
            updated_at = raw["updatedAt"].strip()
    elif isinstance(raw, list):
        charts_in = raw

    charts: list[dict[str, Any]] = []
    ids: set[str] = set()
    for item in charts_in:
        chart = _sanitize_chart(item, len(charts))
        if not chart:
            continue
        chart_id = chart["id"]
        if chart_id in ids:
            chart_id = f"{chart_id}-{len(charts)}"
            chart["id"] = chart_id
        ids.add(chart_id)
        charts.append(chart)
        if len(charts) >= MAX_STATION_CHARTS:
            break

    return {
        "schemaVersion": WORKSPACE_SCHEMA_VERSION,
        "kind": WORKSPACE_KIND,
        "scope": WORKSPACE_SCOPE,
        "updatedAt": updated_at,
        "charts": charts,
    }


def empty_workspace() -> dict[str, Any]:
    return sanitize_workspace({"charts": []})


def load_realtime_trends_workspace() -> dict[str, Any]:
    if not os.path.isfile(WORKSPACE_PATH):
        return empty_workspace()
    try:
        with open(WORKSPACE_PATH, "r", encoding="utf-8") as handle:
            raw = json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        logging.warning("Cannot read realtime-trends workspace: %s", exc)
        return empty_workspace()
    return sanitize_workspace(raw)


def save_realtime_trends_workspace(raw: Any) -> dict[str, Any]:
    document = sanitize_workspace(raw)
    document["updatedAt"] = datetime.now(timezone.utc).isoformat()
    directory = os.path.dirname(WORKSPACE_PATH) or "."
    os.makedirs(directory, exist_ok=True)
    tmp_path = f"{WORKSPACE_PATH}.tmp"
    with open(tmp_path, "w", encoding="utf-8") as handle:
        json.dump(document, handle, indent=2)
    os.replace(tmp_path, WORKSPACE_PATH)
    return document
