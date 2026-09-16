# -*- coding: utf-8 -*-
"""Additive P2 columns + tables (SPEC-ISA18-2-P2-CLOSURE-v2)."""
from __future__ import annotations


def apply(db=None) -> None:
    from ..dbmodels.alarm_p2 import ensure_p2_schema
    from ..dbmodels.alarms import AlarmSummary, ensure_alarm_delay_schema

    if db is not None:
        ensure_alarm_delay_schema(db)
        AlarmSummary._meta.database = db
    ensure_p2_schema(db)
    AlarmSummary.ensure_schema()
