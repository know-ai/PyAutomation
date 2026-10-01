"""Access events. Each description carries the transaction id. Complexity: O(1)."""

from __future__ import annotations

_EVENTS = {
    "received": ("OPC UA external write received", 3, 3),
    "rejected": ("OPC UA external write rejected", 3, 3),
    "field_ok": ("OPC UA field write OK", 2, 2),
    "field_failed": ("OPC UA field write failed", 4, 4),
    "loop": ("OPC UA loop detected", 5, 5),
    "rate": ("OPC UA rate limit hit", 3, 3),
    "oscillation": ("OPC UA oscillation detected", 4, 4),
    "changed": ("OPC UA access level changed", 2, 2),
    "rollback": ("OPC UA rollback executed", 3, 3),
}


def emit_access_event(kind: str, transaction_id: str, detail: str = "", user=None) -> None:
    """Persist one of the nine access events. Complexity: O(1). Never raises."""
    message, priority, criticity = _EVENTS[kind]
    try:
        from ..utils.system_event_audit import persist_system_event

        persist_system_event(
            message=message,
            description=f"{transaction_id} {detail}".strip(),
            classification="Configuration" if kind == "changed" else "Control",
            priority=priority,
            criticity=criticity,
            user=user,
            plant_wide=True,
        )
    except Exception:
        return


def note_metric(app, name: str, step: int = 1) -> None:
    """Increment one counter on the server metrics. Complexity: O(1)."""
    metrics = getattr(app, "metrics", None)
    if metrics is None:
        return
    setattr(metrics, name, int(getattr(metrics, name, 0)) + step)
