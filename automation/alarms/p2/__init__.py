# -*- coding: utf-8 -*-
"""P2 alarm subsystem. SPEC-ISA18-2-P2-CLOSURE-v2. Cero I/O en HOT."""
from .chatter import ChatterDetector
from .clock import FakeClock, SystemClock
from .commands import AlarmAction
from .constants import (
    _ARCHIVE_CHUNK,
    _MAX_CHATTER_WINDOW,
    _PRIORITY_DEFAULT,
    _SUPPRESSION_CACHE_MAX,
)
from .footer import select_footer
from .kpi import KPICollector, KPIComputer
from .latching import LatchingPolicyRegistry
from .partition import PartitionManager
from .priority import PriorityManager
from .retention import RetentionArchiver
from .subsystem import AlarmSubsystem
from .suppression import SuppressionDecorator, SuppressionManager
from .suppression_cache import SuppressionCache
from .suppression_types import DisableType, OOSType, ShelveType, SilenceType, SuppressionType

__all__ = [
    "AlarmAction",
    "AlarmSubsystem",
    "ChatterDetector",
    "DisableType",
    "FakeClock",
    "KPICollector",
    "KPIComputer",
    "LatchingPolicyRegistry",
    "OOSType",
    "PartitionManager",
    "PriorityManager",
    "RetentionArchiver",
    "ShelveType",
    "SilenceType",
    "SuppressionCache",
    "SuppressionDecorator",
    "SuppressionManager",
    "SuppressionType",
    "SystemClock",
    "select_footer",
    "_ARCHIVE_CHUNK",
    "_MAX_CHATTER_WINDOW",
    "_PRIORITY_DEFAULT",
    "_SUPPRESSION_CACHE_MAX",
]
