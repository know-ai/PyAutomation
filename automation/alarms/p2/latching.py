# -*- coding: utf-8 -*-
"""LatchingPolicy Strategy + Registry. Context: COLD. Complexity: O(1)."""
from __future__ import annotations

from abc import ABC, abstractmethod

from ..states import HISTORY_ACK, HISTORY_CLEARED, HISTORY_RTNUN


class LatchingPolicy(ABC):
    """Context: COLD. Complexity: O(1)."""

    @abstractmethod
    def should_record(self, from_state: str, to_state: str) -> bool: ...

    @abstractmethod
    def adjust_target_state(self, from_state: str, to_state: str) -> str: ...


class StandardLatching(LatchingPolicy):
    def should_record(self, f, t):
        return f != t

    def adjust_target_state(self, f, t):
        return t


class NonLatchingPolicy(LatchingPolicy):
    """INV-72: no-latching salta RTN Unack."""

    def should_record(self, f, t):
        return f != t

    def adjust_target_state(self, f, t):
        return HISTORY_CLEARED if t == HISTORY_RTNUN else t


class AutoAckPolicy(LatchingPolicy):
    """INV-73: ack_required=false auto-transiciona."""

    def should_record(self, f, t):
        return f != t

    def adjust_target_state(self, f, t):
        return HISTORY_CLEARED if t == HISTORY_ACK else t


class LatchingPolicyRegistry:
    """Registry: 5ª política se añade con register(), sin tocar el dispatcher."""

    _policies: dict[tuple[bool, bool], LatchingPolicy] = {
        (True, True): StandardLatching(),
        (False, True): NonLatchingPolicy(),
        (True, False): AutoAckPolicy(),
        (False, False): NonLatchingPolicy(),
    }

    @classmethod
    def register(cls, latching: bool, ack_required: bool, policy: LatchingPolicy) -> None:
        cls._policies[(bool(latching), bool(ack_required))] = policy

    @classmethod
    def for_alarm(cls, alarm) -> LatchingPolicy:
        """Context: COLD. Complexity: O(1) dict lookup."""
        key = (bool(getattr(alarm, "latching", True)), bool(getattr(alarm, "ack_required", True)))
        return cls._policies.get(key, cls._policies[(True, True)])
