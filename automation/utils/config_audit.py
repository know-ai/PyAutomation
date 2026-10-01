# -*- coding: utf-8 -*-
"""Fail-safe audit for operator configuration changes.

One Events row per meaningful change, stamped with the actor. Never raises
into the request path. Never includes passwords, tokens or raw payloads.
"""
from __future__ import annotations

import logging
from typing import Any

from .system_event_audit import persist_system_event

_LOGGER = logging.getLogger("pyautomation")

CLIENT_PREFERENCE_VALUES = {
    "locale": frozenset({"es", "en"}),
    "theme": frozenset({"light", "dark"}),
    "display_density": frozenset({"auto", "workstation", "control", "wall"}),
    "show_infra_machines": frozenset({"true", "false"}),
    "display_timezone": frozenset({"plant", "local"}),
}


def record_configuration_event(
    *,
    message: str,
    description: str,
    user=None,
    priority: int = 2,
    criticity: int = 3,
) -> bool:
    """Persist one Configuration event. Returns False if it could not be stored."""
    try:
        actor = user
        if actor is None:
            actor = _current_user()
        return persist_system_event(
            message=message,
            description=description,
            classification="Configuration",
            priority=priority,
            criticity=criticity,
            user=actor,
        )
    except Exception:
        _LOGGER.error("Configuration audit skipped", exc_info=True)
        return False


def _current_user():
    try:
        from ..extensions import _api as Api

        return Api.get_current_user()
    except Exception:
        return None


def _charts(document: dict | None) -> dict[str, dict]:
    charts = {}
    for chart in (document or {}).get("charts") or []:
        if isinstance(chart, dict) and chart.get("id"):
            charts[str(chart["id"])] = chart
    return charts


def _identity(chart: dict) -> tuple:
    tags = chart.get("tagNames") or []
    if not isinstance(tags, list):
        tags = []
    return (chart.get("title"), tuple(tags), chart.get("timeSpanMinutes"))


def _box(chart: dict) -> tuple:
    return (chart.get("x"), chart.get("y"), chart.get("w"), chart.get("h"))


def realtime_trends_changes(before: dict | None, after: dict | None) -> list[tuple[str, str]]:
    """Added, edited, deleted and moved charts. Ignores timestamp-only saves."""
    events: list[tuple[str, str]] = []
    before_title = str((before or {}).get("panelTitle") or "")
    after_title = str((after or {}).get("panelTitle") or "")
    if before_title != after_title:
        events.append((
            "Real-time trends panel title updated",
            f"from={before_title or '-'} to={after_title or '-'}",
        ))

    previous = _charts(before)
    current = _charts(after)
    for chart_id, chart in current.items():
        if chart_id not in previous:
            tags = ",".join(str(name) for name in (chart.get("tagNames") or []))
            events.append((
                "Real-time trend chart added",
                f"chart={chart.get('title') or chart_id} tags={tags or '-'} span={chart.get('timeSpanMinutes')}",
            ))
    for chart_id, chart in previous.items():
        if chart_id not in current:
            events.append((
                "Real-time trend chart deleted",
                f"chart={chart.get('title') or chart_id} id={chart_id}",
            ))

    moved: list[str] = []
    for chart_id, chart in current.items():
        old = previous.get(chart_id)
        if old is None:
            continue
        if _identity(old) != _identity(chart):
            tags = ",".join(str(name) for name in (chart.get("tagNames") or []))
            events.append((
                "Real-time trend chart updated",
                (
                    f"chart={chart.get('title') or chart_id} "
                    f"from_title={old.get('title') or '-'} tags={tags or '-'} "
                    f"span={chart.get('timeSpanMinutes')}"
                ),
            ))
        elif _box(old) != _box(chart):
            moved.append(str(chart.get("title") or chart_id))
    if moved:
        events.append(("Real-time trend layout updated", "charts=" + ",".join(moved)))
    return events


def summary_column_changes(before: list | None, after: list | None) -> list[tuple[str, str]]:
    previous = [str(item) for item in (before or [])]
    current = [str(item) for item in (after or [])]
    if previous == current:
        return []
    added = [item for item in current if item not in previous]
    removed = [item for item in previous if item not in current]
    if not added and not removed:
        return [("Machines summary columns reordered", "columns=" + ",".join(current))]
    return [(
        "Machines summary columns updated",
        f"added={','.join(added) or '-'} removed={','.join(removed) or '-'}",
    )]


def grant_changes(
    subject_type: str,
    subject_id: str,
    before_rows: list | None,
    saved: list | None,
) -> list[tuple[str, str]]:
    previous: dict[tuple[str, str], str] = {}
    for row in before_rows or []:
        if not isinstance(row, dict):
            continue
        key = (str(row.get("resource_key") or ""), str(row.get("action") or "").lower())
        if key[0] and key[1]:
            previous[key] = str(row.get("effect") or "default").lower()
    diffs: list[str] = []
    for item in saved or []:
        if not isinstance(item, dict):
            continue
        resource = str(item.get("resource_key") or "")
        action = str(item.get("action") or "").lower()
        effect = str(item.get("effect") or "default").lower()
        if not resource or not action:
            continue
        old = previous.get((resource, action), "default")
        if old != effect:
            diffs.append(f"{resource} {action} {old}->{effect}")
    if not diffs:
        return []
    return [(
        "Authorization grants updated",
        f"subject={subject_type}:{subject_id} n={len(diffs)} " + "; ".join(diffs),
    )]


def client_preference_change(key: str, value: str) -> tuple[str, str] | None:
    allowed = CLIENT_PREFERENCE_VALUES.get(str(key or ""))
    normalized = str(value or "").strip().lower()
    if allowed is None or normalized not in allowed:
        return None
    return ("Workstation preference updated", f"key={key} to={normalized}")


def import_description(filename: str, result: Any) -> str:
    parts = [f"file={filename or '-'}"]
    summary = result.get("summary") if isinstance(result, dict) else None
    if isinstance(summary, dict):
        for key, value in summary.items():
            if isinstance(value, (int, float, str, bool)) and "password" not in str(key).lower():
                parts.append(f"{key}={value}")
    return " ".join(parts)


def settings_change_description(previous: dict | None, data: dict | None) -> str | None:
    payload = data or {}
    before = previous or {}
    keys = (
        "logger_period",
        "log_max_bytes",
        "log_backup_count",
        "log_level",
        "log_error_cooldown_seconds",
        "alarm_inhibit_uncertain_quality",
    )
    parts = []
    for key in keys:
        if key not in payload:
            continue
        old = before.get(key, "-")
        new = payload.get(key)
        if old != new:
            parts.append(f"{key}:{old}->{new}")
    if not parts:
        return None
    return " ".join(parts)
