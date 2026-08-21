# -*- coding: utf-8 -*-
"""Conflict policy for catalog sync.

Industrial rule:
- Offline-edited (dirty) local rows win when their version is newer than remote.
- Clean local rows never overwrite remote: central historian is SoT while linked.
- Ties and missing local stamps prefer remote.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class VersionStamp:
    version: int
    node_id: str | None = None


def resolve(
    local: VersionStamp | None,
    remote: VersionStamp | None,
    *,
    local_dirty: bool = False,
) -> str:
    """Return 'local', 'remote', or 'equal'.

    ``local_dirty`` is True when the edge authored an offline change
    (``catalog_versions.conflict_resolved is False`` for that row).
    """
    if local is None and remote is None:
        return "equal"
    if local is None:
        return "remote"
    if remote is None:
        return "local"
    # Clean local mirrors must not push clock skew over central.
    if not local_dirty:
        if int(remote.version) != int(local.version):
            return "remote"
        return "remote"
    if int(local.version) > int(remote.version):
        return "local"
    if int(remote.version) > int(local.version):
        return "remote"
    return "remote"
