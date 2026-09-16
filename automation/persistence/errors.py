# -*- coding: utf-8 -*-
"""Classify SAF remote failures: retryable outage vs poison payload vs idempotent ACK."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Sequence

RETRYABLE = "RETRYABLE"
POISON = "POISON"
IDEMPOTENT_OK = "IDEMPOTENT_OK"

_RETRYABLE_MARKERS = (
    "connection already closed",
    "cursor already closed",
    "connection is closed",
    "closed this connection",
    "ssl syscall",
    "eof detected",
    "server closed the connection",
    "could not connect",
    "connection refused",
    "connection reset",
    "timeout expired",
    "timed out",
    "unreachable",
    "name or service not known",
    "network is unreachable",
    "temporary failure",
)

_IDEMPOTENT_MARKERS = (
    "duplicate key",
    "unique constraint",
    "unique violation",
    "already exists",
    "on conflict",
)

_RETRYABLE_TYPE_NAMES = frozenset(
    {
        "OperationalError",
        "InterfaceError",
        "InternalError",
        "TimeoutError",
        "ConnectionError",
        "ConnectionRefusedError",
        "ConnectionResetError",
        "BrokenPipeError",
        "OSError",
        "socket.error",
    }
)

_POISON_TYPE_NAMES = frozenset(
    {
        "ValidationError",
        "JSONDecodeError",
        "KeyError",
        "TypeError",
    }
)


@dataclass
class RowOutcome:
    """Per-row remote result. ``error`` is set only when ``ok`` is False."""

    ok: bool
    error: Any = None

    def error_text(self) -> str:
        if self.error is None:
            return ""
        text = str(self.error).strip()
        return text[:512]

    def __bool__(self) -> bool:
        return bool(self.ok)

    def __eq__(self, other: Any) -> bool:
        if isinstance(other, bool):
            return bool(self.ok) is other
        if isinstance(other, RowOutcome):
            return bool(self.ok) == bool(other.ok)
        return NotImplemented

    def __radd__(self, other: Any) -> int:
        return int(other) + int(self.ok)

    def __add__(self, other: Any) -> int:
        if isinstance(other, RowOutcome):
            return int(self.ok) + int(other.ok)
        return int(self.ok) + int(other)


def classify_saf_error(exc: Any) -> str:
    """Return RETRYABLE, POISON or IDEMPOTENT_OK. Unknown → RETRYABLE (never DLQ)."""
    if exc is None:
        return RETRYABLE
    try:
        from ..utils.db_io import is_stale_historian_handle

        if is_stale_historian_handle(exc):
            return RETRYABLE
    except Exception:
        pass
    if isinstance(exc, (TimeoutError, ConnectionError, BrokenPipeError, OSError)):
        return RETRYABLE
    name = type(exc).__name__
    msg = str(exc or "").lower()
    if any(marker in msg for marker in _IDEMPOTENT_MARKERS):
        return IDEMPOTENT_OK
    if name in _RETRYABLE_TYPE_NAMES:
        return RETRYABLE
    if name == "IntegrityError":
        return POISON
    if name in _POISON_TYPE_NAMES:
        return POISON
    if name == "ValueError" and "unsupported saf domain" in msg:
        return RETRYABLE
    if name in {"TypeError", "ValueError"} and any(
        token in msg for token in ("malformed", "invalid json", "schema")
    ):
        return POISON
    if any(marker in msg for marker in _RETRYABLE_MARKERS):
        return RETRYABLE
    return RETRYABLE


def normalize_outcomes(raw: Any, count: int) -> list[RowOutcome]:
    """Accept list[bool], list[RowOutcome], list[dict] or list[tuple]."""
    if count <= 0:
        return []
    if raw is None:
        return [RowOutcome(False, "empty remote outcome")] * count
    items = list(raw) if not isinstance(raw, (str, bytes)) else [raw]
    out: list[RowOutcome] = []
    for index in range(count):
        if index >= len(items):
            out.append(RowOutcome(False, "missing remote outcome"))
            continue
        item = items[index]
        if isinstance(item, RowOutcome):
            out.append(item)
        elif isinstance(item, dict):
            ok = bool(item.get("ok", item.get("success", False)))
            out.append(RowOutcome(ok, None if ok else item.get("error")))
        elif isinstance(item, tuple):
            ok = bool(item[0]) if item else False
            err = item[1] if len(item) > 1 else None
            out.append(RowOutcome(ok, None if ok else err))
        elif item is True:
            out.append(RowOutcome(True))
        else:
            out.append(RowOutcome(False, item if item not in (False, None) else "remote skipped"))
    return out


def outcomes_as_bool(outcomes: Sequence[RowOutcome]) -> list[bool]:
    return [bool(item.ok) for item in outcomes]
