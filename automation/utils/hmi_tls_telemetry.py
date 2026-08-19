# -*- coding: utf-8 -*-
"""Debounced telemetry for benign remote HMI TLS handshake failures.

Remote browsers reconnecting over HTTPS with self-signed certificates, network
blips, or plain HTTP probes against the TLS port must not flood app.log with
gevent tracebacks. Emit one audit event per client IP per rate window instead.
"""
from __future__ import annotations

import logging
import os
import ssl
import threading
import time
from typing import Optional

_LOGGER = logging.getLogger("pyautomation.hmi_tls")

_IP_RATE_S = float(os.environ.get("AUTOMATION_HMI_TLS_IP_EVENT_WINDOW_S", "300"))
_LOCK = threading.Lock()
_IP_STATE: dict[str, dict[str, float | int | str]] = {}

_QUIET_MARKERS = (
    "CERTIFICATE_UNKNOWN",
    "CERTIFICATE_VERIFY_FAILED",
    "BAD_CERTIFICATE",
    "WRONG_VERSION_NUMBER",
    "HTTP_REQUEST",
    "HTTPS_PROXY_REQUEST",
    "UNEXPECTED_EOF_WHILE_READING",
    "EOF occurred in violation of protocol",
    "SSLV3_ALERT_CERTIFICATE_UNKNOWN",
    "TLSV1_ALERT_UNKNOWN_CA",
    "TLSV1_ALERT_PROTOCOL_VERSION",
)


def _reason_text(exc: BaseException) -> str:
    reason = getattr(exc, "reason", None)
    if reason:
        return str(reason)
    return str(exc)


def is_quiet_client_tls_error(exc: BaseException) -> bool:
    """True when the server-side error is a normal client disconnect / cert reject."""
    if isinstance(exc, (ssl.SSLZeroReturnError, ssl.SSLEOFError)):
        return True
    if isinstance(exc, ssl.SSLError):
        text = _reason_text(exc).upper()
        return any(marker.upper() in text for marker in _QUIET_MARKERS)
    if isinstance(exc, (BrokenPipeError, ConnectionResetError)):
        return True
    return False


def clip_reason(text: Optional[str], max_len: int = 120) -> str:
    normalized = " ".join(str(text or "").replace("\n", " ").split())
    if len(normalized) <= max_len:
        return normalized
    return normalized[: max_len - 1] + "…"


def clip_origin(text: Optional[str], max_len: int = 45) -> str:
    normalized = str(text or "").strip()
    if len(normalized) <= max_len:
        return normalized
    return normalized[: max_len - 1] + "…"


def record_client_tls_failure(exc: BaseException, origin: str = "") -> None:
    """Count a client-side TLS failure; emit at most one audit event per IP per window."""
    reason = clip_reason(_reason_text(exc))
    ip = clip_origin(origin) or "unknown"
    now = time.monotonic()
    emit = False
    count = 0
    sample = reason
    with _LOCK:
        state = _IP_STATE.get(ip)
        if state is None:
            state = {"count": 0, "window_start": now, "sample_reason": ""}
            _IP_STATE[ip] = state
        state["count"] = int(state.get("count", 0)) + 1
        if not state.get("sample_reason"):
            state["sample_reason"] = reason
        if now - float(state["window_start"]) < _IP_RATE_S:
            return
        emit = True
        count = int(state["count"])
        sample = str(state.get("sample_reason") or reason)
        state["count"] = 0
        state["window_start"] = now
        state["sample_reason"] = ""
    if not emit:
        return
    _LOGGER.debug(
        "Remote HMI TLS handshake failure: ip=%s count=%s sample=%s window_s=%s",
        ip,
        count,
        sample,
        int(_IP_RATE_S),
    )
    try:
        from .system_event_audit import clip, persist_system_event

        persist_system_event(
            message="HMI TLS handshake failure",
            description=clip(
                f"origin={ip}; count={count} in {int(_IP_RATE_S)}s; reason={sample}. "
                "Acquisition and historian are unaffected.",
                256,
            ),
            classification="HMI",
            priority=2,
            criticity=2,
            plant_wide=False,
        )
    except Exception:
        _LOGGER.debug("HMI TLS telemetry event skipped", exc_info=True)


def reset_for_tests() -> None:
    with _LOCK:
        _IP_STATE.clear()
