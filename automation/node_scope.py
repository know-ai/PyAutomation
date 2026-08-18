"""Identidad estable y alcance de una instancia de adquisición."""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Mapping


class NodeIdentityError(RuntimeError):
    """La adquisición no puede arrancar sin una identidad multi-edge válida."""


def _enabled(value: str | None, *, default: bool = True) -> bool:
    if value is None:
        return default
    return value.strip().lower() not in {"0", "false", "no", "off"}


def _clean(value: str | None) -> str | None:
    value = (value or "").strip()
    return value or None


@dataclass(frozen=True)
class NodeScope:
    node_id: str | None
    area: str | None
    site: str | None = None
    multi_edge_enabled: bool = True
    area_from_segment: bool = False

    @property
    def enabled(self) -> bool:
        return self.multi_edge_enabled

    @property
    def is_valid(self) -> bool:
        return (
            not self.multi_edge_enabled
            or bool(self.node_id and self.area)
        )

    @classmethod
    def from_env(cls, environ: Mapping[str, str] | None = None) -> "NodeScope":
        env = os.environ if environ is None else environ
        explicit_area = _clean(env.get("AUTOMATION_AREA"))
        legacy_area = _clean(env.get("AUTOMATION_SEGMENT"))
        return cls(
            node_id=_clean(env.get("AUTOMATION_NODE_ID")),
            area=explicit_area or legacy_area,
            site=_clean(env.get("AUTOMATION_SITE")),
            multi_edge_enabled=_enabled(env.get("AUTOMATION_MULTI_EDGE_ENABLED")),
            area_from_segment=explicit_area is None and legacy_area is not None,
        )

    def validate_for_acquisition(self) -> "NodeScope":
        """Valida únicamente el contrato de arranque del plano de adquisición."""
        if not self.multi_edge_enabled:
            return self
        missing = []
        if not self.node_id:
            missing.append("AUTOMATION_NODE_ID")
        if not self.area:
            missing.append("AUTOMATION_AREA")
        if missing:
            raise NodeIdentityError(
                "Multi-edge acquisition requires " + " and ".join(missing)
            )
        return self

    def owns_node(self, owner_node: object) -> bool:
        if not self.multi_edge_enabled:
            return True
        return self.is_valid and bool(owner_node) and str(owner_node) == self.node_id

    def owns_tag(self, tag: object) -> bool:
        if not self.multi_edge_enabled:
            return True
        if not self.is_valid or tag is None:
            return False
        owner_node = getattr(tag, "owner_node", None)
        return (
            bool(owner_node)
            and self.owns_node(owner_node)
            and getattr(tag, "area", None) == self.area
        )


def current_node_scope() -> NodeScope:
    """Lee el entorno actual; útil para workers creados después del import."""
    return NodeScope.from_env()


def get_node_scope() -> NodeScope:
    """Alias público para consumidores del plano runtime."""
    return current_node_scope()
