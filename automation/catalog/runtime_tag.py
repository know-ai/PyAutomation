# -*- coding: utf-8 -*-
"""Runtime tag registration for historian / SAF without restart."""
from __future__ import annotations

import logging
import time

_LOGGER = logging.getLogger("pyautomation")

_HISTORIAN_RETRY_ATTEMPTS = 3
_HISTORIAN_RETRY_SLEEP_S = 0.05


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


def _tag_name(tag) -> str | None:
    if tag is None:
        return None
    name = getattr(tag, "name", None)
    if not name and hasattr(tag, "get_name"):
        try:
            name = tag.get_name()
        except Exception:
            name = None
    return name or None


def ensure_tag_historian_catalog(
    tag,
    *,
    reason: str = "runtime",
    attempts: int = _HISTORIAN_RETRY_ATTEMPTS,
) -> bool:
    """Ensure a CVT tag is visible to SAF (remote ``tags`` table + catalog push).

    Call after ``create_tag``, machine internal tags, or alarms that reference a
    tag so samples are not dropped with ``not in remote Tags``.

    When the historian is connected, retries ``set_tag`` + verify a bounded
    number of times so callers can refuse ``Alarms.create`` until the FK exists.
    """
    name = _tag_name(tag)
    if not name:
        return False

    try:
        from .seed import persist_tag_to_local

        persist_tag_to_local(tag, update_units=False)
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
            from ..dbmodels.tags import Tags

            tries = max(1, int(attempts or 1))
            for attempt in range(tries):
                try:
                    app.logger_engine.set_tag(tag=tag)
                except Exception:
                    _LOGGER.debug(
                        "ensure_tag_historian_catalog set_tag attempt %s failed name=%s",
                        attempt + 1,
                        name,
                        exc_info=True,
                    )
                historian_row = Tags.read_by_name(name=name) is not None
                if historian_row:
                    break
                if attempt + 1 < tries:
                    time.sleep(_HISTORIAN_RETRY_SLEEP_S)
            if not historian_row:
                from ..utils.rate_limited_log import warning_once

                warning_once(
                    _LOGGER,
                    f"historian-tag-missing:{name}",
                    "Tag %s still missing in historian Tags after set_tag (%s)",
                    name,
                    reason,
                )
    except Exception:
        from ..utils.rate_limited_log import warning_once

        warning_once(
            _LOGGER,
            f"historian-tag-set-failed:{name}",
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


def ensure_named_tag_in_historian(tag_name: str, *, reason: str = "alarm-catalog") -> bool:
    """Resolve a CVT tag by name and ensure it exists in remote ``Tags``.

    Used by SAF ``_ensure_alarm_catalog`` and system-alarm helpers before
    ``Alarms.create`` so FK lookup never hits ``tag=None``.
    """
    if not tag_name:
        return False
    try:
        from automation import PyAutomation

        app = PyAutomation()
        tag = app.cvt.get_tag_by_name(tag_name)
        if tag is None:
            from ..utils.rate_limited_log import warning_once

            warning_once(
                _LOGGER,
                f"cvt-tag-missing:{tag_name}",
                "Cannot ensure historian tag '%s': missing in CVT (%s)",
                tag_name,
                reason,
            )
            return False
        if not app.is_db_connected():
            # Local catalog only — caller may still create in-memory alarms.
            try:
                from .seed import persist_tag_to_local

                persist_tag_to_local(tag, update_units=False)
            except Exception:
                pass
            return True
        return ensure_tag_historian_catalog(tag, reason=reason)
    except Exception:
        from ..utils.rate_limited_log import warning_once

        warning_once(
            _LOGGER,
            f"ensure-named-tag-failed:{tag_name}",
            "ensure_named_tag_in_historian failed name=%s reason=%s",
            tag_name,
            reason,
            exc_info=True,
        )
        return False
