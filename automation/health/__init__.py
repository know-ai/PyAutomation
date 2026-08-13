# -*- coding: utf-8 -*-
"""Remote database visibility layer. Orthogonal to Store-and-Forward durability."""
from .interfaces import (
    DB_UNAVAILABLE_CODE,
    DB_UNAVAILABLE_MESSAGE,
    DB_UNAVAILABLE_RETRY_AFTER_S,
    HealthSnapshot,
    IHealthProvider,
    IReconnectionHandler,
    UnavailablePayload,
)
from .service import (
    DatabaseHealthService,
    get_database_health_service,
    set_database_health_service,
)

__all__ = [
    "DB_UNAVAILABLE_CODE",
    "DB_UNAVAILABLE_MESSAGE",
    "DB_UNAVAILABLE_RETRY_AFTER_S",
    "DatabaseHealthService",
    "HealthSnapshot",
    "IHealthProvider",
    "IReconnectionHandler",
    "UnavailablePayload",
    "get_database_health_service",
    "set_database_health_service",
]
