# -*- coding: utf-8 -*-
"""Hydrate in-memory CVT / users from the local catalog mirror."""
from __future__ import annotations

import logging

from .local_provider import LocalCatalogProvider

_LOGGER = logging.getLogger("pyautomation")


def _index(rows: list[dict]) -> dict[str, dict]:
    return {str(row.get("_pk")): row for row in rows}


def fill_roles_from_local() -> int:
    from ..modules.users.roles import Role
    from ..modules.users.roles import Roles as CVTRoles

    roles = CVTRoles()
    count = 0
    for row in LocalCatalogProvider().read_all("roles"):
        try:
            roles.add(
                role=Role(
                    name=row.get("name"),
                    level=int(row.get("level") or 256),
                    identifier=row.get("identifier"),
                )
            )
            count += 1
        except Exception:
            _LOGGER.debug("local role hydrate skipped", exc_info=True)
    return count


def fill_users_from_local() -> int:
    from ..modules.users.roles import Roles as CVTRoles
    from ..modules.users.users import users

    roles = CVTRoles()
    role_rows = _index(LocalCatalogProvider().read_all("roles"))
    count = 0
    for row in LocalCatalogProvider().read_all("users"):
        try:
            role_id = row.get("role_id") or row.get("role")
            role_row = role_rows.get(str(role_id)) if role_id is not None else None
            role_name = (role_row or {}).get("name") or "guest"
            if isinstance(role_name, str):
                role_name = role_name.lower() if role_name.upper() == "GUEST" else role_name
            # Roles manager matches case-insensitively via get_by_name in most paths;
            # keep catalog name as-is (often UPPER like SUDO).
            users.signup(
                username=row.get("username"),
                role_name=role_name,
                email=row.get("email"),
                password=row.get("password"),
                name=row.get("name"),
                lastname=row.get("lastname"),
                identifier=row.get("identifier"),
                encode_password=False,
            )
            count += 1
        except Exception:
            _LOGGER.debug("local user hydrate skipped", exc_info=True)
    return count


def local_opcua_clients() -> list[dict]:
    rows = []
    for row in LocalCatalogProvider().read_all("opcua"):
        rows.append(
            {
                "client_name": row.get("client_name"),
                "host": row.get("host"),
                "port": row.get("port"),
                "owner_node": row.get("owner_node"),
            }
        )
    return rows


def local_tag_payloads() -> list[dict]:
    units = _index(LocalCatalogProvider().read_all("units"))
    types = _index(LocalCatalogProvider().read_all("datatypes"))
    variables = _index(LocalCatalogProvider().read_all("variables"))
    segments = _index(LocalCatalogProvider().read_all("segment"))
    payloads = []
    for row in LocalCatalogProvider().read_all("tags"):
        if row.get("active") is False:
            continue
        unit_row = units.get(str(row.get("unit_id") or row.get("unit") or ""))
        dtype = types.get(str(row.get("data_type_id") or row.get("data_type") or ""))
        display_unit = units.get(str(row.get("display_unit_id") or row.get("display_unit") or ""))
        segment_row = segments.get(str(row.get("segment_id") or row.get("segment") or ""))
        variable_name = ""
        if unit_row:
            var = variables.get(str(unit_row.get("variable_id_id") or unit_row.get("variable_id") or ""))
            variable_name = (var or {}).get("name") or ""
        payloads.append(
            {
                "id": row.get("identifier") or row.get("_pk"),
                "name": row.get("name"),
                "unit": (unit_row or {}).get("unit") or (unit_row or {}).get("name") or "adim",
                "data_type": (dtype or {}).get("name") or "float",
                "description": row.get("description") or "",
                "display_name": row.get("display_name") or row.get("name"),
                "display_unit": (display_unit or unit_row or {}).get("unit") or "adim",
                "opcua_address": row.get("opcua_address"),
                "opcua_client_name": row.get("opcua_client_name"),
                "node_namespace": row.get("node_namespace"),
                "scan_time": row.get("scan_time"),
                "dead_band": row.get("dead_band"),
                "kp": row.get("kp"),
                "variable": variable_name or "Adimentional",
                "active": True,
                "area": row.get("area"),
                "owner_node": row.get("owner_node"),
                "segment": (segment_row or {}).get("name") or "",
                "filter_enabled": row.get("filter_enabled"),
                "filter_wavelet": row.get("filter_wavelet"),
                "filter_level": row.get("filter_level"),
                "filter_threshold_factor": row.get("filter_threshold_factor"),
                "filter_persist": row.get("filter_persist"),
                "out_of_range_detection": row.get("out_of_range_detection"),
                "outlier_detection": row.get("outlier_detection"),
                "frozen_data_detection": row.get("frozen_data_detection"),
            }
        )
    return payloads


def local_machine_payloads() -> list[dict]:
    payloads = []
    for row in LocalCatalogProvider().read_all("machines"):
        payloads.append(
            {
                "identifier": row.get("identifier"),
                "name": row.get("name"),
                "area": row.get("area"),
                "interval": row.get("interval"),
                "description": row.get("description"),
                "classification": row.get("classification"),
                "buffer_size": row.get("buffer_size"),
                "buffer_roll_type": row.get("buffer_roll_type"),
                "criticity": row.get("criticity"),
                "priority": row.get("priority"),
            }
        )
    return payloads


def local_alarm_payloads() -> list[dict]:
    tags = {str(t.get("_pk")): t for t in LocalCatalogProvider().read_all("tags")}
    types = _index(LocalCatalogProvider().read_all("alarmtypes"))
    states = _index(LocalCatalogProvider().read_all("alarmstates"))
    payloads = []
    for row in LocalCatalogProvider().read_all("alarms"):
        tag = tags.get(str(row.get("tag_id") or row.get("tag") or ""))
        trigger = types.get(str(row.get("trigger_type_id") or row.get("trigger_type") or ""))
        state = states.get(str(row.get("state_id") or row.get("state") or ""))
        state_name = (state or {}).get("name") or ""
        if str(state_name).upper() in {"OUT OF SERVICE", "OOS"}:
            continue
        payloads.append(
            {
                "identifier": row.get("identifier"),
                "name": row.get("name"),
                "tag": (tag or {}).get("name"),
                "alarm_type": (trigger or {}).get("name") or "BOOL",
                "trigger_value": row.get("trigger_value"),
                "description": row.get("description") or "",
                "state": (state or {}).get("name"),
                "area": row.get("area"),
                "on_delay": row.get("on_delay"),
                "off_delay": row.get("off_delay"),
                "on_delay_units": row.get("on_delay_units"),
                "off_delay_units": row.get("off_delay_units"),
            }
        )
    return payloads
