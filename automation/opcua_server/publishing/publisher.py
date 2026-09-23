"""Publication strategy. One strategy owns tags, alarms and engines."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class IPublisher(ABC):
    """Publish every entity on the same plane.

    Complexity:
      - publish_tag/alarm/engine: O(1) enqueue
      - materialize_*: O(1) bounded properties
      - shutdown: O(1), idempotent
    """

    plane: str = ""

    @abstractmethod
    def publish_tag(self, tag_object: Any) -> None:
        """Enqueue a CVT tag. O(1)."""

    @abstractmethod
    def publish_alarm(self, alarm_object: Any) -> None:
        """Enqueue an alarm. O(1)."""

    @abstractmethod
    def publish_engine(self, engine_object: Any) -> None:
        """Enqueue an engine. O(1)."""

    @abstractmethod
    def materialize_tag(self, tag_object: Any) -> bool:
        """Create the tag nodes. True when this call added a variable."""

    @abstractmethod
    def materialize_alarm(self, alarm_object: Any) -> bool:
        """Create the alarm nodes. True when this call added a variable."""

    @abstractmethod
    def materialize_engine(self, engine_object: Any) -> bool:
        """Create the engine nodes. True when this call added a variable."""

    @abstractmethod
    def shutdown(self) -> None:
        """Release publisher resources. Idempotent."""
