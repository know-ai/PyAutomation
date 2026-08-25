# -*- coding: utf-8 -*-
"""Naming and lifecycle helpers for wavelet-derived ``.f`` tags."""
from __future__ import annotations

import logging

_FILTER_SUFFIX = ".f"
_FILTER_DISPLAY_SUFFIX = ".f"
_LEGACY_FILTER_DISPLAY_SUFFIX = ".filtro"
_SCOPED_DISPLAY_SEP = " · "


def filtered_tag_name(source_name: str) -> str:
    name = (source_name or "").strip()
    if not name:
        return name
    if name.endswith(_FILTER_SUFFIX):
        return name
    return f"{name}{_FILTER_SUFFIX}"


def is_filtered_derivative_name(name: str) -> bool:
    return bool(name) and str(name).endswith(_FILTER_SUFFIX)


def source_tag_name(filtered_name: str) -> str:
    name = (filtered_name or "").strip()
    if name.endswith(_FILTER_SUFFIX):
        return name[: -len(_FILTER_SUFFIX)]
    return name


def _strip_filter_display_suffix(value: str) -> str:
    base = (value or "").strip()
    if base.endswith(_LEGACY_FILTER_DISPLAY_SUFFIX):
        return base[: -len(_LEGACY_FILTER_DISPLAY_SUFFIX)]
    if base.endswith(_FILTER_DISPLAY_SUFFIX):
        return base[: -len(_FILTER_DISPLAY_SUFFIX)]
    return base


def _source_display_base(source_tag) -> str:
    """DisplayNameRaw: friendly label without Site/Area prefix."""
    base = ""
    getter = getattr(source_tag, "get_display_name", None)
    if callable(getter):
        try:
            base = str(getter() or "").strip()
        except Exception:
            base = ""
    if not base:
        base = str(getattr(source_tag, "display_name", None) or "").strip()
    if _SCOPED_DISPLAY_SEP in base:
        base = base.split(_SCOPED_DISPLAY_SEP, 1)[-1].strip()
    base = _strip_filter_display_suffix(base)
    if base and "." in base and not any(ch.isspace() for ch in base):
        parts = [part for part in base.split(".") if part]
        if parts:
            base = parts[-1]
    if not base:
        name = source_tag_name(str(getattr(source_tag, "name", "") or ""))
        base = name.split(".")[-1] if name else "tag"
    return base


def filtered_display_name(source_tag) -> str:
    """Globally unique ``Tags.display_name``: qualified ``{source.name}.f``.

    ``tags_display_name`` is unique across the plant. Using only DisplayNameRaw
    (e.g. ``FI_02.f``) collides between areas. The HMI still renders the raw
    suffix via ``resolveTagDisplayLabel``.
    """
    return filtered_tag_name(str(getattr(source_tag, "name", "") or ""))


def filtered_description(source_tag) -> str:
    source_desc = getattr(source_tag, "description", None) or getattr(source_tag, "name", "")
    return f"Wavelet filtered · {source_desc}"


def tag_filter_enabled(tag) -> bool:
    """True when wavelet filtering is active on this tag (not a ``.f`` derivative)."""
    if tag is None or is_filtered_derivative_name(getattr(tag, "name", "")):
        return False
    return bool(getattr(tag, "filter_enabled", False))


def resolve_subscription_tag(tag):
    """Return ``.f`` derivative when wavelet filter is enabled, else the source tag."""
    if tag is None or not tag_filter_enabled(tag):
        return tag
    return ensure_filtered_tag(tag) or tag


def machine_sample_interval(machine) -> float:
    """Effective cadence for wavelet publication (sample_interval or execution interval)."""
    sample = machine.get_sample_interval()
    if sample is not None:
        return max(0.05, float(sample))
    return max(0.05, float(machine.get_interval()))


def resolve_filter_config(tag) -> dict:
    return {
        "wavelet": getattr(tag, "filter_wavelet", None) or "db4",
        "level": int(getattr(tag, "filter_level", None) or 4),
        "threshold_factor": float(
            getattr(tag, "filter_threshold_factor", None) or 3.0
        ),
        "persist": bool(getattr(tag, "filter_persist", False)),
    }


def maybe_ensure_persistent_filtered_tag(source_tag) -> object | None:
    """Eager-create ``.f`` when wavelet is on and historian persistence is requested."""
    if not tag_filter_enabled(source_tag):
        return None
    if not bool(getattr(source_tag, "filter_persist", False)):
        return None
    return ensure_filtered_tag(source_tag, persist=True)


def sync_filtered_tag_metadata(source_tag, derived) -> dict:
    """Keep ``.f`` metadata aligned with the raw source tag.

    Mirrors identity and engineering attributes that the UI cannot edit on the
    filtered row: display_name, description, unit, display_unit, variable.

    Returns a dict of bools for what changed.
    """
    changed = {
        "display_name": False,
        "description": False,
        "unit": False,
        "display_unit": False,
        "variable": False,
    }
    if source_tag is None or derived is None:
        return changed
    desired_display = filtered_display_name(source_tag)
    desired_desc = filtered_description(source_tag)
    try:
        current_display = (
            derived.get_display_name()
            if hasattr(derived, "get_display_name")
            else getattr(derived, "display_name", None)
        )
        if current_display != desired_display and hasattr(derived, "set_display_name"):
            derived.set_display_name(desired_display)
            changed["display_name"] = True
        if getattr(derived, "description", None) != desired_desc:
            if hasattr(derived, "set_description"):
                derived.set_description(description=desired_desc)
            else:
                derived.description = desired_desc
            changed["description"] = True

        src_unit = getattr(source_tag, "unit", None)
        if src_unit is not None and getattr(derived, "unit", None) != src_unit:
            if hasattr(derived, "set_unit"):
                derived.set_unit(unit=src_unit)
            else:
                derived.unit = src_unit
            changed["unit"] = True

        src_display_unit = getattr(source_tag, "display_unit", None) or src_unit
        if (
            src_display_unit is not None
            and getattr(derived, "display_unit", None) != src_display_unit
        ):
            if hasattr(derived, "set_display_unit"):
                derived.set_display_unit(unit=src_display_unit)
            else:
                derived.display_unit = src_display_unit
            changed["display_unit"] = True

        src_variable = getattr(source_tag, "variable", None)
        if (
            src_variable is not None
            and getattr(derived, "variable", None) != src_variable
        ):
            if hasattr(derived, "set_variable"):
                derived.set_variable(variable=src_variable)
            else:
                derived.variable = src_variable
            changed["variable"] = True
    except Exception:
        logging.getLogger("pyautomation").debug(
            "Filtered tag metadata sync skipped for %s",
            getattr(source_tag, "name", "?"),
            exc_info=True,
        )
    return changed


def _persist_filtered_identity(app, derived, *, fields: dict) -> None:
    """Write renamed/synced .f fields to historian and/or local catalog."""
    if not fields or derived is None:
        return
    try:
        payload = {k: v for k, v in fields.items() if v is not None}
        if not payload:
            return
        if app.is_db_connected():
            app.logger_engine.update_tag(id=derived.id, **payload)
        else:
            from ..catalog.seed import persist_tag_to_local

            persist_tag_to_local(derived)
    except Exception:
        logging.getLogger("pyautomation").debug(
            "Filtered tag historian identity update skipped for %s",
            getattr(derived, "name", "?"),
            exc_info=True,
        )


def _remap_alarm_tag_index(old_name: str, new_name: str) -> None:
    """Keep AlarmManager lookups working after a ``.f`` rename."""
    if not old_name or not new_name or old_name == new_name:
        return
    try:
        from .. import PyAutomation

        mgr = PyAutomation().alarm_manager
        bucket = getattr(mgr, "_by_tag_name", {}).pop(old_name, None)
        if not bucket:
            return
        for alarm in bucket:
            tag_ref = getattr(alarm, "tag", None)
            if isinstance(tag_ref, str) and tag_ref == old_name:
                alarm.tag = new_name
        dest = mgr._by_tag_name.setdefault(new_name, [])
        for alarm in bucket:
            if alarm not in dest:
                dest.append(alarm)
    except Exception:
        logging.getLogger("pyautomation").debug(
            "Alarm tag-index remap skipped %s → %s", old_name, new_name, exc_info=True
        )


def _find_existing_filtered_tag(app, source_tag, previous_name: str | None):
    """Locate an existing ``.f`` by new name, then by previous source name."""
    new_derived_name = filtered_tag_name(getattr(source_tag, "name", "") or "")
    derived = app.cvt.get_tag_by_name(new_derived_name) if new_derived_name else None
    if derived is not None:
        return derived, new_derived_name, None

    if previous_name:
        old_derived_name = filtered_tag_name(previous_name)
        if old_derived_name and old_derived_name != new_derived_name:
            derived = app.cvt.get_tag_by_name(old_derived_name)
            if derived is not None:
                return derived, new_derived_name, old_derived_name
    return None, new_derived_name, None


def propagate_filtered_tag_identity(
    source_tag,
    *,
    previous_name: str | None = None,
) -> object | None:
    """
    Cascade source identity / engineering fields onto an already-created ``.f`` tag.

    - Renames ``old.f`` → ``new.f`` when the raw tag is renamed.
    - Always realigns ``display_name`` to the qualified ``{source.name}.f``.
    - Mirrors ``unit``, ``display_unit`` and ``variable`` from the raw tag.
    - Persists mirrored fields to the historian when connected.
    - Remaps wavelet worker + alarm indexes for the rename.

    Does **not** create a new ``.f``; use ``ensure_filtered_tag`` for that.
    """
    if source_tag is None:
        return None
    try:
        from .. import PyAutomation

        app = PyAutomation()
        derived, new_derived_name, old_derived_name = _find_existing_filtered_tag(
            app, source_tag, previous_name
        )
        if derived is None:
            return None

        persist_fields: dict = {}
        if old_derived_name and derived.name != new_derived_name:
            conflict = app.cvt.get_tag_by_name(new_derived_name)
            if conflict is not None and getattr(conflict, "id", None) != getattr(derived, "id", None):
                logging.getLogger("pyautomation").warning(
                    "Cannot rename filtered tag %s → %s: target already exists",
                    old_derived_name,
                    new_derived_name,
                )
            else:
                renamed, msg = app.cvt.update_tag(id=derived.id, name=new_derived_name)
                if renamed is None:
                    logging.getLogger("pyautomation").warning(
                        "Filtered tag rename failed %s → %s: %s",
                        old_derived_name,
                        new_derived_name,
                        msg,
                    )
                else:
                    derived = renamed
                    persist_fields["name"] = new_derived_name
                    _remap_alarm_tag_index(old_derived_name, new_derived_name)
                    try:
                        from ..workers.wavelet_worker import get_wavelet_worker

                        worker = get_wavelet_worker()
                        if worker is not None and previous_name:
                            worker.rename_source(previous_name, source_tag.name)
                    except Exception:
                        logging.getLogger("pyautomation").debug(
                            "Wavelet worker source rename skipped",
                            exc_info=True,
                        )
                    try:
                        das = getattr(app, "das", None)
                        buffer = getattr(das, "buffer", None)
                        if isinstance(buffer, dict):
                            buffer.pop(old_derived_name, None)
                    except Exception:
                        pass

        meta = sync_filtered_tag_metadata(source_tag, derived)
        if meta.get("display_name"):
            persist_fields["display_name"] = filtered_display_name(source_tag)
        if meta.get("description"):
            persist_fields["description"] = filtered_description(source_tag)
        if meta.get("unit"):
            persist_fields["unit"] = getattr(source_tag, "unit", None)
        if meta.get("display_unit"):
            persist_fields["display_unit"] = (
                getattr(source_tag, "display_unit", None)
                or getattr(source_tag, "unit", None)
            )
        if meta.get("variable"):
            persist_fields["variable"] = getattr(source_tag, "variable", None)
        _persist_filtered_identity(app, derived, fields=persist_fields)
        return derived
    except Exception:
        logging.getLogger("pyautomation").error(
            "Failed to propagate filtered tag identity for %s",
            getattr(source_tag, "name", "?"),
            exc_info=True,
        )
        return None


def ensure_filtered_tag(
    source_tag,
    *,
    persist: bool | None = None,
    previous_name: str | None = None,
) -> object | None:
    """Create or fetch the ``.f`` CVT tag mirroring metadata from the source tag."""
    if source_tag is None:
        return None
    from .. import PyAutomation

    app = PyAutomation()
    # Prefer cascade/rename when an older .f already exists under previous_name.
    existing = propagate_filtered_tag_identity(source_tag, previous_name=previous_name)
    if existing is not None:
        return existing

    derived_name = filtered_tag_name(source_tag.name)
    cfg = resolve_filter_config(source_tag)
    should_persist = cfg["persist"] if persist is None else bool(persist)
    try:
        derived, msg = app.cvt.set_tag(
            name=derived_name,
            unit=getattr(source_tag, "unit", "adim"),
            data_type="float",
            description=filtered_description(source_tag),
            variable=getattr(source_tag, "variable", "Adimentional"),
            display_name=filtered_display_name(source_tag),
            display_unit=getattr(source_tag, "display_unit", None) or getattr(source_tag, "unit", "adim"),
            scan_time=getattr(source_tag, "scan_time", None),
            dead_band=None,
            filter_enabled=False,
            filter_persist=should_persist,
            area=getattr(source_tag, "area", None),
            owner_node=getattr(source_tag, "owner_node", None),
        )
        if derived is None:
            logging.getLogger("pyautomation").warning(
                "Filtered tag not created for %s: %s", source_tag.name, msg
            )
            return None
        if should_persist and app.is_db_connected():
            try:
                app.logger_engine.set_tag(tag=derived)
                app.db_manager.attach(tag_name=derived.name)
            except Exception:
                logging.getLogger("pyautomation").debug(
                    "Filtered tag historian registration skipped for %s",
                    derived.name,
                    exc_info=True,
                )
        elif should_persist:
            try:
                from ..catalog.seed import persist_tag_to_local

                persist_tag_to_local(derived)
                app.db_manager.attach(tag_name=derived.name)
            except Exception:
                logging.getLogger("pyautomation").debug(
                    "Filtered tag local catalog registration skipped for %s",
                    derived.name,
                    exc_info=True,
                )
        return derived
    except Exception:
        logging.getLogger("pyautomation").error(
            "Failed to ensure filtered tag for %s", source_tag.name, exc_info=True
        )
        return None
