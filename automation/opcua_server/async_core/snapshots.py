"""Build command snapshots on the gevent side. No network."""

from __future__ import annotations

import json

from ..data_value import to_data_value
from ..exposures.common import canonical_for, entity_area, entity_site, leaf_name
from ..identity import classify_entity_kind, make_node_id
from .commands import ExposeEntity, WriteItem

_FOLDERS = {"t": "Process", "a": "Alarms", "e": "Engines"}
_ALARM_PROPS = ("state", "process_condition", "mnemonic", "description")
_ENGINE_PROPS = ("state", "classification", "fluid")


def _text(value) -> str:
    if value is None:
        return ""
    inner = getattr(value, "value", value)
    return "" if inner is None else str(inner)


def _tag_properties(server, entity, kind: str) -> tuple[tuple[str, object], ...]:
    props: list[tuple[str, object]] = []
    variable = ""
    if hasattr(entity, "get_variable"):
        variable = entity.get_variable() or ""
    unit = entity.get_unit() if hasattr(entity, "get_unit") else getattr(entity, "unit", "")
    analog = getattr(server, "analog_item_supported", None)
    if kind == "analog" and analog:
        props.append(("EngineeringUnits", unit or ""))
    elif kind == "analog":
        props.append(("unit", unit or ""))
    props.append(("variable", variable or ""))
    props.append(("area", entity_area(entity) or ""))
    if kind != "analog":
        return tuple(props[:6])
    data_range = getattr(entity, "data_range", None)
    if data_range:
        props.append(("EURange", data_range))
    runtime = {}
    scan = entity.get_scan_time() if hasattr(entity, "get_scan_time") else None
    if scan:
        runtime["scan_time"] = scan
    dead = entity.get_dead_band() if hasattr(entity, "get_dead_band") else None
    if dead:
        runtime["dead_band"] = dead
    if runtime:
        props.append(("runtime_config", json.dumps(runtime)))
    if getattr(entity, "filter_enabled", False):
        props.append(
            (
                "filter_config",
                json.dumps(
                    {
                        "enabled": True,
                        "wavelet": getattr(entity, "filter_wavelet", None),
                        "level": getattr(entity, "filter_level", None),
                        "threshold_factor": getattr(entity, "filter_threshold_factor", None),
                    }
                ),
            )
        )
    return tuple(props[:6])


def _alarm_properties(entity) -> tuple[tuple[str, object], ...]:
    state = getattr(entity, "state", None)
    serialized = state.serialize() if hasattr(state, "serialize") else {}
    return tuple(
        (key, serialized.get(key, getattr(entity, key, "")) or "")
        for key in _ALARM_PROPS
    )


def _engine_properties(entity) -> tuple[tuple[str, object], ...]:
    payload = entity.serialize() if hasattr(entity, "serialize") else {}
    return tuple(
        (key, _text(payload.get(key, getattr(entity, key, ""))))
        for key in _ENGINE_PROPS
    )


def expose_snapshot(server, entity_type: str, name: str) -> ExposeEntity | None:
    """Complexity: O(P) property reads. No address-space call."""
    from ..runtime import _entity_for

    entity = _entity_for(server, entity_type, name)
    if entity is None:
        return None
    if entity_type == "e":
        label = _text(getattr(entity, "name", name))
        area = getattr(entity, "segment", None) or getattr(entity, "area", None)
        identifier = make_node_id("e", _text(area) or None, label)
        site = getattr(entity, "manufacturer", None)
        browse = label or name
        properties = _engine_properties(entity)
        kind = "analog"
    else:
        identifier = canonical_for(entity_type, entity)
        site = entity_site(entity)
        area = entity_area(entity)
        browse = leaf_name(entity, entity_type)
        if entity_type == "a":
            properties = _alarm_properties(entity)
            kind = "analog"
        else:
            data_type = ""
            if hasattr(entity, "get_data_type"):
                data_type = entity.get_data_type() or ""
            else:
                data_type = getattr(entity, "data_type", "") or ""
            variable = entity.get_variable() if hasattr(entity, "get_variable") else ""
            kind = classify_entity_kind(variable or "", data_type)
            properties = _tag_properties(server, entity, kind)
    initial = "" if kind == "string" else (False if kind == "bool" else 0.0)
    namespace = f"ns={int(getattr(server, '_namespace_idx', 0) or 0)};s={identifier}"
    access = 1
    try:
        access = int(server.access.resolve(namespace) or 1)
    except Exception:
        access = 1
    return ExposeEntity(
        entity_type=entity_type,
        name=name,
        identifier=identifier,
        site=_text(site) or None,
        area=_text(area) or None,
        folder=_FOLDERS[entity_type],
        browse=browse or name,
        initial=initial,
        properties=properties,
        access=access,
    )


def write_item(server, entity_type: str, name: str, server_ts) -> WriteItem | None:
    """Complexity: O(1). Tags carry a DataValue. Alarms and engines rewrite properties later."""
    from ..runtime import _entity_for

    entity = _entity_for(server, entity_type, name)
    if entity is None or entity_type != "t":
        if entity is None:
            return None
        snapshot = expose_snapshot(server, entity_type, name)
        if snapshot is None:
            return None
        return WriteItem(identifier=snapshot.identifier, data_value=snapshot)
    return WriteItem(identifier=canonical_for("t", entity), data_value=to_data_value(entity, server_ts))
