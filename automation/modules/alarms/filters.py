# -*- coding: utf-8 -*-
"""In-memory filters for serialized alarm definitions (GET /alarms/)."""
from __future__ import annotations

from typing import Any, Mapping

_STATE_ALIASES: dict[str, frozenset[str]] = {
    "normal": frozenset({"normal", "norm"}),
    "unacknowledged": frozenset({"unacknowledged", "unack"}),
    "acknowledged": frozenset({"acknowledged", "acked"}),
    "rtn unacknowledged": frozenset({"rtn unacknowledged", "rtn unack", "rtnun"}),
    "shelved": frozenset({"shelved", "shlvd"}),
    "suppressed by design": frozenset({"suppressed by design", "suppressed", "dsupr"}),
    "out of service": frozenset({"out of service", "oosrv"}),
}


def _normalize(value: str) -> str:
    return " ".join(str(value or "").strip().lower().replace("_", " ").replace("-", " ").split())


def _state_tokens(state: Any) -> set[str]:
    tokens: set[str] = set()
    if state is None or state == "":
        return tokens
    if isinstance(state, Mapping):
        for key in ("state", "name", "mnemonic"):
            raw = state.get(key)
            if raw:
                tokens.add(_normalize(str(raw)))
        return tokens
    tokens.add(_normalize(str(state)))
    return tokens


def alarm_matches_search(alarm: Mapping[str, Any], query: str) -> bool:
    needle = str(query or "").strip().lower()
    if not needle:
        return True
    haystack = " ".join(
        str(alarm.get(key) or "")
        for key in ("name", "description", "display_name", "tag")
    ).lower()
    return needle in haystack


def alarm_matches_state(alarm: Mapping[str, Any], wanted: str) -> bool:
    needle = _normalize(wanted)
    if not needle:
        return True
    aliases = _STATE_ALIASES.get(needle, frozenset({needle}))
    return bool(_state_tokens(alarm.get("state")) & aliases)


def filter_serialized_alarms(
    alarms: list[Mapping[str, Any]],
    *,
    query: str = "",
    state: str = "",
) -> list[Mapping[str, Any]]:
    if not query and not state:
        return list(alarms)
    return [
        alarm
        for alarm in alarms
        if alarm_matches_search(alarm, query) and alarm_matches_state(alarm, state)
    ]
