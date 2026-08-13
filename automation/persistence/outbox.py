# -*- coding: utf-8 -*-
"""Journal-first write helper shared by Events / Alarms / Logs loggers."""
from __future__ import annotations

import logging
from typing import Any, Callable

from .orchestrator import get_persistence_gateway
from .records import PersistableRecord


def _remote_failed(result: Any) -> bool:
    if result is None:
        return True
    if isinstance(result, tuple) and result and result[0] is None:
        return True
    return False


def journal_then_remote(
    record: PersistableRecord,
    remote_write: Callable[[], Any],
    connected: bool,
) -> tuple[Any, bool]:
    """Persist locally first. Remote success is the only ACK.

    Returns (remote_result_or_None, journaled).
    """
    gateway = get_persistence_gateway()
    journal_id = gateway.enqueue(record)
    if not connected:
        return None, True
    if journal_id:
        gateway.mark_replicating([journal_id])
    try:
        result = remote_write()
        if _remote_failed(result):
            if journal_id:
                gateway.mark_pending([journal_id], error="remote-write-returned-empty")
            return result, True
        if journal_id:
            gateway.mark_sent([journal_id])
        return result, True
    except Exception as err:
        if journal_id:
            gateway.mark_pending([journal_id], error=str(err))
        logging.getLogger("pyautomation").error(
            "SAF remote write failed after local journal; record kept PENDING",
            exc_info=True,
        )
        return None, True
