# -*- coding: utf-8 -*-
"""Cold-start defaults into ./db/catalog.db when the historian is unavailable.

Mirrors what BaseLogger.create_tables / AlarmsLogger create on a live remote:
variables, units, datatypes, roles, alarm types/states. Idempotent.
"""
from __future__ import annotations

import logging
import secrets

from werkzeug.security import generate_password_hash

from .local_db import get_catalog_database
from .local_provider import LocalCatalogProvider
from .versions import edge_node_id, now_ms

_LOGGER = logging.getLogger("pyautomation")


def _find_by_name(table: str, name: str, *, field: str = "name") -> dict | None:
    target = str(name or "").upper()
    for row in LocalCatalogProvider().read_all(table):
        if str(row.get(field) or "").upper() == target:
            return row
    return None


def _find_unit_by_symbol(unit: str) -> dict | None:
    symbol = str(unit or "")
    for row in LocalCatalogProvider().read_all("units"):
        if row.get("unit") == symbol or str(row.get("name") or "") == symbol:
            return row
    return None


def _upsert(table: str, row: dict) -> str | None:
    try:
        return LocalCatalogProvider().upsert(
            table,
            row,
            node_id=edge_node_id(),
            version=now_ms(),
        )
    except Exception:
        _LOGGER.debug("catalog seed upsert failed table=%s", table, exc_info=True)
        return None


def _table_row_count(table: str) -> int:
    try:
        return len(LocalCatalogProvider().read_all(table))
    except Exception:
        return 0


def seed_datatypes() -> int:
    """Insert default datatypes only when the table is empty (never mutate operator rows)."""
    from ..variables import DATATYPES

    if _table_row_count("datatypes") > 0:
        return 0
    n = 0
    for datatype in DATATYPES:
        name = datatype.get("value") if isinstance(datatype, dict) else datatype
        if not name:
            continue
        if _upsert("datatypes", {"name": name}):
            n += 1
    return n


def seed_variables_and_units() -> int:
    """Cold-start variables/units only when units table is empty.

    If any unit row already exists, skip entirely — never upsert catalogue defaults
    over operator-authored symbols (avoids variable_id / unique collisions).
    """
    from ..variables import VARIABLES

    if _table_row_count("units") > 0:
        return 0
    n = 0
    for variable, units in VARIABLES.items():
        var_row = _find_by_name("variables", variable)
        if var_row is None:
            pk = _upsert("variables", {"name": variable})
            var_row = _find_by_name("variables", variable) if pk else None
            if var_row:
                n += 1
        if var_row is None:
            continue
        var_pk = var_row.get("_pk") or var_row.get("id")
        for name, unit in units.items():
            if _find_by_name("units", name) or _find_unit_by_symbol(unit):
                continue
            if _upsert(
                "units",
                {"name": name, "unit": unit, "variable_id": var_pk},
            ):
                n += 1
    return n


def seed_roles() -> int:
    """Insert default roles only when the table is empty."""
    from ..dbmodels.users import Roles

    if _table_row_count("roles") > 0:
        return 0
    n = 0
    for role in Roles.__defaults__:
        name = role["name"]
        if _upsert(
            "roles",
            {
                "name": str(name).upper(),
                "level": int(role["level"]),
                "identifier": role.get("identifier") or secrets.token_hex(4),
            },
        ):
            n += 1
    return n


def ensure_unit_symbol(unit: str, *, variable: str | None = None) -> dict | None:
    """Return a local units row for ``unit``, creating it only if missing.

    Never rewrites an existing symbol's variable_id.
    """
    symbol = str(unit or "").strip()
    if not symbol:
        return None
    existing = _find_unit_by_symbol(symbol)
    if existing is not None:
        return existing
    # Only create when missing; seed parents if cold.
    if _table_row_count("units") == 0:
        seed_variables_and_units()
        existing = _find_unit_by_symbol(symbol)
        if existing is not None:
            return existing
    var_name = variable or "Adimentional"
    var_row = _find_by_name("variables", var_name)
    if var_row is None:
        _upsert("variables", {"name": var_name})
        var_row = _find_by_name("variables", var_name)
    if var_row is None:
        return None
    var_pk = var_row.get("_pk") or var_row.get("id")
    _upsert(
        "units",
        {"name": symbol, "unit": symbol, "variable_id": var_pk},
    )
    return _find_unit_by_symbol(symbol)


def seed_alarm_types_and_states() -> int:
    from ..alarms.states import AlarmState
    from ..alarms.trigger import TriggerType

    n = 0
    for alarm_type in TriggerType:
        name = alarm_type.value
        if _find_by_name("alarmtypes", name):
            continue
        if _upsert("alarmtypes", {"name": str(name).upper()}):
            n += 1
    for alarm_state in AlarmState._states:
        name = alarm_state.state
        if _find_by_name("alarmstates", name):
            continue
        if _upsert(
            "alarmstates",
            {
                "name": name,
                "mnemonic": alarm_state.mnemonic,
                "condition": alarm_state.process_condition,
                "status": alarm_state.alarm_status,
            },
        ):
            n += 1
    return n


def seed_system_user(password: str) -> bool:
    """Ensure sudo role + system user exist in the local mirror."""
    if _find_by_name("users", "system", field="username"):
        return False
    role = _find_by_name("roles", "sudo")
    if role is None:
        seed_roles()
        role = _find_by_name("roles", "sudo")
    if role is None:
        return False
    hashed = generate_password_hash(password)
    pk = _upsert(
        "users",
        {
            "username": "system",
            "email": "system@intelcon.com",
            "password": hashed,
            "identifier": secrets.token_hex(4),
            "name": "System",
            "lastname": "Intelcon",
            "role_id": role.get("_pk") or role.get("id"),
        },
    )
    return bool(pk)


def seed_local_catalog_defaults(*, system_password: str | None = None) -> dict:
    """Idempotent cold-start seed. Returns counts of newly inserted rows."""
    if get_catalog_database() is None:
        return {"skipped": True}
    counts = {
        "datatypes": seed_datatypes(),
        "variables_units": seed_variables_and_units(),
        "roles": seed_roles(),
        "alarm_meta": seed_alarm_types_and_states(),
        "system_user": 0,
    }
    if system_password is not None:
        counts["system_user"] = 1 if seed_system_user(system_password) else 0
    total = sum(v for k, v in counts.items() if k != "skipped" and isinstance(v, int))
    if total:
        _LOGGER.info("Local catalog cold-start seeded: %s", counts)
    return counts


def persist_tag_to_local(tag) -> str | None:
    """Write a CVT tag into the local catalog (FK-resolved). Never raises."""
    try:
        if get_catalog_database() is None or tag is None:
            return None
        unit_row = _find_unit_by_symbol(getattr(tag, "unit", None) or "adim")
        display_unit_row = _find_unit_by_symbol(
            getattr(tag, "display_unit", None) or getattr(tag, "unit", None) or "adim"
        )
        dtype = _find_by_name("datatypes", getattr(tag, "data_type", None) or "float")
        if unit_row is None or display_unit_row is None:
            unit_row = unit_row or ensure_unit_symbol(
                getattr(tag, "unit", None) or "adim",
                variable=getattr(tag, "variable", None),
            )
            display_unit_row = display_unit_row or ensure_unit_symbol(
                getattr(tag, "display_unit", None) or getattr(tag, "unit", None) or "adim",
                variable=getattr(tag, "variable", None),
            )
        if dtype is None:
            if _table_row_count("datatypes") == 0:
                seed_datatypes()
            dtype = _find_by_name("datatypes", getattr(tag, "data_type", None) or "float")
        if unit_row is None or display_unit_row is None or dtype is None:
            _LOGGER.warning(
                "persist_tag_to_local skipped name=%s: missing unit/datatype in catalog",
                getattr(tag, "name", None),
            )
            return None
        existing = _find_by_name("tags", getattr(tag, "name", ""), field="name")
        opcua_address = getattr(tag, "opcua_address", None)
        opcua_client_name = (
            tag.get_opcua_client_name()
            if hasattr(tag, "get_opcua_client_name")
            else getattr(tag, "opcua_client_name", None)
        )
        node_namespace = getattr(tag, "node_namespace", None)
        scan_time = getattr(tag, "scan_time", None)
        # Preserve OPC mapping already in the mirror when callers re-seed tags
        # without opcua_* (e.g. machine bootstrap after local hydrate).
        if existing:
            if not opcua_address and existing.get("opcua_address"):
                opcua_address = existing.get("opcua_address")
            if not opcua_client_name and existing.get("opcua_client_name"):
                opcua_client_name = existing.get("opcua_client_name")
            if not node_namespace and existing.get("node_namespace"):
                node_namespace = existing.get("node_namespace")
            if (scan_time is None or scan_time == 0) and existing.get("scan_time"):
                scan_time = existing.get("scan_time")
            # Keep CVT aligned when catalog still holds the OPC mapping.
            if opcua_address and not getattr(tag, "opcua_address", None):
                try:
                    tag.set_opcua_address(opcua_address)
                except Exception:
                    tag.opcua_address = opcua_address
            if opcua_client_name and not (
                tag.get_opcua_client_name()
                if hasattr(tag, "get_opcua_client_name")
                else getattr(tag, "opcua_client_name", None)
            ):
                if hasattr(tag, "set_opcua_client_name"):
                    tag.set_opcua_client_name(opcua_client_name, opcua_address=opcua_address)
                else:
                    tag.opcua_client_name = opcua_client_name
            if node_namespace and not getattr(tag, "node_namespace", None):
                if hasattr(tag, "set_node_namespace"):
                    tag.set_node_namespace(node_namespace)
                else:
                    tag.node_namespace = node_namespace
            if scan_time and not getattr(tag, "scan_time", None):
                if hasattr(tag, "set_scan_time"):
                    tag.set_scan_time(scan_time)
                else:
                    tag.scan_time = scan_time
        payload = {
            "identifier": getattr(tag, "id", None) or getattr(tag, "identifier", None),
            "name": getattr(tag, "name", None),
            "area": getattr(tag, "area", None),
            "owner_node": getattr(tag, "owner_node", None),
            "unit_id": unit_row.get("_pk") or unit_row.get("id"),
            "data_type_id": dtype.get("_pk") or dtype.get("id"),
            "display_unit_id": display_unit_row.get("_pk") or display_unit_row.get("id"),
            "description": getattr(tag, "description", None) or "",
            "display_name": getattr(tag, "display_name", None) or getattr(tag, "name", None),
            "opcua_address": opcua_address,
            "opcua_client_name": opcua_client_name,
            "node_namespace": node_namespace,
            "scan_time": scan_time,
            "dead_band": getattr(tag, "dead_band", None),
            "kp": getattr(tag, "kp", None),
            "active": True,
            "filter_enabled": getattr(tag, "filter_enabled", False),
            "filter_wavelet": getattr(tag, "filter_wavelet", "db4"),
            "filter_level": getattr(tag, "filter_level", 4),
            "filter_threshold_factor": getattr(tag, "filter_threshold_factor", 3.0),
            "filter_persist": getattr(tag, "filter_persist", False),
            "out_of_range_detection": getattr(tag, "out_of_range_detection", False),
            "outlier_detection": getattr(tag, "outlier_detection", False),
            "frozen_data_detection": getattr(tag, "frozen_data_detection", False),
        }
        # Never blank out a catalog OPC mapping with empty CVT fields.
        if existing:
            if not payload.get("opcua_address") and existing.get("opcua_address"):
                payload["opcua_address"] = existing.get("opcua_address")
            if not payload.get("opcua_client_name") and existing.get("opcua_client_name"):
                payload["opcua_client_name"] = existing.get("opcua_client_name")
            if not payload.get("node_namespace") and existing.get("node_namespace"):
                payload["node_namespace"] = existing.get("node_namespace")
            if not payload.get("scan_time") and existing.get("scan_time"):
                payload["scan_time"] = existing.get("scan_time")
        manufacturer = getattr(tag, "manufacturer", None) or ""
        segment = getattr(tag, "segment", None) or ""
        if manufacturer or segment:
            from .mutations import ensure_named_row, ensure_segment_local

            if manufacturer:
                ensure_named_row("manufacturer", manufacturer)
            if segment:
                seg = ensure_segment_local(segment, manufacturer=manufacturer or None)
                if seg:
                    payload["segment"] = seg.get("_pk") or seg.get("id")
                    payload["segment_id"] = seg.get("_pk") or seg.get("id")
        # apply_raw expects field names for FKs (unit, data_type, display_unit)
        payload["unit"] = payload.pop("unit_id")
        payload["data_type"] = payload.pop("data_type_id")
        payload["display_unit"] = payload.pop("display_unit_id")
        if existing and existing.get("_pk") is not None:
            payload["_pk"] = existing.get("_pk")
            payload["id"] = existing.get("id") or existing.get("_pk")
        return _upsert("tags", payload)
    except Exception:
        _LOGGER.debug("persist_tag_to_local failed", exc_info=True)
        return None


def persist_opcua_client_to_local(
    *,
    client_name: str,
    host: str,
    port: int,
    owner_node: str | None = None,
) -> str | None:
    """Upsert an OPC UA client into the local catalog mirror. Never raises."""
    try:
        if get_catalog_database() is None or not client_name:
            return None
        existing = None
        for row in LocalCatalogProvider().read_all("opcua"):
            if str(row.get("client_name") or "") == str(client_name):
                existing = row
                break
        payload = {
            "client_name": client_name,
            "host": host,
            "port": int(port),
            "owner_node": owner_node,
        }
        if existing and existing.get("_pk") is not None:
            payload["_pk"] = existing.get("_pk")
            payload["id"] = existing.get("id") or existing.get("_pk")
        return _upsert("opcua", payload)
    except Exception:
        _LOGGER.debug("persist_opcua_client_to_local failed", exc_info=True)
        return None


def delete_opcua_client_from_local(client_name: str) -> None:
    """Remove an OPC UA client from the local catalog. Never raises."""
    try:
        if get_catalog_database() is None or not client_name:
            return
        provider = LocalCatalogProvider()
        for row in provider.read_all("opcua"):
            if str(row.get("client_name") or "") == str(client_name):
                pk = row.get("_pk") or row.get("id")
                if pk is not None:
                    provider.delete("opcua", str(pk))
                break
    except Exception:
        _LOGGER.debug("delete_opcua_client_from_local failed", exc_info=True)


def persist_machine_to_local(
    *,
    identifier: str,
    name: str,
    interval,
    description: str = "",
    classification: str = "",
    buffer_size: int = 10,
    buffer_roll_type: str = "backward",
    criticity: int = 2,
    priority: int = 1,
    on_delay=None,
    threshold=None,
    area: str | None = None,
) -> str | None:
    """Write a state-machine definition into the local catalog. Never raises."""
    try:
        if get_catalog_database() is None:
            return None
        if hasattr(threshold, "value"):
            threshold = threshold.value
        if hasattr(on_delay, "value"):
            on_delay = on_delay.value
        if hasattr(interval, "value"):
            interval = interval.value
        existing = _find_by_name("machines", name, field="name")
        payload = {
            "identifier": identifier,
            "name": name,
            "interval": interval,
            "execution_interval": interval,
            "description": description or "",
            "classification": classification or "",
            "buffer_size": buffer_size,
            "buffer_roll_type": buffer_roll_type,
            "criticity": criticity,
            "priority": priority,
            "on_delay": on_delay,
            "threshold": threshold,
            "area": area,
        }
        if existing and existing.get("_pk") is not None:
            payload["_pk"] = existing.get("_pk")
            payload["id"] = existing.get("id") or existing.get("_pk")
        return _upsert("machines", payload)
    except Exception:
        _LOGGER.debug("persist_machine_to_local failed", exc_info=True)
        return None


def persist_alarm_to_local(
    *,
    identifier: str,
    name: str,
    tag_name: str,
    trigger_type: str,
    trigger_value,
    description: str = "",
    state: str = "Normal",
    area: str | None = None,
    on_delay=None,
    off_delay=None,
    on_delay_units: str | None = None,
    off_delay_units: str | None = None,
) -> str | None:
    """Write an alarm definition into the local catalog. Never raises."""
    try:
        if get_catalog_database() is None:
            return None
        tag_row = _find_by_name("tags", tag_name, field="name")
        type_row = _find_by_name("alarmtypes", trigger_type)
        state_row = _find_by_name("alarmstates", state)
        if type_row is None or state_row is None:
            seed_alarm_types_and_states()
            type_row = _find_by_name("alarmtypes", trigger_type)
            state_row = _find_by_name("alarmstates", state)
        if tag_row is None or type_row is None or state_row is None:
            _LOGGER.warning(
                "persist_alarm_to_local skipped name=%s: tag=%s type=%s state=%s",
                name,
                None if tag_row is None else tag_name,
                None if type_row is None else trigger_type,
                None if state_row is None else state,
            )
            return None
        existing = _find_by_name("alarms", name, field="name")
        payload = {
            "identifier": identifier,
            "name": name,
            "tag": tag_row.get("_pk") or tag_row.get("id"),
            "trigger_type": type_row.get("_pk") or type_row.get("id"),
            "trigger_value": trigger_value,
            "description": description or "",
            "state": state_row.get("_pk") or state_row.get("id"),
            "area": area,
            "on_delay": on_delay,
            "off_delay": off_delay,
            "on_delay_units": on_delay_units,
            "off_delay_units": off_delay_units,
        }
        payload = {k: v for k, v in payload.items() if v is not None or k in {"description", "area"}}
        if existing and existing.get("_pk") is not None:
            payload["_pk"] = existing.get("_pk")
            payload["id"] = existing.get("id") or existing.get("_pk")
        return _upsert("alarms", payload)
    except Exception:
        _LOGGER.debug("persist_alarm_to_local failed", exc_info=True)
        return None
