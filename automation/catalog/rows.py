# -*- coding: utf-8 -*-
"""Row dict helpers for catalog clones / historian models."""
from __future__ import annotations

from datetime import datetime
from peewee import Field, ForeignKeyField, Model

from .schema import pk_as_str

# When pushing catalog rows, prefer these unique columns to locate an existing
# historian row before INSERT (avoids unique collisions after offline PK drift).
_UNIQUE_LOOKUP_ORDER: dict[str, tuple[str, ...]] = {
    "opcuaserver": ("namespace", "name"),
    "machines": ("identifier",),
    "tags": ("identifier", "name"),
    "alarms": ("identifier", "name"),
    "users": ("username", "identifier"),
    "opcua": ("client_name",),
    "roles": ("name",),
    "datatypes": ("name",),
    "alarmtypes": ("name",),
    "alarmstates": ("name",),
    "accesstype": ("name",),
    "manufacturer": ("name",),
    "variables": ("name",),
    "units": ("unit", "name"),
    "segment": ("name",),
    "nodes": ("id",),
}


def row_to_raw(row: Model) -> dict:
    data: dict = {}
    for name, field in row._meta.fields.items():
        value = getattr(row, name, None)
        column = getattr(field, "column_name", name)
        if isinstance(field, ForeignKeyField):
            if value is None:
                raw_value = None
            elif isinstance(value, Model):
                raw_value = value._pk
            else:
                raw_value = value
            data[column] = raw_value
            # Also expose the Peewee field name for callers that use ``role`` / ``unit``.
            if column != name:
                data[name] = raw_value
            continue
        if isinstance(value, datetime):
            coerced = value.isoformat()
        else:
            coerced = value
        data[name] = coerced
        # Local clones map historian FKs to Integer/Char fields that keep
        # ``column_name`` (e.g. field ``role`` → column ``role_id``). Emit both
        # keys so upserts that set ``role_id`` stay consistent with reads.
        if column and column != name:
            data[column] = coerced
    data["_pk"] = pk_as_str(row)
    return data


def _coerce(field: Field, value):
    if value is None:
        return None
    # Local row_to_raw serializes datetimes to ISO strings; peewee TimestampField
    # cannot round() a str on save, so parse back before upsert.
    try:
        from peewee import DateTimeField, TimestampField

        if isinstance(field, (DateTimeField, TimestampField)) and isinstance(value, str):
            text = value.strip()
            if text.endswith("Z"):
                text = text[:-1] + "+00:00"
            try:
                return datetime.fromisoformat(text)
            except ValueError:
                pass
    except Exception:
        pass
    python_type = getattr(field, "python_value", None)
    try:
        if python_type:
            return field.python_value(value)
    except Exception:
        pass
    return value


def _pick_raw_value(raw: dict, name: str, column: str):
    """Prefer SQL column key when both field name and column are present.

    Offline updates often copy ``row_to_raw`` (``role``=old) and then set
    ``role_id``=new; without this preference the stale field name wins.
    """
    if column and column != name and column in raw:
        return raw.get(column)
    if name in raw:
        return raw.get(name)
    if column in raw:
        return raw.get(column)
    return None


def apply_raw(model_cls: type[Model], raw: dict) -> dict:
    payload = {}
    for name, field in model_cls._meta.fields.items():
        column = getattr(field, "column_name", name)
        if isinstance(field, ForeignKeyField):
            if column in raw or name in raw:
                payload[name] = _pick_raw_value(raw, name, column)
            continue
        if name in raw or (column and column != name and column in raw):
            payload[name] = _coerce(field, _pick_raw_value(raw, name, column))
    return payload


_TAG_UNIT_FK_FIELDS = ("unit", "display_unit", "data_type", "segment")


def _is_blank_fk(value) -> bool:
    if value is None:
        return True
    if isinstance(value, str) and not value.strip():
        return True
    if isinstance(value, (int, float)) and int(value) == 0:
        return True
    return False


def _resolve_tag_unit_fks(raw: dict) -> dict:
    """Map human unit symbols onto integer FKs; never blank an existing unit_id."""
    out = dict(raw)
    try:
        from .seed import ensure_unit_symbol, _find_unit_by_symbol
    except Exception:
        return out

    for field in ("unit", "display_unit"):
        value = out.get(field)
        alt = out.get(f"{field}_id")
        chosen = value if not _is_blank_fk(value) else alt
        if _is_blank_fk(chosen):
            out.pop(field, None)
            out.pop(f"{field}_id", None)
            continue
        if isinstance(chosen, int) or (isinstance(chosen, str) and str(chosen).isdigit()):
            out[field] = int(chosen)
            out[f"{field}_id"] = int(chosen)
            continue
        if isinstance(chosen, str):
            row = _find_unit_by_symbol(chosen) or ensure_unit_symbol(chosen)
            if row is None:
                out.pop(field, None)
                out.pop(f"{field}_id", None)
                continue
            pk = row.get("_pk") or row.get("id")
            out[field] = pk
            out[f"{field}_id"] = pk
    return out


def _normalize_payload(model_cls: type[Model], payload: dict) -> None:
    """In-place tweaks so historian NOT NULL / alias columns stay consistent."""
    table = str(getattr(model_cls._meta, "table_name", "") or "")
    if table == "machines":
        if payload.get("interval") is None and payload.get("execution_interval") is not None:
            payload["interval"] = payload["execution_interval"]
        if payload.get("execution_interval") is None and payload.get("interval") is not None:
            payload["execution_interval"] = payload["interval"]


def _get_by_pk(model_cls: type[Model], pk_name: str, pk_value) -> Model | None:
    if pk_value is None or pk_value == "":
        return None
    existing = model_cls.get_or_none(getattr(model_cls, pk_name) == pk_value)
    if existing is not None:
        return existing
    try:
        return model_cls.get_or_none(getattr(model_cls, pk_name) == int(pk_value))
    except (TypeError, ValueError):
        return None


def _find_by_unique_lookup(model_cls: type[Model], payload: dict) -> Model | None:
    table = str(getattr(model_cls._meta, "table_name", "") or "")
    ordered = list(_UNIQUE_LOOKUP_ORDER.get(table, ()))
    # Append any other unique fields not already listed.
    for name, field in model_cls._meta.fields.items():
        if name in ordered:
            continue
        if getattr(field, "unique", False):
            ordered.append(name)
    for name in ordered:
        if name not in model_cls._meta.fields:
            continue
        value = payload.get(name)
        if value is None or value == "":
            continue
        found = model_cls.get_or_none(getattr(model_cls, name) == value)
        if found is not None:
            return found
    if table == "machines" and hasattr(model_cls, "name") and hasattr(model_cls, "area"):
        name = payload.get("name")
        if name:
            area = payload.get("area")
            query = model_cls.select().where(model_cls.name == name)
            if area is None or str(area).strip() == "":
                query = query.where((model_cls.area.is_null()) | (model_cls.area == ""))
            else:
                query = query.where(model_cls.area == area)
            found = query.get_or_none()
            if found is not None:
                return found
    # tagsmachines: composite natural key without a single unique column
    if table == "tagsmachines":
        tag = payload.get("tag")
        machine = payload.get("machine")
        if tag is not None and machine is not None:
            return model_cls.get_or_none(
                (model_cls.tag == tag) & (model_cls.machine == machine)
            )
    if table == "authz_grants":
        stype = payload.get("subject_type")
        sid = payload.get("subject_id")
        resource_key = payload.get("resource_key")
        action = payload.get("action")
        if stype is not None and sid is not None and resource_key is not None and action is not None:
            return model_cls.get_or_none(
                (model_cls.subject_type == stype)
                & (model_cls.subject_id == sid)
                & (model_cls.resource_key == resource_key)
                & (model_cls.action == action)
            )
    return None


def _unique_owner(model_cls: type[Model], field_name: str, value, self_pk) -> Model | None:
    field = model_cls._meta.fields.get(field_name)
    if field is None or not getattr(field, "unique", False) or value is None or value == "":
        return None
    other = model_cls.get_or_none(getattr(model_cls, field_name) == value)
    if other is None:
        return None
    try:
        if pk_as_str(other) == str(self_pk):
            return None
    except Exception:
        if getattr(other, "_pk", None) == self_pk:
            return None
    return other


def _update_instance(inst: Model, payload: dict, pk_name: str) -> Model:
    """Apply payload fields without violating unique constraints on peer rows.

    Case-sensitive unit symbols (``mm`` vs ``Mm``) must not be collapsed onto one
    row: if ``name``/``unit`` already belongs to another PK, leave that column alone.
    Never clear existing tag FK columns with NULL/0/empty. Never reassign an
    existing unit row's variable_id via seed/sync collisions.
    """
    model_cls = type(inst)
    table = str(getattr(model_cls._meta, "table_name", "") or "")
    self_pk = getattr(inst, "_pk", None)
    dirty = False
    for key, value in payload.items():
        if key == pk_name:
            continue
        if _unique_owner(model_cls, key, value, self_pk) is not None:
            continue
        if table == "tags" and key in _TAG_UNIT_FK_FIELDS and _is_blank_fk(value):
            continue
        if table == "units" and key in ("variable", "variable_id"):
            current_var = getattr(inst, "variable", None)
            if current_var is not None and value is not None and current_var != value:
                continue
            if _is_blank_fk(value):
                continue
        current = getattr(inst, key, None)
        if current != value:
            setattr(inst, key, value)
            dirty = True
    if dirty:
        inst.save()
    return inst


def upsert_model(model_cls: type[Model], raw: dict) -> Model:
    """Insert or update a historian/local Peewee row from a catalog dict.

    Intentionally bypasses custom ``Model.create()`` classmethods on dbmodels
    (those expect human-facing string names / return dict|None). Catalog sync
    must use ORM field payloads (FK ids) and always return a Model instance.
    """
    from peewee import IntegrityError

    table = str(getattr(model_cls._meta, "table_name", "") or "")
    prepared = _resolve_tag_unit_fks(raw) if table == "tags" else dict(raw)
    payload = apply_raw(model_cls, prepared)
    _normalize_payload(model_cls, payload)
    pk_field = model_cls._meta.primary_key
    pk_name = pk_field.name
    pk_value = payload.get(pk_name, prepared.get("_pk") or prepared.get("id") or prepared.get("sid"))

    existing = _get_by_pk(model_cls, pk_name, pk_value)
    if existing is None:
        existing = _find_by_unique_lookup(model_cls, payload)
    if existing is not None:
        return _update_instance(existing, payload, pk_name)

    if pk_value is not None:
        payload.setdefault(pk_name, pk_value)
    # Never call model_cls.create — many dbmodels override it.
    try:
        inst = model_cls(**payload)
        inst.save(force_insert=True)
        return inst
    except IntegrityError:
        # Race / case-fold collision: locate peer by unique columns and update safely.
        existing = _find_by_unique_lookup(model_cls, payload)
        if existing is None:
            raise
        return _update_instance(existing, payload, pk_name)
