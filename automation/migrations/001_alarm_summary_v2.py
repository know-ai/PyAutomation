# -*- coding: utf-8 -*-
"""Additive alarm_summary schema_version=2 (SPEC-ISA18-2-P0P1 P1-1).

Idempotent: adds columns if missing and backfills schema_version=1 rows.
Does not drop the legacy ``state`` column.
"""
from __future__ import annotations


def apply(db=None) -> None:
    from ..dbmodels.alarms import AlarmSummary, Alarms, ensure_alarm_delay_schema

    if db is not None:
        ensure_alarm_delay_schema(db)
        AlarmSummary._meta.database = db
        Alarms._meta.database = db
    AlarmSummary.ensure_schema()
