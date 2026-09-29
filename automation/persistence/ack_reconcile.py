# -*- coding: utf-8 -*-
"""Apply journaled ACKs that never reached RAM (crash between COMMIT and the transition)."""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

from ..alarms.states import AlarmState
from .orchestrator import get_persistence_gateway
from .records import DOMAIN

_LOG = logging.getLogger("pyautomation")
_ACK_TARGETS = frozenset({"Ack Alarm", "Cleared"})


def reconcile_pending_acks(alarm_manager) -> int:
    journal = get_persistence_gateway().journal
    rows = journal.fetch_pending_domain(DOMAIN.ALARM_SUMMARY, 500)
    applied = 0
    for row in rows:
        payload = row.get("payload")
        if isinstance(payload, str):
            try:
                payload = json.loads(payload)
            except (TypeError, ValueError):
                continue
        if not isinstance(payload, dict):
            continue
        if payload.get("to_state") not in _ACK_TARGETS:
            continue
        name = payload.get("name") or row.get("entity_id")
        if not name:
            continue
        getter = getattr(alarm_manager, "get_alarm_by_name", None)
        alarm = getter(name) if callable(getter) else None
        if alarm is None:
            continue
        if alarm.state not in (AlarmState.UNACK, AlarmState.RTNUN):
            continue
        stamp = payload.get("ack_timestamp") or payload.get("timestamp")
        try:
            when = datetime.fromisoformat(stamp) if isinstance(stamp, str) else datetime.now(timezone.utc)
        except (TypeError, ValueError):
            when = datetime.now(timezone.utc)
        if when.tzinfo is None:
            when = when.replace(tzinfo=timezone.utc)
        try:
            if alarm._acknowledge_in_memory(when):
                applied += 1
        except Exception:
            _LOG.debug("SAF ack reconcile skipped alarm=%s", name, exc_info=True)
    if applied:
        _LOG.warning("SAF reconciled %s acknowledged alarm(s) from the journal", applied)
    return applied
