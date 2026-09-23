"""O(1) ownership check. Mirrors state_machine._scope_owns_tag without importing it."""

from __future__ import annotations


def owns_tag(tag) -> bool:
    try:
        from ..node_scope import get_node_scope

        scope = get_node_scope()
    except (ImportError, AttributeError):
        return True
    if not getattr(scope, "enabled", False):
        return True
    if not getattr(scope, "is_valid", False) or tag is None:
        return False
    try:
        return bool(scope.owns_tag(tag))
    except Exception:
        return False
