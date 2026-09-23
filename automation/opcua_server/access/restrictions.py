"""AccessRestrictions bitmask. Complexity: O(1)."""

from __future__ import annotations

from enum import IntFlag


class AccessRestrictions(IntFlag):
    """Three OPC UA Part 3 bits. v1 publishes zero."""

    SIGNING_REQUIRED = 0x0001
    ENCRYPTION_REQUIRED = 0x0002
    SESSION_REQUIRED = 0x0004
