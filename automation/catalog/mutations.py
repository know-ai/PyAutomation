# -*- coding: utf-8 -*-
"""Offline / dual-write helpers for every replicated catalog table.

All helpers never raise: catalog autonomy must not break the hot path.
"""
from __future__ import annotations

import logging
from typing import Any

from .local_db import get_catalog_database
from .local_provider import LocalCatalogProvider
from .partition import areas_compatible
from .versions import edge_node_id, now_ms

_LOGGER = logging.getLogger("pyautomation")


def _provider() -> LocalCatalogProvider | None:
    if get_catalog_database() is None:
        return None
    return LocalCatalogProvider()


def _find(table: str, *, field: str, value: Any) -> dict | None:
    provider = _provider()
    if provider is None or value is None:
        return None
    hit = provider.find_one(table, field=field, value=value)
    if hit is not None:
        return hit
    # Legacy fallback for odd column aliases — keep rare.
    needle = str(value)
    for row in provider.read_all(table):
        if str(row.get(field) or "") == needle:
            return row
        if field == "name" and str(row.get(field) or "").upper() == needle.upper():
            return row
    return None


def _find_by_any(table: str, **candidates) -> dict | None:
    provider = _provider()
    if provider is None:
        return None
    for key, value in candidates.items():
        if value is None:
            continue
        hit = provider.find_one(table, field=key, value=value)
        if hit is not None:
            return hit
    return None


def _upsert(table: str, payload: dict) -> str | None:
    provider = _provider()
    if provider is None:
        return None
    try:
        return provider.upsert(
            table,
            payload,
            node_id=edge_node_id(),
            version=now_ms(),
        )
    except Exception:
        _LOGGER.debug("catalog mutation upsert failed table=%s", table, exc_info=True)
        return None


def _delete(table: str, row: dict | None) -> None:
    provider = _provider()
    if provider is None or not row:
        return
    pk = row.get("_pk") or row.get("id")
    if pk is None:
        return
    try:
        provider.delete(table, str(pk))
    except Exception:
        _LOGGER.debug("catalog mutation delete failed table=%s pk=%s", table, pk, exc_info=True)


def ensure_named_row(table: str, name: str, *, extra: dict | None = None) -> dict | None:
    """Ensure a parent lookup row exists (segment, manufacturer, accesstype, …)."""
    if not name:
        return None
    existing = _find(table, field="name", value=name)
    if existing:
        return existing
    payload = {"name": name}
    if extra:
        payload.update(extra)
    pk = _upsert(table, payload)
    if pk is None:
        return None
    return _find(table, field="name", value=name) or {"_pk": pk, "id": pk, "name": name}


def soft_deactivate_tag_local(*, identifier: str | None = None, name: str | None = None) -> None:
    """Match historian logical delete: ``active=False``."""
    row = _find_by_any("tags", identifier=identifier, name=name)
    if not row:
        return
    payload = dict(row)
    payload["active"] = False
    _upsert("tags", payload)


def persist_alarm_fields_local(
    *,
    identifier: str,
    name: str | None = None,
    tag_name: str | None = None,
    description: str | None = None,
    alarm_type: str | None = None,
    trigger_value=None,
    state: str | None = None,
    on_delay=None,
    off_delay=None,
    on_delay_units: str | None = None,
    off_delay_units: str | None = None,
) -> None:
    """Update an alarm row already present in the local mirror."""
    row = _find_by_any("alarms", identifier=identifier, name=name)
    if not row:
        # Fall back to full persist helper when the row is missing.
        if name and tag_name:
            try:
                from .seed import persist_alarm_to_local

                persist_alarm_to_local(
                    identifier=identifier,
                    name=name,
                    tag_name=tag_name,
                    trigger_type=alarm_type or "HIGH",
                    trigger_value=trigger_value,
                    description=description or "",
                    state=state or "Normal",
                    on_delay=on_delay,
                    off_delay=off_delay,
                    on_delay_units=on_delay_units,
                    off_delay_units=off_delay_units,
                )
            except Exception:
                _LOGGER.debug("persist_alarm_fields_local create fallback failed", exc_info=True)
        return
    payload = dict(row)
    if name is not None:
        payload["name"] = name
    if description is not None:
        payload["description"] = description
    if trigger_value is not None:
        payload["trigger_value"] = trigger_value
    if tag_name:
        tag_row = _find("tags", field="name", value=tag_name)
        if tag_row:
            pk = tag_row.get("_pk") or tag_row.get("id")
            payload["tag"] = pk
            payload["tag_id"] = pk
    if alarm_type:
        type_row = _find("alarmtypes", field="name", value=str(alarm_type).upper())
        if type_row:
            pk = type_row.get("_pk") or type_row.get("id")
            payload["trigger_type"] = pk
            payload["trigger_type_id"] = pk
    if state:
        state_row = _find("alarmstates", field="name", value=state)
        if state_row is None:
            # Case-insensitive fallback
            for candidate in LocalCatalogProvider().read_all("alarmstates"):
                if str(candidate.get("name") or "").upper() == str(state).upper():
                    state_row = candidate
                    break
        if state_row:
            pk = state_row.get("_pk") or state_row.get("id")
            payload["state"] = pk
            payload["state_id"] = pk
    if on_delay is not None:
        payload["on_delay"] = on_delay
    if off_delay is not None:
        payload["off_delay"] = off_delay
    if on_delay_units is not None:
        payload["on_delay_units"] = on_delay_units
    if off_delay_units is not None:
        payload["off_delay_units"] = off_delay_units
    _upsert("alarms", payload)


def soft_delete_alarm_local(*, identifier: str) -> None:
    persist_alarm_fields_local(identifier=identifier, state="Out Of Service")


def persist_tagsmachines_bind(
    *,
    tag_name: str,
    machine_name: str,
    default_tag_name: str | None = None,
) -> None:
    tag_row = _find("tags", field="name", value=tag_name)
    machine_row = _find("machines", field="name", value=machine_name)
    if not tag_row or not machine_row:
        _LOGGER.debug(
            "tagsmachines bind skipped missing parents tag=%s machine=%s",
            tag_name,
            machine_name,
        )
        return
    if not areas_compatible(tag_row.get("area"), machine_row.get("area")):
        _LOGGER.warning(
            "tagsmachines bind refused cross-area tag=%s area=%s machine=%s area=%s",
            tag_name,
            tag_row.get("area"),
            machine_name,
            machine_row.get("area"),
        )
        return
    tag_pk = tag_row.get("_pk") or tag_row.get("id")
    machine_pk = machine_row.get("_pk") or machine_row.get("id")
    existing = None
    for row in LocalCatalogProvider().read_all("tagsmachines"):
        row_tag = row.get("tag_id") or row.get("tag")
        row_machine = row.get("machine_id") or row.get("machine")
        if str(row_tag) == str(tag_pk) and str(row_machine) == str(machine_pk):
            existing = row
            break
    payload = {
        "tag": tag_pk,
        "tag_id": tag_pk,
        "machine": machine_pk,
        "machine_id": machine_pk,
        "default_tag_name": default_tag_name,
    }
    if existing:
        payload["_pk"] = existing.get("_pk")
        payload["id"] = existing.get("id") or existing.get("_pk")
        if existing.get("sample_override") is not None and "sample_override" not in payload:
            payload["sample_override"] = existing.get("sample_override")
    _upsert("tagsmachines", payload)


def persist_tagsmachines_unbind(*, tag_name: str, machine_name: str) -> None:
    tag_row = _find("tags", field="name", value=tag_name)
    machine_row = _find("machines", field="name", value=machine_name)
    if not tag_row or not machine_row:
        return
    tag_pk = tag_row.get("_pk") or tag_row.get("id")
    machine_pk = machine_row.get("_pk") or machine_row.get("id")
    for row in LocalCatalogProvider().read_all("tagsmachines"):
        row_tag = row.get("tag_id") or row.get("tag")
        row_machine = row.get("machine_id") or row.get("machine")
        if str(row_tag) == str(tag_pk) and str(row_machine) == str(machine_pk):
            _delete("tagsmachines", row)
            break


def persist_tagsmachines_sample_override(
    *,
    tag_name: str,
    machine_name: str,
    sample_override,
) -> None:
    tag_row = _find("tags", field="name", value=tag_name)
    machine_row = _find("machines", field="name", value=machine_name)
    if not tag_row or not machine_row:
        return
    tag_pk = tag_row.get("_pk") or tag_row.get("id")
    machine_pk = machine_row.get("_pk") or machine_row.get("id")
    for row in LocalCatalogProvider().read_all("tagsmachines"):
        row_tag = row.get("tag_id") or row.get("tag")
        row_machine = row.get("machine_id") or row.get("machine")
        if str(row_tag) == str(tag_pk) and str(row_machine) == str(machine_pk):
            payload = dict(row)
            payload["sample_override"] = sample_override
            payload["tag"] = tag_pk
            payload["machine"] = machine_pk
            _upsert("tagsmachines", payload)
            return
    persist_tagsmachines_bind(tag_name=tag_name, machine_name=machine_name)
    persist_tagsmachines_sample_override(
        tag_name=tag_name,
        machine_name=machine_name,
        sample_override=sample_override,
    )


def persist_machine_fields_local(*, name: str, **fields) -> bool:
    """Update machine fields in the local catalog. Returns True on write.

    If the machine row is missing (created only in memory / YAML while offline),
    creates a minimal catalog row from the provided fields so subsequent edits stick.
    """
    row = _find("machines", field="name", value=name)
    if not row:
        cleaned = {}
        for key, value in fields.items():
            if value is None and key not in ("sample_interval",):
                continue
            if hasattr(value, "value"):
                value = value.value
            cleaned[key] = value
        if not cleaned:
            return False
        try:
            from .seed import persist_machine_to_local
            import secrets

            interval = cleaned.get("interval") or cleaned.get("execution_interval") or 1.0
            pk = persist_machine_to_local(
                identifier=cleaned.get("identifier") or secrets.token_hex(4),
                name=name,
                interval=interval,
                description=cleaned.get("description") or "",
                classification=cleaned.get("classification") or "",
                buffer_size=int(cleaned.get("buffer_size") or 10),
                buffer_roll_type=cleaned.get("buffer_roll_type") or "backward",
                criticity=int(cleaned.get("criticity") or 2),
                priority=int(cleaned.get("priority") or 1),
                on_delay=cleaned.get("on_delay"),
                threshold=cleaned.get("threshold"),
                area=cleaned.get("area"),
            )
            return pk is not None
        except Exception:
            _LOGGER.debug("persist_machine_fields_local create skipped name=%s", name, exc_info=True)
            return False
    payload = dict(row)
    for key, value in fields.items():
        if value is None and key not in ("sample_interval",):
            continue
        if hasattr(value, "value"):
            value = value.value
        payload[key] = value
    return _upsert("machines", payload) is not None


class _LocalOpcuaServerView:
    """Duck-type for ``OPCUAServer.serialize()`` when the historian is offline."""

    __slots__ = ("_row", "_access_name")

    def __init__(self, row: dict, access_name: str = "Read"):
        self._row = row
        self._access_name = access_name or "Read"

    def serialize(self) -> dict:
        pk = self._row.get("id") or self._row.get("_pk")
        return {
            "id": pk,
            "name": self._row.get("name"),
            "namespace": self._row.get("namespace"),
            "access_type": {"id": self._row.get("access_type_id") or self._row.get("access_type"), "name": self._access_name},
        }


def get_opcua_server_local(*, namespace: str):
    """Return a serialize()-able view of a local opcuaserver row, or None."""
    row = _find("opcuaserver", field="namespace", value=namespace)
    if not row:
        return None
    access_name = "Read"
    access_pk = row.get("access_type_id") or row.get("access_type")
    if access_pk is not None:
        access_row = _find("accesstype", field="id", value=access_pk) or _find(
            "accesstype", field="_pk", value=access_pk
        )
        if not access_row:
            # Integer PK lookup via provider.read
            provider = _provider()
            if provider is not None:
                access_row = provider.read("accesstype", str(access_pk))
        if access_row:
            access_name = str(access_row.get("name") or "Read")
    return _LocalOpcuaServerView(row, access_name=access_name)


def persist_opcua_server_local(
    *,
    name: str,
    namespace: str,
    access_type: str = "Read",
) -> None:
    existing = _find("opcuaserver", field="namespace", value=namespace) or _find(
        "opcuaserver", field="name", value=name
    )
    access_row = ensure_named_row("accesstype", access_type)
    access_pk = (access_row or {}).get("_pk") or (access_row or {}).get("id")
    if existing is not None:
        prev = existing.get("access_type_id") or existing.get("access_type")
        if str(prev or "") == str(access_pk or "") and str(existing.get("name") or "") == str(name):
            # Already mirrored — skip write (OPC UA address-space build hits this per node).
            return
    payload = {
        "name": name,
        "namespace": namespace,
        "access_type": access_pk,
        "access_type_id": access_pk,
    }
    if existing:
        payload["_pk"] = existing.get("_pk")
        payload["id"] = existing.get("id") or existing.get("_pk")
    _upsert("opcuaserver", payload)


def update_opcua_server_access_local(*, namespace: str, access_type: str) -> None:
    row = _find("opcuaserver", field="namespace", value=namespace)
    if not row:
        return
    access_row = ensure_named_row("accesstype", access_type)
    access_pk = (access_row or {}).get("_pk") or (access_row or {}).get("id")
    payload = dict(row)
    payload["access_type"] = access_pk
    payload["access_type_id"] = access_pk
    _upsert("opcuaserver", payload)


def ensure_segment_local(segment_name: str, *, manufacturer: str | None = None) -> dict | None:
    existing = _find("segment", field="name", value=segment_name)
    if existing:
        return existing
    mfr_name = manufacturer or "Default"
    mfr = ensure_named_row("manufacturer", mfr_name)
    mfr_pk = (mfr or {}).get("_pk") or (mfr or {}).get("id")
    return ensure_named_row(
        "segment",
        segment_name,
        extra={"manufacturer": mfr_pk, "manufacturer_id": mfr_pk},
    )


def persist_lrs_point_local(
    *,
    segment_name: str,
    kp: float,
    latitude: float,
    longitude: float,
    elevation: float | None = None,
    point_id: int | str | None = None,
) -> dict | None:
    segment = ensure_segment_local(segment_name)
    if not segment:
        return None
    segment_pk = segment.get("_pk") or segment.get("id")
    existing = None
    if point_id is not None:
        existing = _find_by_any("linearreferencinggeospatial", id=point_id, _pk=point_id)
    if existing is None:
        for row in LocalCatalogProvider().read_all("linearreferencinggeospatial"):
            seg = row.get("segment_id") or row.get("segment")
            if str(seg) == str(segment_pk) and float(row.get("kp") or 0) == float(kp):
                existing = row
                break
    payload = {
        "segment": segment_pk,
        "segment_id": segment_pk,
        "kp": float(kp),
        "latitude": float(latitude),
        "longitude": float(longitude),
        "elevation": elevation,
    }
    if existing:
        payload["_pk"] = existing.get("_pk")
        payload["id"] = existing.get("id") or existing.get("_pk")
    pk = _upsert("linearreferencinggeospatial", payload)
    if pk is None:
        return None
    row = _find_by_any("linearreferencinggeospatial", id=pk, _pk=pk) or payload
    return {
        "id": int(row.get("id") or row.get("_pk") or pk),
        "segment": segment_name,
        "kp": float(kp),
        "latitude": float(latitude),
        "longitude": float(longitude),
        "elevation": elevation,
    }


def delete_lrs_point_local(*, point_id: int | str) -> bool:
    row = _find_by_any("linearreferencinggeospatial", id=point_id, _pk=point_id)
    if not row:
        return False
    _delete("linearreferencinggeospatial", row)
    return True


def list_lrs_points_local(*, segment_name: str | None = None) -> list[dict]:
    provider = _provider()
    if provider is None:
        return []
    segments = {str(s.get("_pk")): s for s in provider.read_all("segment")}
    # also index by id
    for s in list(segments.values()):
        segments[str(s.get("id"))] = s
    rows = []
    for row in provider.read_all("linearreferencinggeospatial"):
        seg_pk = row.get("segment_id") or row.get("segment")
        seg = segments.get(str(seg_pk)) if seg_pk is not None else None
        name = (seg or {}).get("name")
        if segment_name and str(name or "").upper() != str(segment_name).upper():
            continue
        rows.append(
            {
                "id": int(row.get("id") or row.get("_pk")),
                "segment": name,
                "kp": row.get("kp"),
                "latitude": row.get("latitude"),
                "longitude": row.get("longitude"),
                "elevation": row.get("elevation"),
            }
        )
    rows.sort(key=lambda item: float(item.get("kp") or 0))
    return rows


def interpolate_lrs_local(*, segment_name: str, kp: float) -> tuple[dict | None, str]:
    points = list_lrs_points_local(segment_name=segment_name)
    if not points:
        return None, f"Segment {segment_name} does not exist into database"
    exact = next((p for p in points if float(p["kp"]) == float(kp)), None)
    if exact:
        data = dict(exact)
        data["interpolated"] = False
        return data, "Exact KP match"
    lowers = [p for p in points if float(p["kp"]) < float(kp)]
    uppers = [p for p in points if float(p["kp"]) > float(kp)]
    lower = max(lowers, key=lambda p: float(p["kp"])) if lowers else None
    upper = min(uppers, key=lambda p: float(p["kp"])) if uppers else None
    if lower is None or upper is None:
        return None, f"Cannot interpolate KP {kp} for segment {segment_name}"
    span = float(upper["kp"]) - float(lower["kp"])
    if span == 0:
        return None, f"Cannot interpolate KP {kp} for segment {segment_name}"
    ratio = (float(kp) - float(lower["kp"])) / span

    def _lerp(a, b):
        if a is None or b is None:
            return None
        return float(a) + (float(b) - float(a)) * ratio

    data = {
        "id": None,
        "segment": segment_name,
        "kp": float(kp),
        "latitude": _lerp(lower.get("latitude"), upper.get("latitude")),
        "longitude": _lerp(lower.get("longitude"), upper.get("longitude")),
        "elevation": _lerp(lower.get("elevation"), upper.get("elevation")),
        "interpolated": True,
    }
    return data, "Interpolated KP"
