# -*- coding: utf-8 -*-
"""P2 tables: suppressions, KPI history, archive. Additive. Context: BG/API."""
from __future__ import annotations

import logging
from datetime import datetime

from peewee import (
    BooleanField,
    CharField,
    DateTimeField,
    FloatField,
    IntegerField,
    TextField,
    TimestampField,
)

from ..timebase import TAGVALUE_TIMESTAMP_RESOLUTION
from .core import BaseModel


class AlarmSuppressions(BaseModel):
    alarm_id = IntegerField()
    suppression_type = CharField(max_length=16)
    operator_id = IntegerField(null=True)
    reason = TextField()
    timestamp_start = DateTimeField(default=datetime.utcnow)
    timestamp_end = DateTimeField(null=True)
    expires_at = DateTimeField(null=True)
    is_active = BooleanField(default=True)

    class Meta:
        table_name = "alarm_suppressions"


class AlarmKpiHistory(BaseModel):
    kpi_name = CharField(max_length=64)
    ts = TimestampField(utc=True, resolution=TAGVALUE_TIMESTAMP_RESOLUTION)
    value = FloatField(null=True)
    payload = CharField(max_length=512, null=True)

    class Meta:
        table_name = "alarm_kpi_history"
        indexes = ((("kpi_name", "ts"), False),)


class AlarmSummaryArchive(BaseModel):
    alarm_id = IntegerField(null=True)
    from_state = CharField(max_length=24, null=True)
    to_state = CharField(max_length=24, null=True)
    event_time = TimestampField(utc=True, null=True, resolution=TAGVALUE_TIMESTAMP_RESOLUTION)
    sample_uuid = CharField(max_length=255, null=True)
    archived_at = DateTimeField(default=datetime.utcnow)

    class Meta:
        table_name = "alarm_summary_archive"


def ensure_p2_schema(db=None) -> None:
    """Context: BG. Complexity: O(1) DDL. Additive, idempotent."""
    logger = logging.getLogger("pyautomation")
    models = (AlarmSuppressions, AlarmKpiHistory, AlarmSummaryArchive)
    try:
        if db is not None:
            for model in models:
                model._meta.database = db
        for model in models:
            model.create_table(safe=True)
    except Exception:
        logger.debug("p2 create_table skipped", exc_info=True)
    database = db or AlarmSummaryArchive._meta.database
    if database is None:
        return
    statements = (
        "CREATE INDEX IF NOT EXISTS idx_suppressions_active "
        "ON alarm_suppressions(alarm_id)",
        "CREATE INDEX IF NOT EXISTS idx_kpi_history_name_ts "
        "ON alarm_kpi_history(kpi_name, ts)",
        "CREATE INDEX IF NOT EXISTS idx_summary_archive_event_time "
        "ON alarm_summary_archive(event_time)",
        "CREATE INDEX IF NOT EXISTS idx_alarms_priority_time "
        "ON alarms(priority, last_transition_ts)",
    )
    for sql in statements:
        try:
            database.execute_sql(sql)
        except Exception:
            logger.debug("p2 index skipped sql=%s", sql, exc_info=True)
