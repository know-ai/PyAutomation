"""Eight contracts. Production classes are sealed after registration. Complexity: O(1)."""

from __future__ import annotations

from abc import ABC, abstractmethod

from ..registry import Registry

applier_registry: Registry[type] = Registry("access_applier")
validator_registry: Registry[type] = Registry("access_validator")
writeback_registry: Registry[type] = Registry("access_writeback")
router_registry: Registry[type] = Registry("access_router")
field_writer_registry: Registry[type] = Registry("access_field_writer")
rollback_registry: Registry[type] = Registry("access_rollback")
rate_registry: Registry[type] = Registry("access_rate")
oscillation_registry: Registry[type] = Registry("access_oscillation")


class IAccessLevelApplier(ABC):
    @abstractmethod
    async def apply(self, node, access_level: int, user_access_level: int | None = None, restrictions: int = 0) -> bool:
        """Apply the three attributes. Complexity: O(1)."""


class IValueValidator(ABC):
    @abstractmethod
    def check(self, access_level: int, user_access_level: int, value) -> object:
        """Return a StatusCode or None. Complexity: O(1)."""


class IWriteBackHandler(ABC):
    @abstractmethod
    def datachange_notification(self, node, val, data) -> None:
        """Enqueue one client write. Complexity: O(1)."""


class IPropagationRouter(ABC):
    @abstractmethod
    def route(self, tag, value, transaction) -> object:
        """Propagate one external write. Complexity: O(1) plus the field wait."""


class IFieldWriter(ABC):
    @abstractmethod
    def write(self, url: str, node_id: str, value) -> object:
        """Write one field node. Complexity: O(1) plus the network wait."""


class IRollbackService(ABC):
    @abstractmethod
    def revert(self, tag, previous) -> None:
        """Restore the previous CVT value. Complexity: O(1)."""


class IRateLimiter(ABC):
    @abstractmethod
    def allow(self, tag_key: str, session_key: str) -> bool:
        """Complexity: O(1)."""


class IOscillationDetector(ABC):
    @abstractmethod
    def observe(self, tag_key: str, value) -> bool:
        """Return True when the tag just became oscillatory. Complexity: O(1)."""


class AsyncuaApplier(IAccessLevelApplier):
    async def apply(self, node, access_level: int, user_access_level: int | None = None, restrictions: int = 0) -> bool:
        from .applier import apply_level

        return await apply_level(node, access_level, user_access_level, restrictions)


class RangeTypeValidator(IValueValidator):
    def check(self, access_level: int, user_access_level: int, value):
        from .enforcement import check_value_write

        return check_value_write(access_level, user_access_level, value=value)


class _Registered:
    """Placeholder so each registry has one production entry. Complexity: O(1)."""


def seal_registries() -> None:
    """Freeze every access registry. Complexity: O(1)."""
    for registry, key, item in (
        (applier_registry, "asyncua", AsyncuaApplier),
        (validator_registry, "range", RangeTypeValidator),
        (writeback_registry, "scada", _Registered),
        (router_registry, "field", _Registered),
        (field_writer_registry, "asyncua", _Registered),
        (rollback_registry, "cvt", _Registered),
        (rate_registry, "window", _Registered),
        (oscillation_registry, "window", _Registered),
    ):
        try:
            registry.register(key, item)
        except ValueError:
            continue
        registry.freeze()


class FakeApplier(IAccessLevelApplier):
    def __init__(self) -> None:
        self.calls = []

    async def apply(self, node, access_level: int, user_access_level: int | None = None, restrictions: int = 0) -> bool:
        self.calls.append((access_level, user_access_level, restrictions))
        return True


class FakeFieldWriter(IFieldWriter):
    def __init__(self, status: str = "ok") -> None:
        self.status = status
        self.calls = []

    def write(self, url: str, node_id: str, value):
        self.calls.append((url, node_id, value))
        return self.status


seal_registries()
