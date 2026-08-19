#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""One-shot backfill of tag area/owner_node and Site.Area.Base names (multi-edge).

Destructive to tag *names* when re-qualification is required. Run only during
a maintenance window with a database backup.

Usage:
  python -m automation.scripts.backfill_tag_names [--dry-run] [--apply]
"""
from __future__ import annotations

import argparse
import logging
import sys

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger("backfill_tag_names")


def _load_app():
    from automation import PyAutomation

    app = PyAutomation()
    app._refresh_node_scope()
    return app


def backfill(*, dry_run: bool = True) -> dict:
    from automation.tag_naming import TagNameError, qualify_user_tag_name, tag_name_validation_skipped

    if tag_name_validation_skipped():
        logger.warning("AUTOMATION_SKIP_TAG_VALIDATION=true — aborting backfill")
        return {"skipped": True, "reason": "validation_disabled"}

    app = _load_app()
    scope = app.node_scope
    if not scope.enabled or not scope.is_valid:
        logger.error("Multi-edge scope is not configured: %s", scope.blocked_reason)
        return {"skipped": True, "reason": "invalid_scope"}

    stats = {"examined": 0, "updated": 0, "errors": 0}
    tags = app.cvt.get_tags() or []
    for row in tags:
        stats["examined"] += 1
        tag_id = row.get("id")
        name = row.get("name") or ""
        area = row.get("area")
        owner = row.get("owner_node")
        try:
            qualified = qualify_user_tag_name(name, scope.site, scope.area)
        except TagNameError as exc:
            logger.warning("Skip tag id=%s name=%r: %s", tag_id, name, exc)
            stats["errors"] += 1
            continue

        needs_name = qualified.name != name
        needs_area = area != scope.area
        needs_owner = owner != scope.node_id
        if not (needs_name or needs_area or needs_owner):
            continue

        logger.info(
            "Tag id=%s: name %r -> %r area=%s owner=%s",
            tag_id,
            name,
            qualified.name if needs_name else name,
            scope.area,
            scope.node_id,
        )
        if dry_run:
            stats["updated"] += 1
            continue

        payload = {
            "area": scope.area,
            "owner_node": scope.node_id,
        }
        if needs_name:
            payload["name"] = qualified.name
        updated, msg = app.update_tag(id=tag_id, **payload)
        if updated is None:
            logger.error("Failed id=%s: %s", tag_id, msg)
            stats["errors"] += 1
        else:
            stats["updated"] += 1

    return stats


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Backfill tag Site.Area.Base names")
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
