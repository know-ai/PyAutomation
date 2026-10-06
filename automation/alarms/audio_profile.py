"""ISA-18.2 audible annunciation profile.

Each alarm priority picks a catalog tone and a repeat interval.
More urgent priorities must repeat strictly faster. Priority 1 is the most urgent.
"""
from __future__ import annotations

from .p2.constants import alarm_priority_or_default

PRIORITIES = (1, 2, 3, 4)
SOUND_ID_MIN = 1
SOUND_ID_MAX = 12
MIN_REPEAT_SECONDS = 2
MAX_CUES = 1000

DEFAULT_PROFILES = (
    {"priority": 1, "soundId": 4, "repeatSeconds": 2},
    {"priority": 2, "soundId": 4, "repeatSeconds": 5},
    {"priority": 3, "soundId": 4, "repeatSeconds": 10},
    {"priority": 4, "soundId": 4, "repeatSeconds": 30},
)


def default_document() -> dict:
    return {
        "muted": False,
        "profiles": [dict(row) for row in DEFAULT_PROFILES],
        "updatedAt": None,
    }


def _state_text(alarm) -> str:
    state = getattr(alarm, "state", None)
    if isinstance(alarm, dict):
        state = alarm.get("state", state)
    if isinstance(state, dict):
        raw = state.get("state") or state.get("name") or state.get("mnemonic") or ""
    else:
        raw = getattr(state, "state", None)
        if raw is None:
            raw = getattr(state, "name", None) or state or ""
    return str(raw).strip().lower().replace("_", " ").replace("-", " ")


def is_strict_unacknowledged(alarm) -> bool:
    """Ribal rule: only ISA state Unacknowledged, not return-to-normal."""
    return _state_text(alarm) in {"unacknowledged", "unack"}


def cues_from_alarms(alarms, limit: int = MAX_CUES) -> list[dict]:
    """Compact id/priority pairs for alarms that must beep. Bounded."""
    cues = []
    cap = max(1, min(int(limit or MAX_CUES), MAX_CUES))
    for alarm in alarms:
        if not is_strict_unacknowledged(alarm):
            continue
        if isinstance(alarm, dict):
            identifier = alarm.get("identifier") or alarm.get("id") or alarm.get("name")
            priority = alarm.get("priority")
        else:
            identifier = getattr(alarm, "identifier", None) or getattr(alarm, "id", None) or getattr(alarm, "name", None)
            priority = getattr(alarm, "priority", None)
        if not identifier:
            continue
        cues.append({
            "id": str(identifier),
            "priority": alarm_priority_or_default(priority),
        })
        if len(cues) >= cap:
            break
    return cues


def _profile_map(profiles) -> dict[int, dict]:
    mapped = {}
    for row in profiles or []:
        if not isinstance(row, dict):
            continue
        try:
            priority = int(row.get("priority"))
        except (TypeError, ValueError):
            continue
        mapped[priority] = row
    return mapped


def normalize_profiles(profiles) -> list[dict]:
    """Return the four priority rows or raise ValueError."""
    mapped = _profile_map(profiles)
    if set(mapped) != set(PRIORITIES):
        raise ValueError("profiles must include priorities 1, 2, 3 and 4")
    normalized = []
    previous = None
    for priority in PRIORITIES:
        row = mapped[priority]
        try:
            sound_id = int(row.get("soundId"))
            repeat = int(row.get("repeatSeconds"))
        except (TypeError, ValueError) as exc:
            raise ValueError(f"priority {priority} needs an integer sound and interval") from exc
        if not SOUND_ID_MIN <= sound_id <= SOUND_ID_MAX:
            raise ValueError(f"sound {sound_id} is outside the catalog")
        if repeat < MIN_REPEAT_SECONDS:
            raise ValueError(f"priority {priority} interval must be at least {MIN_REPEAT_SECONDS}s")
        if previous is not None and repeat <= previous:
            raise ValueError(
                "Repeat intervals must increase as priority becomes less urgent: 1 < 2 < 3 < 4 (seconds)."
            )
        previous = repeat
        normalized.append({
            "priority": priority,
            "soundId": sound_id,
            "repeatSeconds": repeat,
        })
    return normalized


def urgent_priority(cues) -> int | None:
    """Lowest priority number among cues. None when nothing is unacknowledged."""
    found = None
    for cue in cues or []:
        try:
            priority = int(cue.get("priority"))
        except (AttributeError, TypeError, ValueError):
            continue
        if found is None or priority < found:
            found = priority
    return found
