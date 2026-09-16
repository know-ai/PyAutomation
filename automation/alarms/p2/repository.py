# -*- coding: utf-8 -*-
"""In-memory IAlarmRepository. Context: COLD/API. Complexity: O(1). Cota: _MAX_ALARMS."""
from __future__ import annotations

from contextlib import nullcontext
from typing import Any

from .constants import _MAX_ALARMS, _PRIORITY_DEFAULT


class MemoryAlarmRepository:
    """Context: COLD/API. Complexity: O(1) por PK. DIP: no Peewee."""

    def __init__(self):
        self._rows: dict[Any, dict[str, Any]] = {}

    def _row(self, alarm_id) -> dict[str, Any]:
        row = self._rows.get(alarm_id)
        if row is None:
            if len(self._rows) >= _MAX_ALARMS:
                oldest = next(iter(self._rows))
                self._rows.pop(oldest, None)
            row = {
                "priority": _PRIORITY_DEFAULT,
                "chattering": False,
                "chatter_count": 0,
            }
            self._rows[alarm_id] = row
        return row

    def get_priority(self, alarm_id) -> int:
        return int(self._row(alarm_id)["priority"])

    def set_priority(self, alarm_id, p: int) -> None:
        self._row(alarm_id)["priority"] = int(p)

    def set_chattering(self, alarm_id, value: bool) -> None:
        self._row(alarm_id)["chattering"] = bool(value)

    def set_chatter_count(self, alarm_id, count: int) -> None:
        self._row(alarm_id)["chatter_count"] = int(count)

    def transaction(self):
        return nullcontext()
