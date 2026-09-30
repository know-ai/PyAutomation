# -*- coding: utf-8 -*-
"""Strict CSV contract for a linear-referencing geospatial profile.

The only accepted file is UTF-8 CSV with this header, in this order:

    segment_name,kp,latitude,longitude
"""
from __future__ import annotations

import csv
import math
from io import StringIO

REQUIRED_HEADER = ("segment_name", "kp", "latitude", "longitude")
MAX_CSV_BYTES = 1_048_576


class GeospatialCsvError(ValueError):
    """The file does not match the geospatial profile contract."""


class GeospatialCsvProfile:
    """Parses one profile. A single invalid row rejects the whole file."""

    def parse(self, raw: bytes) -> list[dict]:
        if raw is None:
            raise GeospatialCsvError("File is empty")
        if len(raw) > MAX_CSV_BYTES:
            raise GeospatialCsvError("File exceeds 1 MB")
        if not raw.strip():
            raise GeospatialCsvError("File is empty")
        try:
            text = raw.decode("utf-8-sig")
        except UnicodeDecodeError as err:
            raise GeospatialCsvError("File must be UTF-8 CSV") from err
        return self.parse_text(text)

    def parse_text(self, text: str) -> list[dict]:
        reader = csv.reader(StringIO(text))
        header = next(reader, None)
        if header is None:
            raise GeospatialCsvError("File is empty")
        normalized = tuple((cell or "").strip() for cell in header)
        if normalized != REQUIRED_HEADER:
            expected = ",".join(REQUIRED_HEADER)
            raise GeospatialCsvError(
                f"Header must be exactly {expected}"
            )

        rows: list[dict] = []
        seen: set[tuple[str, float]] = set()
        data_row = 0
        for raw_row in reader:
            if not raw_row or not any((cell or "").strip() for cell in raw_row):
                continue
            data_row += 1
            line_no = data_row + 1
            cells = [(cell or "").strip() for cell in raw_row]
            if len(cells) != len(REQUIRED_HEADER):
                raise GeospatialCsvError(
                    f"Row {line_no}: expected {len(REQUIRED_HEADER)} columns"
                )
            segment_name, kp_raw, lat_raw, lon_raw = cells
            if not segment_name:
                raise GeospatialCsvError(f"Row {line_no}: missing segment_name")
            kp = _finite_number(kp_raw, line_no, "kp")
            latitude = _finite_number(lat_raw, line_no, "latitude")
            longitude = _finite_number(lon_raw, line_no, "longitude")
            if latitude < -90 or latitude > 90:
                raise GeospatialCsvError(
                    f"Row {line_no}: latitude must be between -90 and 90"
                )
            if longitude < -180 or longitude > 180:
                raise GeospatialCsvError(
                    f"Row {line_no}: longitude must be between -180 and 180"
                )
            key = (segment_name, kp)
            if key in seen:
                raise GeospatialCsvError(
                    f"Row {line_no}: duplicated kp {kp} for segment {segment_name}"
                )
            seen.add(key)
            rows.append(
                {
                    "segment_name": segment_name,
                    "kp": kp,
                    "latitude": latitude,
                    "longitude": longitude,
                    "elevation": None,
                }
            )

        if not rows:
            raise GeospatialCsvError("File has no data rows")
        return rows


def _finite_number(raw: str, line_no: int, field: str) -> float:
    try:
        value = float(raw)
    except (TypeError, ValueError) as err:
        raise GeospatialCsvError(f"Row {line_no}: {field} must be a number") from err
    if not math.isfinite(value):
        raise GeospatialCsvError(f"Row {line_no}: {field} must be a number")
    return value
