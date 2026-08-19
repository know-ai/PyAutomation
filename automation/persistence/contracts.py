# -*- coding: utf-8 -*-
"""SOLID contracts for the Phoenix durability layer.

Acquisition depends only on IPersistenceGateway. Replication depends on
IRemoteDB. Observability is segregated on IHealthProbe.
"""
from __future__ import annotations

from typing import Any, Iterable, Mapping, Protocol, Sequence, runtime_checkable


@runtime_checkable
class IPersistable(Protocol):
    def domain(self) -> str: ...
    def entity_id(self) -> str: ...
    def idempotency_key(self) -> str: ...
    def payload(self) -> Mapping[str, Any]: ...
    def is_critical(self) -> bool: ...


@runtime_checkable
class IPersistenceGateway(Protocol):
    def enqueue(self, persistable: IPersistable) -> int: ...
    def mark_sent(self, journal_ids: Sequence[int]) -> None: ...
    def pending_count(self) -> int: ...
    def flush_sync(self) -> None: ...


@runtime_checkable
class IPayloadMapper(Protocol):
    """Maps a journal JSON payload to dialect-agnostic insert rows (OCP)."""

    def to_rows(self, payloads: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]: ...


@runtime_checkable
class IRemoteDB(Protocol):
    def is_reachable(self) -> bool: ...
    def write_batch(self, domain: str, payloads: Sequence[Mapping[str, Any]]) -> int: ...
    def batch_insert_with_dedupe(self, payloads: Sequence[Mapping[str, Any]]) -> int: ...


@runtime_checkable
class IReplicationWorker(Protocol):
    def replicate_once(self) -> int: ...


@runtime_checkable
class IHealthProbe(Protocol):
    def snapshot(self) -> Mapping[str, Any]: ...


class NullRemoteDB:
    """Liskov-safe stand-in for chaos tests (always unreachable)."""

    def is_reachable(self) -> bool:
        return False

    def write_batch(self, domain: str, payloads: Sequence[Mapping[str, Any]]) -> int:
        raise RuntimeError("NullRemoteDB rejects all writes")

    def write_batch_outcomes(self, domain: str, payloads: Sequence[Mapping[str, Any]]) -> list[bool]:
        raise RuntimeError("NullRemoteDB rejects all writes")

    def batch_insert_with_dedupe(self, payloads: Sequence[Mapping[str, Any]]) -> int:
        raise RuntimeError("NullRemoteDB rejects all writes")
