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


def _resolve_alias(
    primary: str | None,
    alias: str | None,
    *,
    primary_name: str,
    alias_name: str,
) -> tuple[str | None, bool, str | None]:
    """Una sola identidad con dos nombres de env. Si ambos existen, deben coincidir."""
    primary = _clean(primary)
    alias = _clean(alias)
    if primary and alias and primary != alias:
        return None, True, (
            f"{primary_name} ({primary}) and {alias_name} ({alias}) must be the same value"
        )
    if primary:
        return primary, False, None
    return alias, False, None


@dataclass(frozen=True)
class NodeScope:
    node_id: str | None
    area: str | None
    site: str | None = None
    multi_edge_enabled: bool = True
    area_from_segment: bool = False
    site_from_manufacturer: bool = False
    identity_conflict: str | None = None

    @property
    def enabled(self) -> bool:
        return self.multi_edge_enabled

    @property
    def is_valid(self) -> bool:
        return (
            not self.multi_edge_enabled
            or bool(self.node_id and self.area and not self.identity_conflict)
        )

    @property
    def blocked_reason(self) -> str | None:
        if not self.multi_edge_enabled:
            return None
        if self.identity_conflict:
            return self.identity_conflict
        missing = []
        if not self.node_id:
            missing.append("AUTOMATION_NODE_ID")
        if not self.area:
            missing.append("AUTOMATION_AREA or AUTOMATION_SEGMENT")
        if missing:
            return "missing " + " and ".join(missing)
        return None

    @classmethod
    def from_env(cls, environ: Mapping[str, str] | None = None) -> "NodeScope":
        env = os.environ if environ is None else environ
        area, area_conflict, area_error = _resolve_alias(
            env.get("AUTOMATION_AREA"),
            env.get("AUTOMATION_SEGMENT"),
            primary_name="AUTOMATION_AREA",
            alias_name="AUTOMATION_SEGMENT",
        )
        site_primary = _clean(env.get("AUTOMATION_SITE"))
        site_alias = _clean(env.get("AUTOMATION_MANUFACTURER"))
        site_mismatch = bool(
            site_primary and site_alias and site_primary != site_alias
        )
        if site_mismatch:
            # SITE is optional metadata. Prefer the application name so a leftover
            # AUTOMATION_SITE cannot fail-close acquisition.
            site = site_alias
            site_from_manufacturer = True
        else:
            site = site_primary or site_alias
            site_from_manufacturer = site_primary is None and site is not None

        explicit_area = _clean(env.get("AUTOMATION_AREA"))
        return cls(
            node_id=_clean(env.get("AUTOMATION_NODE_ID")),
            area=None if area_conflict else area,
            site=site,
            multi_edge_enabled=_enabled(env.get("AUTOMATION_MULTI_EDGE_ENABLED")),
            area_from_segment=explicit_area is None and area is not None and not area_conflict,
            site_from_manufacturer=site_from_manufacturer,
            identity_conflict=area_error,
        )

    def validate_for_acquisition(self) -> "NodeScope":
        """Valida únicamente el contrato de arranque del plano de adquisición."""
        if not self.multi_edge_enabled:
            return self
        if self.identity_conflict:
            raise NodeIdentityError(self.identity_conflict)
        missing = []
        if not self.node_id:
            missing.append("AUTOMATION_NODE_ID")
        if not self.area:
            missing.append("AUTOMATION_AREA or AUTOMATION_SEGMENT")
        if missing:
            raise NodeIdentityError(
                "Multi-edge acquisition requires " + " and ".join(missing)
            )
        return self

    def owns_node(self, owner_node: object) -> bool:
        if not self.multi_edge_enabled:
            return True
        return self.is_valid and bool(owner_node) and str(owner_node) == self.node_id

    def owns_area(self, area: object) -> bool:
        """This edge owns its line area, plus unscoped/system events it created."""
        if not self.multi_edge_enabled:
            return True
        if not self.is_valid:
            return False
        if area is None:
            return True
        text = str(area).strip()
        if not text or text == "System":
            return True
        return text == self.area

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
