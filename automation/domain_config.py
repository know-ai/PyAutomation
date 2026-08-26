# -*- coding: utf-8 -*-
"""Optional DomainConfigurable contract for product engines.

PyAutomationIO does not import product modules. A machine exposes domain
configuration when it implements ``get_ui_schema``, ``get_config`` and
``put_config`` (duck-typing). The HMI renders those schemas in a generic slot.
"""
from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

SCHEMA_VERSION_SUPPORTED = 1

GENERIC_ATTRIBUTE_KEYS = frozenset(
    {
        "threshold",
        "on_delay",
        "interval",
        "execution_interval",
        "sample_interval",
        "sample_overrides",
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


def unknown_generic_attribute_keys(payload: dict | None) -> list[str]:
    if not payload:
        return []
    return sorted(key for key in payload.keys() if key not in GENERIC_ATTRIBUTE_KEYS)
