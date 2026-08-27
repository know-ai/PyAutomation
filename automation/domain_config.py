# -*- coding: utf-8 -*-
"""Optional DomainConfigurable contract for product engines.

PyAutomationIO does not import product modules. A machine exposes domain
configuration when it implements ``get_ui_schema``, ``get_config`` and
``put_config`` (duck-typing). The HMI renders those schemas in a generic slot.
"""
from __future__ import annotations

from typing import Any, Iterable, Mapping, Protocol, runtime_checkable

SCHEMA_VERSION_SUPPORTED = 1

GENERIC_ATTRIBUTE_KEYS = frozenset(
    {
        "threshold",
        "on_delay",
        "interval",
        "execution_interval",
        "sample_interval",
        "sample_overrides",
        "signal_modes",
        "buffer_size",
    }
)


@runtime_checkable
class DomainConfigurable(Protocol):
    def get_ui_schema(self) -> dict:
        """Return a versioned JSON schema describing domain config fields."""
        ...

    def get_config(self) -> dict:
        """Return the current domain configuration values."""
        ...

    def put_config(self, payload: dict) -> dict:
        """Validate, apply and persist domain configuration. Return effective config.

        Raise ``ValueError`` or ``TypeError`` on validation failure.
        """
        ...


def supports_domain_config(machine: Any) -> bool:
    required = ("get_ui_schema", "get_config", "put_config")
    return all(hasattr(machine, name) and callable(getattr(machine, name)) for name in required)


def supports_domain_files(machine: Any) -> bool:
    """Optional file upload hook used by POST /domain-config/files."""
    return supports_domain_config(machine) and callable(getattr(machine, "put_domain_files", None))


def unknown_generic_attribute_keys(payload: dict | None) -> list[str]:
    if not payload:
        return []
    return sorted(key for key in payload.keys() if key not in GENERIC_ATTRIBUTE_KEYS)


INTERNAL_CONFIG_KEYS = frozenset(
    {
        "_reset",
        "_set_factory",
        "_restart",
        "_files",
        "_warnings",
        "_effective_pressure_mode",
        "_pressure_tags_status",
        "_missing_tags_message",
    }
)


def domain_config_action(payload: Mapping[str, Any] | None) -> str:
    if not payload:
        return "save"
    if payload.get("_reset") is True:
        return "reset"
    if payload.get("_set_factory") is True:
        return "set_factory"
    if payload.get("_restart") is True:
        return "restart"
    return "save"


def _iter_schema_fields(schema: Mapping[str, Any] | None) -> Iterable[Mapping[str, Any]]:
    if not isinstance(schema, Mapping):
        return
    for section in schema.get("sections") or []:
        if not isinstance(section, Mapping):
            continue
        for field in section.get("fields") or []:
            if isinstance(field, Mapping) and field.get("key"):
                yield field
            nested = field.get("fields") if isinstance(field, Mapping) else None
            if isinstance(nested, list):
                for child in nested:
                    if isinstance(child, Mapping) and child.get("key"):
                        yield child


def _field_index(schema: Mapping[str, Any] | None) -> dict[str, Mapping[str, Any]]:
    return {str(field["key"]): field for field in _iter_schema_fields(schema)}


def _normalize_config_value(value: Any) -> Any:
    if isinstance(value, bool) or value is None:
        return value
    if isinstance(value, (int, float)):
        try:
            number = float(value)
        except (TypeError, ValueError):
            return value
        if not number == number:  # NaN
            return value
        return round(number, 6)
    if isinstance(value, str):
        return value.strip()
    return value


def _format_config_value(value: Any, field: Mapping[str, Any] | None) -> str:
    meta = field or {}
    if isinstance(value, bool):
        if value:
            return str(meta.get("true_label") or "sí")
        return str(meta.get("false_label") or "no")
    if meta.get("type") == "select":
        for option in meta.get("options") or []:
            if isinstance(option, Mapping) and option.get("value") == value:
                return str(option.get("label") or option.get("value"))
    if value is None or value == "":
        return "—"
    formatted = str(value)
    unit = meta.get("unit")
    if unit:
        return f"{formatted} {unit}"
    return formatted


def _field_caption(key: str, field: Mapping[str, Any] | None) -> str:
    meta = field or {}
    return str(meta.get("label") or meta.get("short_label") or key)


def diff_domain_config(
    before: Mapping[str, Any] | None,
    after: Mapping[str, Any] | None,
    schema: Mapping[str, Any] | None = None,
) -> list[dict[str, str]]:
    """Return friendly per-field changes, ignoring internal/read-only keys."""
    previous = dict(before or {})
    current = dict(after or {})
    fields = _field_index(schema)
    keys = sorted(
        key
        for key in set(previous) | set(current)
        if not str(key).startswith("_") and str(key) not in INTERNAL_CONFIG_KEYS
    )
    changes: list[dict[str, str]] = []
    for key in keys:
        old = _normalize_config_value(previous.get(key))
        new = _normalize_config_value(current.get(key))
        if old == new:
            continue
        field = fields.get(key)
        changes.append(
            {
                "key": key,
                "label": _field_caption(key, field),
                "from": _format_config_value(previous.get(key), field),
                "to": _format_config_value(current.get(key), field),
            }
        )
    return changes


def audit_domain_config_change(
    *,
    machine_name: str,
    payload: Mapping[str, Any] | None,
    before: Mapping[str, Any] | None,
    after: Mapping[str, Any] | None,
    schema: Mapping[str, Any] | None = None,
    user=None,
) -> None:
    """Write one Events row per changed field (plus factory actions). Never raises."""
    try:
        from .utils.system_event_audit import clip, persist_system_event
    except Exception:
        return

    action = domain_config_action(payload)
    changes = diff_domain_config(before, after, schema)
    name = str(machine_name or "máquina")

    def _emit(message: str, description: str) -> None:
        persist_system_event(
            message=clip(message, 256),
            description=clip(description, 256),
            classification="Configuration",
            priority=2,
            criticity=3,
            user=user,
        )

    try:
        if action == "reset":
            _emit(
                f"{name}: restauró valores de fábrica",
                "Se aplicaron los valores de fábrica de la configuración de dominio.",
            )
        elif action == "set_factory":
            _emit(
                f"{name}: fijó valores de fábrica",
                "La configuración actual queda como referencia de fábrica. Guardar no la modifica.",
            )
        for change in changes:
            _emit(
                f"{name}: cambió {change['label']}",
                f"De {change['from']} a {change['to']}.",
            )
    except Exception:
        return
