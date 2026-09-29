"""Typed commands. Payloads are snapshots. Handlers do not read the CVT."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class StartEndpoint:
    host: str
    port: int
    namespace_uri: str
    shelf_file: str


@dataclass(frozen=True)
class ExposeEntity:
    entity_type: str
    name: str
    identifier: str
    site: str | None
    area: str | None
    folder: str
    browse: str
    initial: object
    properties: tuple[tuple[str, object], ...]
    access: int = 1
    groups: tuple[str, ...] = ()
    under_default: bool = False


@dataclass(frozen=True)
class ApplyAccess:
    namespace: str
    access_level: int


@dataclass(frozen=True)
class WriteItem:
    identifier: str
    data_value: object
    unit: str | None = None
    refresh: object | None = None


@dataclass(frozen=True)
class WriteValues:
    items: tuple[WriteItem, ...]


@dataclass(frozen=True)
class DropTag:
    name: str
    reexpose: bool = False


@dataclass(frozen=True)
class ResetServer:
    pass


@dataclass(frozen=True)
class StopServer:
    pass
