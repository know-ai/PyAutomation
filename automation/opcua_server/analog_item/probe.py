"""One-shot AnalogItemType probe against the live stack."""

from __future__ import annotations

from asyncua import ua

from ..address_space import AddressSpaceBuilder
from ..flags import analog_item_enabled
from .capability import ICapabilityProbe

_PROBE_ID = "pyautomation:analog-item-probe"


class AnalogItemProbe(ICapabilityProbe):
    """Create one variable, try the typedef swap, delete it. Result is cached."""

    def __init__(self, server) -> None:
        self._server = server
        self._cached: bool | None = None

    def probe(self) -> bool:
        if self._cached is not None:
            return self._cached
        if not analog_item_enabled():
            self._cached = False
            return False
        parent = self._server.objects
        idx = self._server._namespace_idx
        node = parent.add_variable(
            ua.NodeId(Identifier=_PROBE_ID, NamespaceIndex=idx),
            "analog_probe",
            0.0,
        )
        ok = AddressSpaceBuilder.swap_analog_item(node)
        try:
            node.delete()
        except Exception:
            ok = bool(ok)
        self._cached = bool(ok)
        return self._cached

    def cached(self) -> bool | None:
        return self._cached
