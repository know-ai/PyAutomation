"""Catalog helpers for the SCADA end-to-end test."""

from __future__ import annotations


def tag_names(count: int = 100) -> list[str]:
    """O(count) names. The live test publishes one tag; the bench uses the full list."""
    return [f"t:l1:fi_{index:04d}" for index in range(count)]
