"""Browse folders under Engines. NodeIds stay on the tag; only the tree changes."""

from __future__ import annotations


def browse_under_default(entity_type: str, name: str) -> bool:
    """System tags and alarms live in Default. Plant data stays beside it."""
    if entity_type == "e":
        return False
    from .identity import canonicalize_name

    tokens = set(canonicalize_name(name).split("."))
    return "sys" in tokens or "alm" in tokens


def engine_folder_name(entity) -> str:
    """Last segment of a machine name: ``Supe.Linea1.LDS`` -> ``LDS``."""
    raw = getattr(entity, "name", "")
    text = getattr(raw, "value", raw)
    part = str(text or "").strip().split(".")[-1].strip()
    return part


def engine_groups_for_tag(tag_name: str) -> tuple[str, ...]:
    """Engine folders that should show this process tag. Empty keeps it under Process."""
    name = str(tag_name or "").strip()
    if not name:
        return ()
    try:
        from .. import PyAutomation

        machines = PyAutomation().get_machines() or []
    except Exception:
        return ()
    found: list[str] = []
    for item in machines:
        machine = item[0] if isinstance(item, (tuple, list)) else item
        label = engine_folder_name(machine)
        if not label or label.lower() in {"opcuaserver", "opcua_server"}:
            continue
        if name in _bound_tag_names(machine):
            found.append(label)
    return tuple(dict.fromkeys(found))


def _bound_tag_names(machine) -> set[str]:
    names: set[str] = set()
    for value in vars(machine).values():
        if type(value).__name__ != "ProcessType":
            continue
        tag = getattr(value, "tag", None)
        bound = getattr(tag, "name", None)
        if bound:
            names.add(str(bound))
    return names
