#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""One-shot backfill of alarm area and alarm.Site.Area.Base names (multi-edge).

Destructive to alarm *names* when re-qualification is required. Run only during
a maintenance window with a database backup.

Usage:
  python -m automation.scripts.backfill_alarm_names [--dry-run] [--apply]
"""
from __future__ import annotations

import argparse
import logging
import sys

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger("backfill_alarm_names")


def _load_app():
    from automation import PyAutomation

    app = PyAutomation()
    app._refresh_node_scope()
    return app


def _is_internal_name(name: str) -> bool:
    parts = [p for p in (name or "").split(".") if p]
    return len(parts) > 4


def backfill(*, dry_run: bool = True) -> dict:
    from automation.alarm_naming import (
        AlarmNameError,
        alarm_name_validation_skipped,
        qualify_user_alarm_name,
    )

    if alarm_name_validation_skipped():
        logger.warning("AUTOMATION_SKIP_ALARM_VALIDATION=true — aborting backfill")
        return {"skipped": True, "reason": "validation_disabled"}

    app = _load_app()
    scope = app.node_scope
    if not scope.enabled or not scope.is_valid:
        logger.error("Multi-edge scope is not configured: %s", scope.blocked_reason)
        return {"skipped": True, "reason": "invalid_scope"}

    stats = {"examined": 0, "updated": 0, "errors": 0, "internal_skipped_rename": 0}
    alarms = list(app.alarm_manager.get_alarms().values())
    for alarm in alarms:
        stats["examined"] += 1
        name = alarm.name or ""
        current_area = getattr(alarm, "area", None)
        new_name = name
        if _is_internal_name(name):
            stats["internal_skipped_rename"] += 1
        else:
            try:
                qualified = qualify_user_alarm_name(name, scope.site, scope.area)
                new_name = qualified.name
            except AlarmNameError as exc:
                logger.warning("Skip alarm id=%s name=%r: %s", alarm.identifier, name, exc)
                stats["errors"] += 1
                continue

        needs_name = new_name != name
        needs_area = current_area != scope.area
        if not (needs_name or needs_area):
            continue

        logger.info(
            "Alarm id=%s: name %r -> %r area=%s",
            alarm.identifier,
            name,
            new_name if needs_name else name,
            scope.area,
        )
        if dry_run:
            stats["updated"] += 1
            continue

        if needs_name:
            app.update_alarm(id=alarm.identifier, name=new_name)
            refreshed = app.get_alarm(alarm.identifier)
            if refreshed is None or refreshed.name != new_name:
                logger.error("Failed rename id=%s", alarm.identifier)
                stats["errors"] += 1
                continue
            alarm = refreshed
        alarm.area = scope.area
        if app.is_db_connected():
            try:
                from automation.dbmodels.alarms import Alarms

                record = Alarms.read_by_identifier(identifier=alarm.identifier)
                if record is not None:
                    fields = {"area": scope.area}
                    if needs_name:
                        fields["name"] = new_name
                    Alarms.put(id=record.id, **fields)
            except Exception:
                logger.exception("Failed DB area stamp id=%s", alarm.identifier)
                stats["errors"] += 1
                continue
        stats["updated"] += 1

    return stats


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Backfill alarm.Site.Area.Base names")
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Persist changes (default is dry-run)",
    )
    args = parser.parse_args(argv)
    dry_run = not args.apply
    if dry_run:
        logger.info("Dry-run mode (pass --apply to persist)")
    stats = backfill(dry_run=dry_run)
    logger.info("Done: %s", stats)
    return 0 if stats.get("errors", 0) == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
