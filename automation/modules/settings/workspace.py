# -*- coding: utf-8 -*-
"""Station-scoped HMI workspace persistence (survives host power cycle)."""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from typing import Any

WORKSPACE_KIND = "real-time-trends"
WORKSPACE_SCHEMA_VERSION = 3
WORKSPACE_SCOPE = "station"
MAX_STATION_CHARTS = 24
TITLE_MAX_LEN = 80
MAX_TAGS_PER_CHART = 16
TIME_SPAN_OPTIONS_MINUTES = (1, 2, 3, 5)
DEFAULT_TIME_SPAN_MINUTES = 2

GRID_COLS = 48
GRID_ROW_HEIGHT = 10
GRID_MARGIN_Y = 10
MIN_GRID_W = 16
MAX_GRID_W = 48
MIN_GRID_H = 15
MAX_GRID_H = 120
DEFAULT_GRID_W = 24
DEFAULT_GRID_H = 15

LEGACY_COLS = 12
LEGACY_ROW_HEIGHT = 40
LEGACY_MARGIN_Y = 10
LEGACY_MIN_W = 4
LEGACY_MAX_W = 12
LEGACY_MIN_H = 6
LEGACY_MAX_H = 48
LEGACY_DEFAULT_W = 6

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


def _time_span_from_legacy_buffer(buffer_size: Any) -> int:
    """Migrate old point-count buffers (120–360 @ ~1 Hz) to minutes."""
    try:
        parsed = int(buffer_size)
    except (TypeError, ValueError):
        return DEFAULT_TIME_SPAN_MINUTES
    if parsed <= 90:
        return 1
    if parsed <= 150:
        return 2
    if parsed <= 240:
        return 3
    return 5


def _sanitize_time_span_minutes(raw: dict[str, Any]) -> int:
    value = raw.get("timeSpanMinutes")
    if value is not None:
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            parsed = None
        if parsed in TIME_SPAN_OPTIONS_MINUTES:
            return parsed
    if raw.get("bufferSize") is not None:
        return _time_span_from_legacy_buffer(raw.get("bufferSize"))
    return DEFAULT_TIME_SPAN_MINUTES


def _span_px(rows: int, row_height: int, margin: int) -> int:
    n = max(0, int(rows))
    if n <= 0:
        return 0
    return n * row_height + (n - 1) * margin


def _rows_from_px(px: int, row_height: int, margin: int) -> int:
    step = row_height + margin
    if step <= 0:
        return 1
    return max(1, int(round((max(0, px) + margin) / step)))


def _incoming_is_legacy(raw: Any) -> bool:
    if not isinstance(raw, dict):
        return True
    try:
        version = int(raw.get("schemaVersion") or 1)
    except (TypeError, ValueError):
        version = 1
    grid = raw.get("grid") if isinstance(raw.get("grid"), dict) else {}
    cols = grid.get("cols")
    if version >= 3 and cols == GRID_COLS:
        return False
    if version <= 2:
        return True
    charts = raw.get("charts")
    if not isinstance(charts, list) or not charts:
        return version < 3
    for item in charts:
        if not isinstance(item, dict):
            continue
        try:
            width = int(item.get("w") or 0)
            x = int(item.get("x") or 0)
        except (TypeError, ValueError):
            continue
        if width > LEGACY_MAX_W or x + width > LEGACY_COLS:
            return False
    return True


def _migrate_box_to_v3(x: int, y: int, w: int, h: int) -> tuple[int, int, int, int]:
    y_px = y * (LEGACY_ROW_HEIGHT + LEGACY_MARGIN_Y)
    h_px = _span_px(max(h, 1), LEGACY_ROW_HEIGHT, LEGACY_MARGIN_Y)
    y_step = GRID_ROW_HEIGHT + GRID_MARGIN_Y
    return (
        int(round(x * (GRID_COLS / LEGACY_COLS))),
        int(round(y_px / y_step)),
        int(round(w * (GRID_COLS / LEGACY_COLS))),
        _rows_from_px(h_px, GRID_ROW_HEIGHT, GRID_MARGIN_Y),
    )


def _sanitize_bool(value: Any, default: bool = True) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"1", "true", "yes", "on"}:
            return True
        if lowered in {"0", "false", "no", "off"}:
            return False
    return default


def _sanitize_chart(raw: Any, index: int, *, legacy: bool) -> dict[str, Any] | None:
    if not isinstance(raw, dict):
        return None
    chart_id = raw.get("id")
    if not isinstance(chart_id, str) or not chart_id.strip():
        chart_id = f"stripchart-{index + 1}"
    else:
        chart_id = chart_id.strip()[:80]
    if legacy:
        x = _clamp_int(raw.get("x"), 0, LEGACY_MAX_W - LEGACY_MIN_W, 0)
        y = _clamp_int(raw.get("y"), 0, 10_000, 0)
        w = _clamp_int(raw.get("w"), LEGACY_MIN_W, LEGACY_MAX_W, LEGACY_DEFAULT_W)
        h = _clamp_int(raw.get("h"), LEGACY_MIN_H, LEGACY_MAX_H, LEGACY_MIN_H)
        x, y, w, h = _migrate_box_to_v3(x, y, w, h)
    else:
        x = _clamp_int(raw.get("x"), 0, MAX_GRID_W - MIN_GRID_W, 0)
        y = _clamp_int(raw.get("y"), 0, 10_000, 0)
        w = _clamp_int(raw.get("w"), MIN_GRID_W, MAX_GRID_W, DEFAULT_GRID_W)
        h = _clamp_int(raw.get("h"), MIN_GRID_H, MAX_GRID_H, DEFAULT_GRID_H)
    w = min(MAX_GRID_W, max(MIN_GRID_W, w))
    h = min(MAX_GRID_H, max(MIN_GRID_H, h))
    x = min(x, MAX_GRID_W - w)
    return {
        "id": chart_id,
        "title": _sanitize_title(raw.get("title"), f"Chart {index + 1}"),
        "tagNames": _sanitize_tag_names(raw.get("tagNames")),
        "timeSpanMinutes": _sanitize_time_span_minutes(raw),
        "showThresholds": _sanitize_bool(raw.get("showThresholds"), True),
        "x": max(0, x),
        "y": max(0, y),
        "w": w,
        "h": h,
    }


def sanitize_workspace(raw: Any) -> dict[str, Any]:
    charts_in: list[Any] = []
    updated_at = datetime.now(timezone.utc).isoformat()
    panel_title = ""
    legacy = _incoming_is_legacy(raw)
    if isinstance(raw, dict):
        maybe_charts = raw.get("charts")
        if isinstance(maybe_charts, list):
            charts_in = maybe_charts
        if isinstance(raw.get("updatedAt"), str) and raw["updatedAt"].strip():
            updated_at = raw["updatedAt"].strip()
        panel_title = _sanitize_title(raw.get("panelTitle"), "")
        if raw.get("panelTitle") in (None, ""):
            panel_title = ""
    elif isinstance(raw, list):
        charts_in = raw

    charts: list[dict[str, Any]] = []
    ids: set[str] = set()
    for item in charts_in:
        chart = _sanitize_chart(item, len(charts), legacy=legacy)
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
        "grid": {"cols": GRID_COLS, "rowHeight": GRID_ROW_HEIGHT},
        "panelTitle": panel_title,
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
