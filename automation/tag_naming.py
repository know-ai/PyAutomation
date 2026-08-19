# -*- coding: utf-8 -*-
"""User-tag name qualification for multi-edge HMI creates (Site.Area.Base)."""
from __future__ import annotations

import os
from typing import NamedTuple


class TagNameError(ValueError):
    """Operator-facing tag name validation failure (HTTP 400)."""


class QualifiedTagName(NamedTuple):
    name: str
    base_name: str


def tag_name_validation_skipped(environ: dict | None = None) -> bool:
    env = os.environ if environ is None else environ
    raw = (env.get("AUTOMATION_SKIP_TAG_VALIDATION") or "").strip().lower()
    return raw in {"1", "true", "yes", "on"}


def _base_segment(name: str) -> str:
    parts = [p for p in (name or "").split(".") if p]
    return parts[-1] if parts else (name or "").strip()


def qualify_user_tag_name(
    name: str,
    site: str | None,
    area: str | None,
) -> QualifiedTagName:
    """Qualify a manual HMI tag name to ``Site.Area.Base``.

    Raises ``TagNameError`` for 2-part names, foreign 3-part names, and
    names with more than 3 parts (reserved for internal machine tags).
    """
    raw = (name or "").strip()
    if not raw:
        raise TagNameError("Tag name is required")
    if not site or not area:
        return QualifiedTagName(name=raw, base_name=_base_segment(raw))

    prefix = f"{site}.{area}"
    parts = [p for p in raw.split(".") if p]
    if len(parts) == 1:
        base = parts[0]
        return QualifiedTagName(name=f"{prefix}.{base}", base_name=base)
    if len(parts) == 2:
        raise TagNameError(
            f"Tag name must be in format 'Site.Area.TagName' or just 'TagName'. "
            f"For this node, the correct prefix is '{prefix}.'"
        )
    if len(parts) == 3:
        input_site, input_area, base = parts
        if input_site != site or input_area != area:
            raise TagNameError(
                f"Site/Area mismatch. This node is {prefix}. "
                f"Please use '{prefix}.{base}' or just '{base}'."
            )
        return QualifiedTagName(name=raw, base_name=base)
    raise TagNameError(
        "Invalid tag name format. Use 'Site.Area.TagName' or just 'TagName'. "
        "Names with more than 3 parts are reserved for internal system tags."
    )
