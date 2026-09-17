# -*- coding: utf-8 -*-
"""Host-application hooks run before ACL seed/catalog discovery.

Downstream apps (e.g. iDetectFugas) register a bootstrap hook so their REST
namespaces are mounted on the shared Flask app before grants are seeded.
They may also extend ``default_allows`` so product APIs get seed Allow rows.
"""
from __future__ import annotations

from typing import Any, Callable

BootstrapHook = Callable[[Any], None]
# role, resource_key, action → True allow, False deny, None defer to core matrix
DefaultAllowsHook = Callable[[str, str, str], bool | None]

_hooks: list[BootstrapHook] = []
_default_allows_hooks: list[DefaultAllowsHook] = []
_extra_rest_keys: set[str] = set()


def register_bootstrap_hook(callback: BootstrapHook) -> None:
    """Register a callable invoked before default grant seeding."""
    if callback not in _hooks:
        _hooks.append(callback)


def register_default_allows(callback: DefaultAllowsHook) -> None:
    """Register a product extension of the seed matrix (``default_allows``)."""
    if callback not in _default_allows_hooks:
        _default_allows_hooks.append(callback)


def extra_default_allows(role_name: str, resource_key: str, action: str) -> bool | None:
    """First non-None product decision, or None to keep the core matrix."""
    for hook in _default_allows_hooks:
        result = hook(role_name, resource_key, action)
        if result is not None:
            return result
    return None


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
