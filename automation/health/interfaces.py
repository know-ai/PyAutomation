# -*- coding: utf-8 -*-
"""Contracts for remote-database visibility. Independent of Store-and-Forward."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional


DB_UNAVAILABLE_CODE = "DB_UNAVAILABLE"
DB_UNAVAILABLE_RETRY_AFTER_S = 30
DB_UNAVAILABLE_MESSAGE = (
    "La base de datos remota no está disponible. "
    "Los datos se están almacenando localmente y se sincronizarán automáticamente al reconectar."
)


@dataclass(frozen=True)
class HealthSnapshot:
    """Point-in-time view of remote DB reachability. Never includes credentials."""

    connected: bool
    latency_ms: Optional[float] = None
    message: str = ""
    checked_at: float = 0.0
    engine: str = "database"

    @property
    def status(self) -> str:
        return "ok" if self.connected else "error"

    def as_dict(self) -> dict:
        payload = {
            "status": self.status,
            "connected": self.connected,
            "latency_ms": None if self.latency_ms is None else round(self.latency_ms, 1),
            "message": self.message,
        }
        return payload


@dataclass(frozen=True)
class UnavailablePayload:
    status: str = "error"
    code: str = DB_UNAVAILABLE_CODE
    message: str = DB_UNAVAILABLE_MESSAGE
    retry_after: int = DB_UNAVAILABLE_RETRY_AFTER_S
    extras: dict = field(default_factory=dict)

    def as_dict(self) -> dict:
        body = {
            "status": self.status,
            "code": self.code,
            "message": self.message,
            "retry_after": self.retry_after,
        }
        body.update(self.extras)
        return body


class IHealthProvider(ABC):
    """Read-only connectivity probe. Query endpoints depend on this, not on reconnect."""

    @abstractmethod
    def is_connected(self) -> bool:
        raise NotImplementedError

    @abstractmethod
    def snapshot(self) -> HealthSnapshot:
        raise NotImplementedError


class IReconnectionHandler(ABC):
    """Reconnect surface. Not required by endpoints that only report status."""

    @abstractmethod
    def reconnect(self) -> HealthSnapshot:
        raise NotImplementedError
