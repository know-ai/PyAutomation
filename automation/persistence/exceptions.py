# -*- coding: utf-8 -*-


class JournalError(Exception):
    """Base error for the local durable journal."""


class JournalDiskFullError(JournalError):
    """Local journal cannot accept more PENDING records (disk / quota)."""


class JournalBackpressureError(JournalError):
    """Hot-path ring is full; acquisition of new history must slow down."""


class ReplicationError(JournalError):
    """Remote replication failed without losing local durability."""
