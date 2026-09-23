"""Process-local hooks so CVT/alarms can mark the OPC server dirty in O(1)."""

from __future__ import annotations

_server = None


def bind(server) -> None:
    global _server
    _server = server


def unbind(server) -> None:
    global _server
    if _server is server:
        _server = None


def mark_tag_name(name: str) -> None:
    server = _server
    if server is not None and name:
        server.mark_tag_name(name)


def mark_alarm(name: str) -> None:
    server = _server
    if server is not None and name:
        server.mark_alarm(name)


def mark_engine(name: str) -> None:
    server = _server
    if server is not None and name:
        server.mark_engine(name)
