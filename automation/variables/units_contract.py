# -*- coding: utf-8 -*-
"""Convert a live sample to ProcessType.unit (spec 12 §7, CA-UNIT-06/09)."""
from __future__ import annotations

import logging
from typing import Any

from ..utils.unit_metrics import inc_units_mismatch
from ..utils.unit_symbols import canonical_symbol

_LOGGER = logging.getLogger("pyautomation")


def _target_unit(process_type, target_unit: str | None) -> str | None:
    if target_unit:
        return canonical_symbol(target_unit)
    if process_type is None:
        return None
    return canonical_symbol(getattr(process_type, "unit", None))


def _emit_mismatch(process_type, value, target: str, exc: Exception) -> None:
    inc_units_mismatch()
    tag = getattr(process_type, "tag", None) if process_type is not None else None
    tag_name = getattr(tag, "name", None) or getattr(process_type, "name", None) or "?"
    src_unit = getattr(value, "unit", None)
    _LOGGER.warning(
        "UNITS_MISMATCH tag=%s from=%s to=%s: %s",
        tag_name,
        src_unit,
        target,
        exc,
    )
    try:
        from ..utils.system_event_audit import clip, persist_system_event

        persist_system_event(
            message=clip(f"Unit mismatch: {tag_name}", 256),
            description=clip(f"{src_unit} → {target}: {exc}", 256),
            classification="Configuration",
            priority=2,
            criticity=3,
        )
    except Exception:
        _LOGGER.debug("unit mismatch event skipped", exc_info=True)


def resolve_value_for_process_type(
    value: Any,
    process_type=None,
    *,
    target_unit: str | None = None,
    mutate: bool = True,
):
    """Convert ``value`` to the process-type SI unit.

    ``mutate=True`` uses ``change_unit`` (subscription path). ``mutate=False``
    uses ``convert`` and does not alter the source object (algorithm reads).
    On failure the original value is returned and ``UNITS_MISMATCH_COUNT``
    increments.
    """
    if value is None:
        return value
    target = _target_unit(process_type, target_unit)
    if not target:
        return value
    current = canonical_symbol(getattr(value, "unit", None))
    if current and current == target:
        return value
    try:
        if mutate and hasattr(value, "change_unit"):
            value.change_unit(unit=target)
            return value
        if hasattr(value, "convert"):
            converted = value.convert(target)
            if mutate and hasattr(value, "unit"):
                value.unit = target
                if hasattr(value, "value") and not isinstance(converted, type(value)):
                    try:
                        value.value = converted
                    except Exception:
                        pass
            return value if mutate else converted
        return value
    except Exception as exc:
        _emit_mismatch(process_type, value, target, exc)
        return value


def scan_process_type_unit_mismatches() -> int:
    """Count subscribed tags whose live value cannot convert to ProcessType.unit."""
    count = 0
    try:
        from .. import PyAutomation

        app = PyAutomation()
        machines = app.get_machines() if hasattr(app, "get_machines") else []
    except Exception:
        return 0
    for item in machines or []:
        machine = item[0] if isinstance(item, (tuple, list)) else item
        get_subs = getattr(machine, "get_subscribed_tags", None)
        if not callable(get_subs):
            continue
        try:
            subscribed = get_subs() or {}
        except Exception:
            continue
        for _tag_name, process_type in subscribed.items():
            target = _target_unit(process_type, None)
            if not target:
                continue
            value = getattr(process_type, "value", None)
            if value is None:
                tag = getattr(process_type, "tag", None)
                value = getattr(tag, "value", None) if tag is not None else None
            if value is None or not hasattr(value, "convert"):
                continue
            current = canonical_symbol(getattr(value, "unit", None))
            if current == target:
                continue
            try:
                value.convert(target)
            except Exception:
                count += 1
    return count
