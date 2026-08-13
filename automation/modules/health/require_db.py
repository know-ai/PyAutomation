# -*- coding: utf-8 -*-
"""HTTP adapter: historian query endpoints return 503 when the remote DB is down."""
from __future__ import annotations

from functools import wraps

from ...health import (
    DB_UNAVAILABLE_RETRY_AFTER_S,
    UnavailablePayload,
    get_database_health_service,
)


def db_unavailable_response():
    """Standard 503 body + Retry-After. No credentials, no internals."""
    body = UnavailablePayload().as_dict()
    headers = {"Retry-After": str(DB_UNAVAILABLE_RETRY_AFTER_S)}
    return body, 503, headers


def require_remote_db(fn):
    """Guard a REST handler. Must wrap *outside* token_required so auth is not
    forced to hit the Users table while PostgreSQL is unreachable.
    """

    @wraps(fn)
    def wrapper(*args, **kwargs):
        provider = get_database_health_service()
        if not provider.is_connected():
            return db_unavailable_response()
        return fn(*args, **kwargs)

    return wrapper
