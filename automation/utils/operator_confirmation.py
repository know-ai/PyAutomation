# -*- coding: utf-8 -*-
"""Short-lived proof that an operator re-authenticated for one HMI action.

The token never carries a password. It is single-use, bound to method and
path, and expires quickly. Verification never raises into the caller.
"""
from __future__ import annotations

import logging
import threading
import time
import uuid
from urllib.parse import unquote

_PURPOSE = "operator-confirm"
_TTL_S = 45
_LOGGER = logging.getLogger("pyautomation")
_USED: dict[str, int] = {}
_LOCK = threading.Lock()


def normalize_api_path(path: str) -> str:
    raw = unquote(str(path or "").strip())
    if not raw.startswith("/"):
        raw = "/" + raw
    if not raw.startswith("/api"):
        raw = "/api" + raw
    if len(raw) > 1:
        raw = raw.rstrip("/")
    return raw


def is_restart_target(value: str | None) -> bool:
    target = str(value or "").strip().lower()
    return target in {"restart", "restarting"}


def action_requires_confirmation(method: str, path: str, target_state: str | None = None) -> bool:
    """True for alarm acknowledge, a leak classification, and an engine restart."""
    method_u = str(method or "").upper()
    normalized = normalize_api_path(path)
    if method_u == "POST" and (
        normalized == "/api/alarms/acknowledge_all"
        or normalized.startswith("/api/alarms/acknowledge/")
    ):
        return True
    if method_u == "PUT" and (
        normalized == "/api/leaks/report"
        or normalized.startswith("/api/leaks/report/")
    ):
        return True
    if (
        method_u == "PUT"
        and normalized.startswith("/api/machines/")
        and normalized.endswith("/transition")
        and is_restart_target(target_state)
    ):
        return True
    return False


def policy_enabled() -> bool:
    try:
        from ..modules.settings.operator_confirmation import load_operator_confirmation

        return bool(load_operator_confirmation().get("enabled"))
    except Exception:
        _LOGGER.debug("operator confirmation policy unread", exc_info=True)
        return False


def issue_confirmation_token(
    *,
    username: str,
    method: str,
    path: str,
    secret: str,
    target_state: str | None = None,
) -> str | None:
    try:
        import jwt

        now = int(time.time())
        payload = {
            "purpose": _PURPOSE,
            "sub": str(username or "").strip(),
            "method": str(method or "").upper(),
            "path": normalize_api_path(path),
            "to": str(target_state or "").strip().lower(),
            "jti": uuid.uuid4().hex,
            "iat": now,
            "exp": now + _TTL_S,
        }
        if not payload["sub"] or not secret:
            return None
        token = jwt.encode(payload, secret, algorithm="HS256")
        return token if isinstance(token, str) else token.decode("utf-8")
    except Exception:
        _LOGGER.error("operator confirmation token skipped", exc_info=True)
        return None


def consume_confirmation_token(
    token: str | None,
    *,
    method: str,
    path: str,
    secret: str,
    target_state: str | None = None,
) -> str | None:
    """Return the username if the token matches this request. Single use."""
    try:
        import jwt

        if not token or not secret:
            return None
        payload = jwt.decode(
            token,
            secret,
            algorithms=["HS256"],
            options={"require": ["exp", "sub", "method", "path", "jti", "purpose"]},
        )
        if payload.get("purpose") != _PURPOSE:
            return None
        if str(payload.get("method") or "").upper() != str(method or "").upper():
            return None
        if normalize_api_path(str(payload.get("path") or "")) != normalize_api_path(path):
            return None
        expected_to = str(payload.get("to") or "").strip().lower()
        actual_to = str(target_state or "").strip().lower()
        if expected_to != actual_to:
            return None
        jti = str(payload.get("jti") or "")
        exp = int(payload.get("exp") or 0)
        if not jti or not _remember(jti, exp):
            return None
        username = str(payload.get("sub") or "").strip()
        return username or None
    except Exception:
        return None


def _remember(jti: str, exp: int) -> bool:
    now = int(time.time())
    with _LOCK:
        stale = [key for key, until in _USED.items() if until < now]
        for key in stale:
            _USED.pop(key, None)
        if jti in _USED:
            return False
        _USED[jti] = exp
        return True


def reset_confirmation_tokens() -> None:
    """Test helper."""
    with _LOCK:
        _USED.clear()
