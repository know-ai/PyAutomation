# -*- coding: utf-8 -*-
"""Journal-first write helper shared by Events / Alarms / Logs loggers."""
from __future__ import annotations

import logging
from typing import Any, Callable, Sequence

from .orchestrator import get_persistence_gateway
from .records import PersistableRecord

_LOGGER = logging.getLogger("pyautomation")


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


def journal_then_remote(
    record: PersistableRecord,
    remote_write: Callable[[], Any],
    connected: bool,
) -> tuple[Any, bool]:
    """Journal locally and return. ReplicationWorker is the only remote writer.

    ``remote_write`` and ``connected`` stay in the signature so existing callers
    compile. They are ignored: an inline INSERT would block ACK and the alarm
    worker on PostgreSQL during catch-up. Disk-full and backpressure still raise.
    """
    del remote_write, connected
    gateway = get_persistence_gateway()
    gateway.enqueue(record)
    return None, True


def journal_then_remote_batch(
    records: Sequence[PersistableRecord],
    remote_write: Callable[[], Any],
    connected: bool,
) -> tuple[Any, bool]:
    """One local COMMIT for the batch. Remote replay belongs to ReplicationWorker."""
    del remote_write, connected
    items = [record for record in records if record is not None]
    if not items:
        return None, False
    gateway = get_persistence_gateway()
    enqueue_many = getattr(gateway, "enqueue_many", None)
    if callable(enqueue_many):
        enqueue_many(items)
    else:
        for record in items:
            gateway.enqueue(record)
    return None, True
