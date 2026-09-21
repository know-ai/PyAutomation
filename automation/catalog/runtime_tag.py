# -*- coding: utf-8 -*-
"""Runtime tag registration for historian / SAF without restart."""
from __future__ import annotations

import logging

_LOGGER = logging.getLogger("pyautomation")


def notify_tag_catalog_changed(
    tag_name: str,
    *,
    action: str = "upsert",
    reason: str = "runtime",
) -> None:
    """Tell connected HMIs to refresh tag pickers (Real-Time Trends, etc.)."""
    if not tag_name:
        return
    try:
        from automation import PyAutomation

        app = PyAutomation()
        sio = getattr(app, "sio", None)
        if sio is None:
            return
        sio.emit(
            "on.tag_catalog",
            data={"name": tag_name, "action": action, "reason": reason},
        )
    except Exception:
        _LOGGER.debug(
            "notify_tag_catalog_changed skipped name=%s action=%s",
            tag_name,
            action,
            exc_info=True,
        )


def ensure_tag_historian_catalog(tag, *, reason: str = "runtime") -> bool:
    """Ensure a CVT tag is visible to SAF (remote ``tags`` table + catalog push).

    Call after ``create_tag``, machine internal tags, or alarms that reference a
    tag so samples are not dropped with ``not in remote Tags``.
    """
    if tag is None:
        return False
    name = getattr(tag, "name", None)
    if not name and hasattr(tag, "get_name"):
        try:
            name = tag.get_name()
        except Exception:
            name = None
    if not name:
        return False

    try:
        from .seed import persist_tag_to_local

        persist_tag_to_local(tag)
    except Exception:
        _LOGGER.debug(
            "ensure_tag_historian_catalog local mirror skipped name=%s",
            name,
            exc_info=True,
        )

    historian_row = False
    try:
        from automation import PyAutomation

        app = PyAutomation()
        if app.is_db_connected():
            app.logger_engine.set_tag(tag=tag)
            from ..dbmodels.tags import Tags

            historian_row = Tags.read_by_name(name=name) is not None
            if not historian_row:
                _LOGGER.warning(
                    "Tag %s still missing in historian Tags after set_tag (%s)",
                    name,
                    reason,
                )
    except Exception:
        _LOGGER.warning(
            "ensure_tag_historian_catalog set_tag failed name=%s reason=%s",
            name,
            reason,
            exc_info=True,
        )

    try:
        from ..persistence.remote import clear_missing_tag_retry, nudge_tag_catalog_push

        nudge_tag_catalog_push(name)
        clear_missing_tag_retry(name)
    except Exception:
        _LOGGER.debug(
            "ensure_tag_historian_catalog nudge skipped name=%s",
            name,
            exc_info=True,
        )

    try:
        from .replicator import get_catalog_replicator

        worker = get_catalog_replicator()
        if worker is not None:
            worker.request_full_sync(reason=f"{reason}: {name}")
    except Exception:
        _LOGGER.debug(
            "ensure_tag_historian_catalog full-sync request skipped name=%s",
            name,
            exc_info=True,
        )

    notify_tag_catalog_changed(name, action="upsert", reason=reason)

    return historian_row
