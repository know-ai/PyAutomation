"""Structured OPC UA client errors for API + HMI i18n."""

from __future__ import annotations

from typing import Any

CONNECTION_REFUSED = "connection_refused"
CONNECTION_TIMEOUT = "connection_timeout"
HOST_UNRESOLVED = "host_unresolved"
HOST_UNREACHABLE = "host_unreachable"
SESSION_CLOSED = "session_closed"
NOT_CONNECTED = "not_connected"
CLIENT_NOT_FOUND = "client_not_found"
BROWSE_FAILED = "browse_failed"
ADD_FAILED = "add_failed"
UPDATE_FAILED = "update_failed"
REMOVE_FAILED = "remove_failed"
DUPLICATE_NAME = "duplicate_name"
NOT_OWNED = "not_owned"
IDENTITY_MISSING = "identity_missing"
DISCOVERY_FAILED = "discovery_failed"
INVALID_REQUEST = "invalid_request"
UNKNOWN = "unknown"

CODES = {
    CONNECTION_REFUSED,
    CONNECTION_TIMEOUT,
    HOST_UNRESOLVED,
    HOST_UNREACHABLE,
    SESSION_CLOSED,
    NOT_CONNECTED,
    CLIENT_NOT_FOUND,
    BROWSE_FAILED,
    ADD_FAILED,
    UPDATE_FAILED,
    REMOVE_FAILED,
    DUPLICATE_NAME,
    NOT_OWNED,
    IDENTITY_MISSING,
    DISCOVERY_FAILED,
    INVALID_REQUEST,
    UNKNOWN,
}

DEFAULT_MESSAGES = {
    CONNECTION_REFUSED: "The OPC UA server refused the connection.",
    CONNECTION_TIMEOUT: "The OPC UA server did not respond in time.",
    HOST_UNRESOLVED: "The OPC UA host name could not be resolved.",
    HOST_UNREACHABLE: "The OPC UA host is unreachable.",
    SESSION_CLOSED: "The OPC UA session is no longer available.",
    NOT_CONNECTED: "The OPC UA client is not connected.",
    CLIENT_NOT_FOUND: "The OPC UA client was not found.",
    BROWSE_FAILED: "The OPC UA node tree could not be retrieved.",
    ADD_FAILED: "The OPC UA client could not be added.",
    UPDATE_FAILED: "The OPC UA client could not be updated.",
    REMOVE_FAILED: "The OPC UA client could not be removed.",
    DUPLICATE_NAME: "An OPC UA client with this name already exists.",
    NOT_OWNED: "This OPC UA client belongs to another edge node.",
    IDENTITY_MISSING: "Multi-edge node identity is not configured.",
    DISCOVERY_FAILED: "No OPC UA server was found at this address.",
    INVALID_REQUEST: "The request is not valid.",
    UNKNOWN: "OPC UA communication failed.",
}

_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    (CONNECTION_REFUSED, ("connection refused", "errno 111", "errno 61", "actively refused")),
    (CONNECTION_TIMEOUT, ("timed out", "timeout", "errno 110", "etimedout")),
    (HOST_UNRESOLVED, (
        "name or service not known",
        "nodename nor servname",
        "getaddrinfo",
        "could not translate host",
        "temporary failure in name resolution",
    )),
    (HOST_UNREACHABLE, ("network is unreachable", "no route to host", "errno 101", "errno 113")),
    (SESSION_CLOSED, ("badsessionid", "session closed", "connection closed", "broken pipe", "eof occurred")),
    (NOT_CONNECTED, ("cannot unpack", "nonetype", "not connected", "is not connected")),
    (DUPLICATE_NAME, ("duplicated", "already exists", "duplicate")),
    (NOT_OWNED, ("not owned", "another edge", "another node", "belongs to another")),
    (IDENTITY_MISSING, ("identity is not configured",)),
    (DISCOVERY_FAILED, ("servers not found", "failed to discover", "discover")),
    (CLIENT_NOT_FOUND, ("client not found", "client was not found")),
)


def classify_opcua_error(source: Any) -> str:
    if isinstance(source, dict):
        code = source.get("code")
        if isinstance(code, str) and code in CODES:
            return code
        parts = [source.get("error"), source.get("message"), source.get("url")]
        source = " ".join(str(part) for part in parts if part)
    elif isinstance(source, BaseException):
        source = f"{type(source).__name__}: {source}"
    text = str(source or "").lower()
    for code, needles in _RULES:
        if any(needle in text for needle in needles):
            return code
    return UNKNOWN


def opcua_error(code: str, message: str = "", **params: Any) -> dict[str, Any]:
    resolved = code if code in CODES else UNKNOWN
    payload: dict[str, Any] = {
        "code": resolved,
        "message": message or DEFAULT_MESSAGES[resolved],
    }
    clean = {key: value for key, value in params.items() if value not in (None, "")}
    if clean:
        payload["params"] = clean
    return payload


def from_connect_failure(data: Any, **params: Any) -> dict[str, Any]:
    extra = dict(params)
    raw: Any = data
    if isinstance(data, dict):
        if data.get("url") and "url" not in extra:
            extra["url"] = data["url"]
        raw = data.get("error") or data.get("message") or data
        if data.get("code") in CODES:
            return opcua_error(str(data["code"]), message=str(data.get("message") or ""), **extra)
    return opcua_error(classify_opcua_error(raw), **extra)


def unpack_result(result: Any) -> tuple[Any, Any]:
    if isinstance(result, tuple) and len(result) == 2:
        return result[0], result[1]
    return result, None
