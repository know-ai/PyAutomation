#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Qualify wavelet ``.f`` tags so ``Tags.display_name`` is globally unique.

Existing rows that used DisplayNameRaw (e.g. ``FI_02.f``) collide across areas.
This script sets ``name`` and ``display_name`` to ``{source.name}.f``.

Usage:
  python -m automation.scripts.migrate_filtered_tags [--dry-run] [--apply]
"""
from __future__ import annotations

import argparse
import logging
import sys

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger("migrate_filtered_tags")


def _load_app():
    from automation import PyAutomation

    app = PyAutomation()
    app._refresh_node_scope()
    return app


def migrate_filtered_tags(*, dry_run: bool = True) -> dict:
    from automation.dbmodels.tags import Tags
    from automation.signal_conditioning.filtered_tags import (
        filtered_tag_name,
        is_filtered_derivative_name,
        source_tag_name,
    )

    app = _load_app()
    if not app.is_db_connected():
        logger.error("Historian is not connected; aborting")
        return {"skipped": True, "reason": "historian_offline"}

    stats = {"examined": 0, "migrated": 0, "skipped": 0, "errors": 0}
    rows = list(Tags.select().where(Tags.name.endswith(".f")))
    for tag in rows:
        stats["examined"] += 1
        old_name = tag.name
        try:
            if not is_filtered_derivative_name(old_name):
                stats["skipped"] += 1
                continue
            source_name = source_tag_name(old_name)
            source = Tags.get_or_none(Tags.name == source_name)
            if source is None:
                logger.warning("Source tag %s not found for %s", source_name, old_name)
                stats["errors"] += 1
                continue
            new_name = filtered_tag_name(source.name)
            desired_display = new_name
            needs_name = new_name != tag.name
            needs_display = (tag.display_name or "") != desired_display
            if not needs_name and not needs_display:
                stats["skipped"] += 1
                continue
            if needs_name:
                conflict = Tags.get_or_none(Tags.name == new_name)
                if conflict is not None and conflict.id != tag.id:
                    logger.warning(
                        "Target name %s already exists; skipping %s", new_name, old_name
                    )
                    stats["errors"] += 1
                    continue
            display_conflict = Tags.get_or_none(Tags.display_name == desired_display)
            if display_conflict is not None and display_conflict.id != tag.id:
                logger.warning(
                    "Target display_name %s already exists; skipping %s",
                    desired_display,
                    old_name,
                )
                stats["errors"] += 1
                continue
            logger.info(
                "Filtered tag id=%s: name %r -> %r display %r -> %r",
                tag.identifier,
                old_name,
                new_name,
                tag.display_name,
                desired_display,
            )
            if dry_run:
                stats["migrated"] += 1
                continue
            payload = {"display_name": desired_display}
            if needs_name:
                payload["name"] = new_name
            Tags.put(id=tag.id, **payload)
            try:
                app.cvt.update_tag(id=tag.identifier, **payload)
            except Exception:
                logger.debug("CVT update skipped for %s", old_name, exc_info=True)
            try:
                app.logger_engine.update_tag(id=tag.identifier, **payload)
            except Exception:
                logger.debug("historian update skipped for %s", old_name, exc_info=True)
            stats["migrated"] += 1
        except Exception as exc:
            logger.error("Error migrating %s: %s", old_name, exc)
            stats["errors"] += 1

    logger.info(
        "Migration complete: %s migrated, %s skipped, %s errors (examined %s)",
        stats["migrated"],
        stats["skipped"],
        stats["errors"],
        stats["examined"],
    )
    return stats


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Qualify filtered .f tag names and display_name by area"
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Persist changes (default is dry-run)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Alias of the default dry-run mode",
    )
    args = parser.parse_args(argv)
    dry_run = not args.apply
    if dry_run:
        logger.info("Dry-run mode (pass --apply to persist)")
    stats = migrate_filtered_tags(dry_run=dry_run)
    logger.info("Done: %s", stats)
    if stats.get("skipped") is True:
        return 1
    return 0 if stats.get("errors", 0) == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
