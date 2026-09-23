"""AnalogItem capability probe and explicit fallback."""

from .fallback import apply_analog_fallback
from .probe import AnalogItemProbe

__all__ = ["AnalogItemProbe", "apply_analog_fallback"]
