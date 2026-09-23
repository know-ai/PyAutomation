"""Canonical publication. IPublisher is the only contract; CanonicalPublisher is the only implementation.

Invariants: one plane, FIFO expose queue, shutdown is idempotent.
"""

from .publisher import IPublisher

__all__ = ["IPublisher"]
