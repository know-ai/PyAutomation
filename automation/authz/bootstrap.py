# -*- coding: utf-8 -*-
"""Load default grants and in-memory cache after routes exist."""
from __future__ import annotations

import logging
from typing import Any

_LOGGER = logging.getLogger("pyautomation")


def resolve_flask_app(flask_app: Any | None = None) -> Any | None:
    """Best-effort Flask app for REST route discovery during authz seed."""
    if flask_app is not None:
        return flask_app
    try:
        from flask import current_app

        return current_app._get_current_object()
    except Exception:
        pass
    try:
        from .. import server as automation_server

        return automation_server
    except Exception:
        pass
    return None


def bootstrap_authz(flask_app=None) -> int:
    """Reload cache and insert missing default grants (HMI + REST when app is known)."""
    try:
        from .app_hooks import run_bootstrap_hooks
        from .catalog import collect_rest_keys
        from .seed import seed_default_grants
        from .store import reload_cache

        app = resolve_flask_app(flask_app)
        run_bootstrap_hooks(app)
        reload_cache(reason="boot")
        created = seed_default_grants(app)
        reload_cache(reason="seed")
        if app is not None:
            rest_count = len(collect_rest_keys(app))
            _LOGGER.info(
                "authz bootstrap complete grants_created=%s rest_resources=%s",
                created,
                rest_count,
            )
        return int(created or 0)
    except Exception:
        _LOGGER.warning("authz bootstrap skipped", exc_info=True)
        return 0
