# -*- coding: utf-8 -*-
"""Host-application hooks run before ACL seed/catalog discovery.

Downstream apps (e.g. iDetectFugas) register a bootstrap hook so their REST
namespaces are mounted on the shared Flask app before grants are seeded.
"""
from __future__ import annotations

from typing import Any, Callable

BootstrapHook = Callable[[Any], None]

_hooks: list[BootstrapHook] = []
_extra_rest_keys: set[str] = set()


def register_bootstrap_hook(callback: BootstrapHook) -> None:
    """Register a callable invoked before default grant seeding."""
    if callback not in _hooks:
        _hooks.append(callback)


def register_rest_resource_keys(keys: list[str] | tuple[str, ...]) -> None:
    """Register REST resource keys not discoverable from url_map (optional)."""
    for key in keys:
        normalized = str(key or "").strip()
        if normalized.startswith("rest:"):
            _extra_rest_keys.add(normalized)


def extra_rest_keys() -> list[str]:
    return sorted(_extra_rest_keys)


def run_bootstrap_hooks(flask_app: Any | None) -> None:
    for hook in _hooks:
        hook(flask_app)
