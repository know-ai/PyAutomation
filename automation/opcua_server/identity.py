"""Canonical OPC UA NodeId strings.

Option B: MANUFACTURER is the {site} folder used to browse the tree.
It is not a structural field of the NodeId. A SCADA binding survives a change
of AUTOMATION_MANUFACTURER because the identifier is only type, area and name.

NodeId string (without the namespace index): ``<t|a|e>:<area>:<canonical_name>``.
"""

from __future__ import annotations

import functools
import re
import unicodedata

_WS = re.compile(r"\s+")
_UNSAFE_CTRL = re.compile(r"[\x00-\x1f\x7f]")
_MAX_NAME_LENGTH = 256
_INPUT_LIMIT = _MAX_NAME_LENGTH * 2
_RESERVED_PREFIXES = ("PyAutomationIO.", "SYS.", "ALM.PERF.", "alarm.SYS.")


class IdentityCounters:
    """Process-wide identity counters. They move on rejects and truncations, not on time."""

    collisions = 0
    reserved_rejected = 0
    length_truncated = 0


def note_collision() -> None:
    """Complexity: O(1)."""
    IdentityCounters.collisions += 1


def note_reserved() -> None:
    """Complexity: O(1)."""
    IdentityCounters.reserved_rejected += 1


def _note_truncated() -> None:
    IdentityCounters.length_truncated += 1


@functools.lru_cache(maxsize=10_000)
def _canonicalize_cached(name: str) -> tuple[str, bool]:
    text = unicodedata.normalize("NFC", name)
    text = _UNSAFE_CTRL.sub("", text)
    text = text.strip()
    text = _WS.sub(" ", text)
    text = text.casefold()
    text = text.replace(" ", ".")
    text = text.replace(";", "_").replace(",", "_")
    text = text.strip(".")
    cut = False
    if len(text) > _MAX_NAME_LENGTH:
        cut = True
        text = text[:_MAX_NAME_LENGTH].strip(".")
    return (text or "_", cut)


def canonicalize_name(name: str) -> str:
    """Normalize a business name. Complexity: O(len(name)) on a cache miss.

    Guarantees: deterministic, idempotent, case-insensitive, whitespace collapsed
    to dots, NFC, no ';' or ',', length at most 256, never empty.
    """
    if not name:
        return "_"
    clipped = len(name) > _INPUT_LIMIT
    bounded = name[:_INPUT_LIMIT] if clipped else name
    before = _canonicalize_cached.cache_info().misses
    text, cut = _canonicalize_cached(bounded)
    if _canonicalize_cached.cache_info().misses != before and (clipped or cut):
        _note_truncated()
    return text


canonicalize_name.cache_clear = _canonicalize_cached.cache_clear  # type: ignore[attr-defined]
canonicalize_name.cache_info = _canonicalize_cached.cache_info  # type: ignore[attr-defined]


@functools.lru_cache(maxsize=10_000)
def canonical_area(area: str | None) -> str:
    """Normalize an area. Empty or None becomes '_'. Complexity: O(len(area))."""
    if not (area or "").strip():
        return "_"
    return canonicalize_name(area or "")


def folder_token(value: str | None, default: str) -> str:
    """Browse folder name. Empty becomes the default, not '_'. Complexity: O(len(value))."""
    if not (value or "").strip():
        return default
    token = canonicalize_name(value or "")
    if token == "_":
        return default
    return token


def make_node_id(entity_type: str, area: str | None, name: str) -> str:
    """Build ``<type>:<area>:<name>``. MANUFACTURER is not a field. Complexity: O(len(name))."""
    if entity_type not in ("t", "a", "e"):
        raise ValueError(f"Unknown entity type: {entity_type!r}")
    return f"{entity_type}:{canonical_area(area)}:{canonicalize_name(name)}"


def normalize_tag_name(raw_name: str, manufacturer: str, segment: str) -> str:
    """Prefix a new tag as ``{site}.{area}.{short}`` when the prefix is missing. Complexity: O(len(name))."""
    site = (manufacturer or "").strip() or "Default"
    area = (segment or "").strip() or "Global"
    prefix = f"{site}.{area}."
    raw = raw_name or ""
    if raw.casefold().startswith(prefix.casefold()):
        return raw
    return prefix + raw


def validate_tag_name(name: str) -> None:
    """Reject a reserved system prefix. Complexity: O(len(name))."""
    canonical = canonicalize_name(name)
    for prefix in _RESERVED_PREFIXES:
        stem = canonicalize_name(prefix[:-1] if prefix.endswith(".") else prefix)
        if canonical == stem or canonical.startswith(stem + "."):
            note_reserved()
            raise ValueError(f"Tag name uses reserved prefix: {prefix}")


def conflicting_canonical_name(name: str, existing_names) -> str | None:
    """Return the other business name that canonicalizes to the same id. Complexity: O(N)."""
    target = canonicalize_name(name)
    for other in existing_names:
        if not other or other == name:
            continue
        if canonicalize_name(other) == target:
            note_collision()
            return other
    return None


def make_browse_name(name: str, entity_type: str) -> str:
    """Human-facing BrowseName. Case is preserved; whitespace is normalized."""
    text = unicodedata.normalize("NFC", name or "")
    text = _WS.sub(" ", text).strip()
    return text or f"{entity_type}_unnamed"


def short_browse_name(qualified_name: str, entity_type: str) -> str:
    """Last path segment, case preserved, for the tree leaf."""
    leaf = (qualified_name or "").strip().split(".")[-1]
    return make_browse_name(leaf, entity_type)


def classify_entity_kind(variable: str, data_type: str) -> str:
    """Return 'analog' | 'bool' | 'string'."""
    kind = (data_type or "").lower()
    if kind == "str":
        return "string"
    if kind == "bool":
        return "bool"
    return "analog"
