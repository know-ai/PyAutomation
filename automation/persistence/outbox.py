# -*- coding: utf-8 -*-
"""Journal-first write helper shared by Events / Alarms / Logs loggers."""
from __future__ import annotations

import logging
from typing import Any, Callable, Sequence

from .orchestrator import get_persistence_gateway
from .records import PersistableRecord


def _remote_failed(result: Any) -> bool:
    if result is None:
        return True
    if isinstance(result, tuple) and result and result[0] is None:
        return True
    return False


def _close_ephemeral_historian() -> None:
    # Immediate remote write runs on the caller (SM/OPC/HTTP). Leave the
    # idle socket only on LoggerWorker; everyone else must close.
    try:
        from ..utils.db_connections import (
            close_current_greenlet_connection,
            keep_historian_socket,
        )
        from .. import PyAutomation

        if not keep_historian_socket():
            close_current_greenlet_connection(getattr(PyAutomation(), "_db", None))
    except Exception:
        logging.getLogger("pyautomation").debug(
            "ephemeral historian close after journal_then_remote skipped",
            exc_info=True,
        )


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
    finally:
        _close_ephemeral_historian()


def journal_then_remote_batch(
    records: Sequence[PersistableRecord],
    remote_write: Callable[[], Any],
    connected: bool,
) -> tuple[Any, bool]:
    """Journal-first bulk write: one COMMIT locally, then one remote transaction."""
    items = [record for record in records if record is not None]
    if not items:
        try:
            result = remote_write() if connected else None
            return result, False
        finally:
            _close_ephemeral_historian()

    gateway = get_persistence_gateway()
    enqueue_many = getattr(gateway, "enqueue_many", None)
    if callable(enqueue_many):
        journal_ids = [jid for jid in enqueue_many(items) if jid]
    else:
        journal_ids = [jid for jid in (gateway.enqueue(record) for record in items) if jid]
    if not connected:
        return None, True
    if journal_ids:
        gateway.mark_replicating(journal_ids)
    try:
        result = remote_write()
        if _remote_failed(result) or (isinstance(result, int) and result <= 0):
            if journal_ids:
                gateway.mark_pending(journal_ids, error="remote-write-returned-empty")
            return result, True
        if journal_ids:
            gateway.mark_sent(journal_ids)
        return result, True
    except Exception as err:
        if journal_ids:
            gateway.mark_pending(journal_ids, error=str(err))
        logging.getLogger("pyautomation").error(
            "SAF remote batch write failed after local journal; records kept PENDING",
            exc_info=True,
        )
        return None, True
    finally:
        _close_ephemeral_historian()
