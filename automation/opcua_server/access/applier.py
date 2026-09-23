"""Apply AccessLevel bits on an asyncua node. Complexity: O(1) per node."""

from __future__ import annotations

import logging

from asyncua import ua

from .level import AccessLevel

_LOG = logging.getLogger("pyautomation")

_BITS = (
    (ua.AccessLevel.CurrentRead, AccessLevel.CURRENT_READ),
    (ua.AccessLevel.CurrentWrite, AccessLevel.CURRENT_WRITE),
    (ua.AccessLevel.HistoryRead, AccessLevel.HISTORY_READ),
    (ua.AccessLevel.HistoryWrite, AccessLevel.HISTORY_WRITE),
    (ua.AccessLevel.SemanticChange, AccessLevel.SEMANTIC_CHANGE),
    (ua.AccessLevel.StatusWrite, AccessLevel.STATUS_WRITE),
    (ua.AccessLevel.TimestampWrite, AccessLevel.TIMESTAMP_WRITE),
)


async def _set_mask(node, attribute, mask: int) -> None:
    for flag, bit in _BITS:
        if int(mask) & int(bit):
            await node.set_attr_bit(attribute, flag)
        else:
            await node.unset_attr_bit(attribute, flag)


async def apply_level(node, access_level: int, user_access_level: int | None = None, restrictions: int = 0) -> bool:
    """Write AccessLevel and UserAccessLevel. Restrictions stay 0 when the stack has no attribute. Complexity: O(1)."""
    level = int(access_level) & 0x7F
    user = level if user_access_level is None else int(user_access_level) & 0x7F
    await _set_mask(node, ua.AttributeIds.AccessLevel, level)
    await _set_mask(node, ua.AttributeIds.UserAccessLevel, user)
    return await _write_restrictions(node, int(restrictions))


async def _write_restrictions(node, restrictions: int) -> bool:
    try:
        variant = ua.Variant(int(restrictions), ua.VariantType.UInt16)
        await node.write_attribute(ua.AttributeIds.AccessRestrictions, ua.DataValue(variant))
        return True
    except Exception:
        _LOG.debug("AccessRestrictions attribute is not available on this node", exc_info=True)
        return False
