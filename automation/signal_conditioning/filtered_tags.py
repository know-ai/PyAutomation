# -*- coding: utf-8 -*-
"""Naming and lifecycle helpers for wavelet-derived ``.f`` tags."""
from __future__ import annotations

import logging

_FILTER_SUFFIX = ".f"


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


def ensure_filtered_tag(source_tag, *, persist: bool | None = None) -> object | None:
    """Create or fetch the ``.f`` CVT tag mirroring metadata from the source tag."""
    if source_tag is None:
        return None
    from .. import PyAutomation

    app = PyAutomation()
    derived_name = filtered_tag_name(source_tag.name)
    existing = app.cvt.get_tag_by_name(derived_name)
    if existing is not None:
        return existing

    cfg = resolve_filter_config(source_tag)
    should_persist = cfg["persist"] if persist is None else bool(persist)
    try:
        derived, msg = app.cvt.set_tag(
            name=derived_name,
            unit=getattr(source_tag, "unit", "adim"),
            data_type="float",
            description=f"Wavelet filtered · {getattr(source_tag, 'description', source_tag.name)}",
            variable=getattr(source_tag, "variable", "Adimentional"),
            display_name=f"{getattr(source_tag, 'display_name', source_tag.name.split('.')[-1])} (filt)",
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
        return derived
    except Exception:
        logging.getLogger("pyautomation").error(
            "Failed to ensure filtered tag for %s", source_tag.name, exc_info=True
        )
        return None
