# -*- coding: utf-8 -*-
"""Background P2 jobs. Context: BG. Never HOT/COLD worker."""
from __future__ import annotations

from automation.alarms.p2.kpi import KPIComputer
from automation.alarms.runtime import get_alarm_runtime


def run_p2_maintenance() -> dict:
    """Context: BG. Complexity: O(chunk)+O(1) DDL. Expire silence, archive, partitions."""
    runtime = get_alarm_runtime()
    expired = runtime.suppression.expire_due()
    archived = runtime.archiver.run()
    created = runtime.partitions.ensure()
    dropped = runtime.partitions.drop_old()
    snap = KPIComputer().compute(runtime.kpi)
    hist = getattr(runtime, "kpi_history", None)
    if hist is not None:
        hist.save(snap)
    return {
        "expired": expired,
        "archived": archived,
        "partitions_created": created,
        "partitions_dropped": dropped,
        "kpis": snap,
    }
