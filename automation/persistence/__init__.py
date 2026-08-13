# -*- coding: utf-8 -*-
"""Nuclear Store-and-Forward persistence layer (Phoenix Directive).

SQLite WAL is Plan A for durability. The remote historian (PostgreSQL / MySQL /
SQLite) is the distribution plane. Acquisition never waits on the network.
"""
from .config import SafConfig
from .contracts import IHealthProbe, IPayloadMapper, IPersistable, IPersistenceGateway, IRemoteDB, IReplicationWorker
from .cycle_dedupe import CycleSampleCache
from .exceptions import JournalBackpressureError, JournalDiskFullError, JournalError
from .health import SafHealthProbe
from .idempotent_insert import IdempotentBatchInserter
from .orchestrator import PersistenceOrchestrator, get_persistence_gateway, reset_persistence_gateway
from .records import DOMAIN, PersistableRecord
from .remote import TagValuePayloadMapper

__all__ = [
    "CycleSampleCache",
    "DOMAIN",
    "IHealthProbe",
    "IPayloadMapper",
    "IPersistable",
    "IPersistenceGateway",
    "IRemoteDB",
    "IReplicationWorker",
    "IdempotentBatchInserter",
    "JournalBackpressureError",
    "JournalDiskFullError",
    "JournalError",
    "PersistableRecord",
    "PersistenceOrchestrator",
    "SafConfig",
    "SafHealthProbe",
    "TagValuePayloadMapper",
    "get_persistence_gateway",
    "reset_persistence_gateway",
]
