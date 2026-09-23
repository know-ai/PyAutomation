"""One observer per tag. Tag.attach stores ``_subject`` on the observer instance."""

from __future__ import annotations


class TagDirtyObserver:
    __slots__ = ("_subject", "_server")

    def __init__(self, server) -> None:
        self._server = server
        self._subject = None

    def update(self) -> None:
        tag = self._subject
        if tag is None:
            return
        if getattr(tag, "last_source", "internal") == "external":
            return
        self._server.mark_tag(tag)
