"""Frozen commands from the gevent thread to the field-client loop."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

@dataclass(frozen=True)
class Connect:
    url: str
    client_name: str
    correlation_id: str
    timeout: float = 60.0
    username: str | None = None
    password: str | None = None
@dataclass(frozen=True)
class Disconnect:
    client_name: str
    correlation_id: str
@dataclass(frozen=True)
class ReadBatch:
    client_name: str
    node_ids: tuple[str, ...]
    correlation_id: str
@dataclass(frozen=True)
class Subscribe:
    client_name: str
    node_ids: tuple[str, ...]
    period_ms: int
@dataclass(frozen=True)
class Unsubscribe:
    client_name: str
    node_ids: tuple[str, ...]
@dataclass(frozen=True)
class Browse:
    client_name: str
    node_id: str
    depth: int
    correlation_id: str
    mode: str = "tree"
    max_nodes: int = 50_000
    include_properties: bool = True
    include_property_values: bool = False
@dataclass(frozen=True)
class Write:
    client_name: str
    node_id: str
    value: Any
    correlation_id: str
@dataclass(frozen=True)
class Discover:
    url: str
    correlation_id: str
    kind: str
@dataclass(frozen=True)
class StopClientLoop:
    pass
@dataclass(frozen=True)
class ReadBatchResult:
    correlation_id: str
    data_values: tuple | None
@dataclass(frozen=True)
class DasResult:
    namespace: str
    value: Any
    status_code: Any
    source_timestamp: Any
@dataclass(frozen=True)
class CommandResult:
    correlation_id: str
    ok: bool
    payload: Any = None
    error: str | None = None
