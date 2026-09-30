# -*- coding: utf-8 -*-
"""Two-phase import of a linear-referencing profile.

Every row is validated before the first write. A missing segment or a bad
value rejects the whole batch.
"""
from __future__ import annotations

import math
from typing import Any


def apply_linear_referencing_import(
    rows: list,
    *,
    default_segment_name: str | None,
    update_existing: bool,
    db_connected: bool,
) -> dict:
    prepared, errors = _prepare_rows(rows, default_segment_name)
    result = {
        "created": 0,
        "updated": 0,
        "skipped": 0,
        "errors": errors,
        "processed": len(rows) if isinstance(rows, list) else 0,
        "success": False,
    }
    if errors:
        return result

    if db_connected:
        missing = _missing_historian_segments(prepared)
    else:
        missing = _missing_local_segments(prepared)
    if missing:
        result["errors"] = missing
        return result

    if db_connected:
        _apply_historian(prepared, update_existing=update_existing, result=result)
    else:
        _apply_local(prepared, update_existing=update_existing, result=result)
    result["success"] = len(result["errors"]) == 0
    return result


def _prepare_rows(rows: list, default_segment_name: str | None) -> tuple[list[dict], list[str]]:
    if not isinstance(rows, list):
        return [], ["Import payload must be a list of rows"]
    prepared: list[dict] = []
    errors: list[str] = []
    seen: set[tuple[str, float]] = set()
    for idx, row in enumerate(rows, start=1):
        item, error = _prepare_row(row, idx, default_segment_name)
        if error:
            errors.append(error)
            continue
        key = (item["segment_name"], item["kp"])
        if key in seen:
            errors.append(
                f"Row {idx}: duplicated kp {item['kp']} for segment {item['segment_name']}"
            )
            continue
        seen.add(key)
        prepared.append(item)
    return prepared, errors


def _prepare_row(row: Any, idx: int, default_segment_name: str | None) -> tuple[dict | None, str | None]:
    if not isinstance(row, dict):
        return None, f"Row {idx}: invalid row"
    segment_name = row.get("segment_name") or default_segment_name
    if isinstance(segment_name, str):
        segment_name = segment_name.strip()
    if not segment_name:
        return None, f"Row {idx}: missing segment_name"
    if row.get("kp") is None or row.get("latitude") is None or row.get("longitude") is None:
        return None, f"Row {idx}: missing kp/latitude/longitude"
    try:
        kp = float(row.get("kp"))
        latitude = float(row.get("latitude"))
        longitude = float(row.get("longitude"))
        elevation = row.get("elevation")
        if elevation in ("", None):
            elevation = None
        else:
            elevation = float(elevation)
    except (TypeError, ValueError) as err:
        return None, f"Row {idx}: {err}"
    numbers = [kp, latitude, longitude]
    if elevation is not None:
        numbers.append(elevation)
    if not all(math.isfinite(value) for value in numbers):
        return None, f"Row {idx}: kp/latitude/longitude must be finite numbers"
    return {
        "row": idx,
        "segment_name": segment_name,
        "kp": kp,
        "latitude": latitude,
        "longitude": longitude,
        "elevation": elevation,
    }, None


def _missing_historian_segments(prepared: list[dict]) -> list[str]:
    from ...dbmodels import Segment

    cache: dict[str, Any] = {}
    errors: list[str] = []
    for item in prepared:
        name = item["segment_name"]
        if name not in cache:
            cache[name] = Segment.read_by_name(name=name)
        if cache[name] is None:
            errors.append(f"Row {item['row']}: segment {name} does not exist")
        else:
            item["segment"] = cache[name]
    return errors


def _missing_local_segments(prepared: list[dict]) -> list[str]:
    from ...catalog.local_provider import LocalCatalogProvider

    names = set()
    try:
        for row in LocalCatalogProvider().read_all("segment"):
            name = row.get("name")
            if name:
                names.add(str(name))
    except Exception:
        names = set()
    return [
        f"Row {item['row']}: segment {item['segment_name']} does not exist"
        for item in prepared
        if item["segment_name"] not in names
    ]


def _apply_historian(prepared: list[dict], *, update_existing: bool, result: dict) -> None:
    from ...dbmodels import LinearReferencingGeospatial

    db = LinearReferencingGeospatial._meta.database

    def _write() -> None:
        for item in prepared:
            current = LinearReferencingGeospatial.get_or_none(
                (LinearReferencingGeospatial.segment == item["segment"])
                & (LinearReferencingGeospatial.kp == item["kp"])
            )
            if current is None:
                point, message = LinearReferencingGeospatial.create(
                    segment_name=item["segment_name"],
                    kp=item["kp"],
                    latitude=item["latitude"],
                    longitude=item["longitude"],
                    elevation=item["elevation"],
                )
                if point is None:
                    raise RuntimeError(f"Row {item['row']}: {message}")
                result["created"] += 1
                continue
            if not update_existing:
                result["skipped"] += 1
                continue
            LinearReferencingGeospatial.put(
                id=current.id,
                latitude=item["latitude"],
                longitude=item["longitude"],
                elevation=item["elevation"],
            )
            result["updated"] += 1

    try:
        with db.atomic():
            _write()
    except Exception as err:
        result["created"] = 0
        result["updated"] = 0
        result["skipped"] = 0
        result["errors"].append(str(err))


def _apply_local(prepared: list[dict], *, update_existing: bool, result: dict) -> None:
    from ...catalog.local_provider import LocalCatalogProvider
    from ...catalog.mutations import list_lrs_points_local, persist_lrs_point_local

    existing = {}
    for point in list_lrs_points_local():
        name = point.get("segment") or point.get("segment_name")
        try:
            kp = float(point.get("kp"))
        except (TypeError, ValueError):
            continue
        if name is not None:
            existing[(str(name), kp)] = point

    def _write() -> None:
        for item in prepared:
            current = existing.get((item["segment_name"], item["kp"]))
            if current is not None and not update_existing:
                result["skipped"] += 1
                continue
            point = persist_lrs_point_local(
                segment_name=item["segment_name"],
                kp=item["kp"],
                latitude=item["latitude"],
                longitude=item["longitude"],
                elevation=item["elevation"],
                point_id=None if current is None else current.get("id"),
            )
            if point is None:
                raise RuntimeError(f"Row {item['row']}: local persist failed")
            if current is None:
                result["created"] += 1
            else:
                result["updated"] += 1

    try:
        with LocalCatalogProvider().atomic():
            _write()
    except Exception as err:
        result["created"] = 0
        result["updated"] = 0
        result["skipped"] = 0
        result["errors"].append(str(err))
