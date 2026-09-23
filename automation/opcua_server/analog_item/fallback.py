"""Record a single AnalogItem fallback per process start."""

from __future__ import annotations


def apply_analog_fallback(server, probe_ok: bool) -> None:
    """Set the builder flag. Audit and metric fire once when the probe fails."""
    supported = bool(probe_ok)
    if server.builder is not None:
        server.builder.analog_item_supported = supported
    server.analog_item_supported = supported
    if supported:
        return
    if getattr(server, "_analog_fallback_audited", False):
        return
    server._analog_fallback_audited = True
    server.metrics.analog_item_fallbacks = 1
    from ..audit import capability_fallback

    capability_fallback(
        capability="AnalogItemType",
        fallback="BaseDataVariableType",
        criticity=2,
    )
