# -*- coding: utf-8 -*-
"""Quality alarm engine: process-PV BAD/stale → ALM.QUALITY.<tag>.

Invoked from Tag.set_value on quality/stale transitions. Fail-safe, re-entrant
safe, no JSON I/O. Events are rate-limited per tag.
"""
from __future__ import annotations

import logging
import threading
import time

from ..signal_conditioning.quality import publication_quality_label
from ..utils.quality_alarms import is_quality_subject, set_quality_degraded

_LOGGER = logging.getLogger("pyautomation")
_EVENT_COOLDOWN_S = 5.0

_tls = threading.local()
_event_lock = threading.Lock()
_last_event: dict[str, float] = {}


def notify_quality_transition(tag, *, degraded: bool) -> None:
    """Drive ALM.QUALITY and a forensic Event. Never raises. Never re-enters."""
    if getattr(_tls, "active", False):
        return
    if tag is None or not is_quality_subject(tag):
        return
    _tls.active = True
    try:
        name = getattr(tag, "name", "") or ""
        set_quality_degraded(name, degraded)
        _emit_quality_event(tag, degraded=degraded)
    except Exception:
        _LOGGER.debug("Quality alarm engine skipped tag=%s", getattr(tag, "name", None), exc_info=True)
    finally:
        _tls.active = False


def _emit_quality_event(tag, *, degraded: bool) -> None:
    name = getattr(tag, "name", "") or ""
    now = time.monotonic()
    with _event_lock:
        last = _last_event.get(name, 0.0)
        if now - last < _EVENT_COOLDOWN_S:
            return
        _last_event[name] = now
    try:
        from ..utils.system_event_audit import clip, persist_system_event

        quality = getattr(tag, "quality", None)
        substatus = getattr(tag, "quality_substatus", None)
        opc_code = getattr(tag, "opc_status_code", None)
        parts = [
            f"tag={name}",
            f"quality={publication_quality_label(quality)}",
            f"degraded={int(bool(degraded))}",
        ]
        if substatus:
            parts.append(f"substatus={substatus}")
        if opc_code is not None:
            parts.append(f"opc_code={int(opc_code)}")
        persist_system_event(
            message="Quality changed",
            description=clip("; ".join(parts), 256),
            classification="System",
            priority=3,
            criticity=4 if degraded else 2,
            area=getattr(tag, "area", None),
            source=tag,
        )
    except Exception:
        _LOGGER.debug("Quality change event skipped tag=%s", name, exc_info=True)
