# -*- coding: utf-8 -*-
"""Idempotency keys live on the journal UNIQUE index.

Remote writes treat a duplicate key as success so replay is exactly-once
at the business level (at-least-once + unique key).
"""
from __future__ import annotations

from typing import Iterable


class IdempotencyGuard:
    def already_seen(self, existing_keys: Iterable[str], candidate: str) -> bool:
        return candidate in existing_keys
