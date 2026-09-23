"""Runtime flags for the embedded OPC UA server.

The address space is always canonical. These flags only tune the endpoint,
the AnalogItem probe and constant mode.

Complexity: each reader is O(1).
"""

from __future__ import annotations

import os
from pathlib import Path


def _truthy(raw: str | None) -> bool:
    return (raw or "").strip().lower() in {"1", "true", "yes", "on"}


def server_host() -> str:
    """Bind address. Complexity: O(1). Default 0.0.0.0."""
    raw = (os.environ.get("AUTOMATION_OPCUA_SERVER_HOST") or "0.0.0.0").strip()
    return raw or "0.0.0.0"


def analog_item_enabled() -> bool:
    """True unless AUTOMATION_OPCUA_ANALOG_ITEM is explicitly false. Complexity: O(1)."""
    raw = os.environ.get("AUTOMATION_OPCUA_ANALOG_ITEM")
    if raw is None:
        return True
    return _truthy(raw)


def constant_mode() -> bool:
    """Skip the full reconcile and use the rotating tag slice. Complexity: O(1)."""
    return _truthy(os.environ.get("AUTOMATION_OPCUA_CONSTANT_MODE"))


def namespace_uri() -> str:
    """Product namespace URI. Complexity: O(1) after the version file is read."""
    version = "2.9.0"
    path = Path(__file__).resolve().parents[2] / "version.py"
    try:
        ns: dict = {}
        exec(path.read_text(encoding="utf-8"), ns)
        version = str(ns.get("__version__") or version)
    except Exception:
        version = version
    parts = version.split(".")
    major_minor = ".".join(parts[:2]) if parts else "2.9"
    return f"urn:pyautomationio:opcua:{major_minor}"
