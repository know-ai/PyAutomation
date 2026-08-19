# -*- coding: utf-8 -*-
"""Boolean system alarm for NTP / clock synchronization."""
from __future__ import annotations

import logging

from .connection_alarms import (
    _ALARM_TYPE,
    _TAG_DATA_TYPE,
    _TAG_UNIT,
    _TAG_VARIABLE,
    _app,
    _as_bool,
    _ensure_bool_alarm,
    _scoped_name,
    _write_disconnected,
)

_LOGGER = logging.getLogger("pyautomation")

NTP_TAG_NAME = "SYS.NTP.OutOfSync"
NTP_ALARM_NAME = "ALM.NTP.OutOfSync"
NTP_TAG_DESCRIPTION = "True when the edge clock is out of sync with plant NTP"
NTP_ALARM_DESCRIPTION = "Edge clock out of sync with plant NTP"


def ntp_tag_name() -> str:
    return _scoped_name(NTP_TAG_NAME)


def ntp_alarm_name() -> str:
    return _scoped_name(NTP_ALARM_NAME)


def ensure_ntp_sync_alarm() -> None:
    """Create the NTP sync BOOL alarm once. Never raises."""
    try:
        app = _app()
        _ensure_bool_alarm(
            app,
            tag_name=ntp_tag_name(),
            alarm_name=ntp_alarm_name(),
            tag_description=NTP_TAG_DESCRIPTION,
            alarm_description=NTP_ALARM_DESCRIPTION,
            display_name="NTP Out Of Sync",
        )
    except Exception:
        _LOGGER.error("Failed to ensure NTP sync alarm", exc_info=True)


def set_ntp_out_of_sync(out_of_sync: bool) -> None:
    """Drive the NTP sync alarm. Never raises."""
    try:
        ensure_ntp_sync_alarm()
        _write_disconnected(ntp_tag_name(), out_of_sync)
    except Exception:
        _LOGGER.error("Failed to update NTP sync alarm", exc_info=True)


def is_ntp_out_of_sync() -> bool:
    try:
        app = _app()
        tag = app.cvt.get_tag_by_name(ntp_tag_name())
        if tag is None:
            return False
        return _as_bool(getattr(tag.value, "value", False))
    except Exception:
        return False
