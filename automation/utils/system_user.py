"""Interactive HTTP scope for the bootstrap ``system`` user.

Internal workers still use the in-memory ``system`` user (sudo). HTTP sessions
authenticated as ``system`` may only reach user-management APIs.
"""

SYSTEM_USERNAME = "system"

SYSTEM_USER_ALLOWED_PREFIXES = (
    "/api/users/",
    "/api/health/",
    "/api/system/",
)

SYSTEM_USER_DENIED_EXACT = frozenset(
    {
        "/api/users/create_tpt",
    }
)


def is_system_username(username: str | None) -> bool:
    return (username or "").strip().lower() == SYSTEM_USERNAME


def _normalize_path(path: str) -> str:
    if not path:
        return "/"
    normalized = "/" + str(path).lstrip("/")
    if len(normalized) > 1:
        normalized = normalized.rstrip("/")
    return normalized or "/"


def system_user_path_allowed(path: str) -> bool:
    exact = _normalize_path(path)
    if exact in SYSTEM_USER_DENIED_EXACT:
        return False
    for prefix in SYSTEM_USER_ALLOWED_PREFIXES:
        allowed = _normalize_path(prefix)
        if exact == allowed or exact.startswith(f"{allowed}/"):
            return True
    return False
