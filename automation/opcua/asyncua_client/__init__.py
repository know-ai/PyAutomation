"""Field OPC UA client on a dedicated asyncio thread."""

from .sync_adapter import get_runner

__all__ = ["get_runner"]
