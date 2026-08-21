# -*- coding: utf-8 -*-
"""Journal-first write helper shared by Events / Alarms / Logs loggers."""
from __future__ import annotations

import logging
from typing import Any, Callable, Sequence

from .orchestrator import get_persistence_gateway
from .records import PersistableRecord

_LOGGER = logging.getLogger("pyautomation")


def _remote_failed(result: Any) -> bool:
    if result is None:
        return True
    if isinstance(result, tuple) and result and result[0] is None:
        return True
    return False


def _mark_app_historian_down(*, clear_live: bool = False) -> None:
    """Cooldown probe cooldown after a write/probe failure.

    Do **not** clear ``_db_live`` for ephemeral greenlet sockets (outbox callers):
    that made LoggerWorker think the historian was down, arm ALM.DB.Connection,
    then recover via check_connectivity without clearing the sticky alarm tag.
    Only the watchdog / explicit disconnect paths own ``_db_live=False``.
    """
    try:
        from .. import PyAutomation
        from ..utils.db_io import mark_remote_db_dead

        mark_remote_db_dead()
        if clear_live:
            PyAutomation()._db_live = False
    except Exception:
        _LOGGER.debug("mark historian down after outbox failure skipped", exc_info=True)


def historian_write_ready() -> bool:
    """True only if the bound Peewee handle can answer ``SELECT 1`` right now.

    ``is_db_connected()`` can briefly be True while another greenlet still holds
    a closed socket after reconnect. Probing the bound handle avoids
    ``InterfaceError: connection already closed`` on the immediate write.
    """
    try:
        from .. import PyAutomation
        from ..utils.db_connections import ensure_bound_connection
        from ..utils.db_io import probe_is_cooling_down

        if probe_is_cooling_down():
            return False
        app = PyAutomation()
        if not bool(getattr(app, "is_db_connected", lambda: False)()):
            return False
        db = None
        try:
            db = app.db_manager.get_db()
        except Exception:
            db = None
        if db is None:
            db = getattr(app, "_db", None)
        if db is None:
            return False
        ensure_bound_connection(db)
        return True
    except Exception as exc:
        from ..utils.db_io import log_historian_link_issue

        log_historian_link_issue(_LOGGER, exc, where="outbox.historian_write_ready", action="probe")
        _mark_app_historian_down()
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
        _LOGGER.debug(
            "ephemeral historian close after journal_then_remote skipped",
            exc_info=True,
        )


def journal_then_remote(
    record: PersistableRecord,
    remote_write: Callable[[], Any],
    connected: bool,
) -> tuple[Any, bool]:
    """Persist locally first. Remote success is the only ACK.

    Returns (remote_result_or_None, journaled). Never raises: stale sockets
    leave the row PENDING for SAF drain.
    """
    gateway = get_persistence_gateway()
    journal_id = gateway.enqueue(record)
    if not connected or not historian_write_ready():
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
        from ..utils.db_io import is_stale_historian_handle, log_historian_link_issue

        if journal_id:
            gateway.mark_pending([journal_id], error=str(err))
        log_historian_link_issue(_LOGGER, err, where="journal_then_remote", action="write")
        if is_stale_historian_handle(err):
            _mark_app_historian_down()
        else:
            _LOGGER.error(
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
            result = remote_write() if connected and historian_write_ready() else None
            return result, False
        finally:
            _close_ephemeral_historian()

    gateway = get_persistence_gateway()
    enqueue_many = getattr(gateway, "enqueue_many", None)
    if callable(enqueue_many):
        journal_ids = [jid for jid in enqueue_many(items) if jid]
    else:
        journal_ids = [jid for jid in (gateway.enqueue(record) for record in items) if jid]
    if not connected or not historian_write_ready():
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
        from ..utils.db_io import is_stale_historian_handle, log_historian_link_issue

        if journal_ids:
            gateway.mark_pending(journal_ids, error=str(err))
        log_historian_link_issue(_LOGGER, err, where="journal_then_remote_batch", action="write")
        if is_stale_historian_handle(err):
            _mark_app_historian_down()
        else:
            _LOGGER.error(
                "SAF remote batch write failed after local journal; records kept PENDING",
                exc_info=True,
            )
        return None, True
    finally:
        _close_ephemeral_historian()
