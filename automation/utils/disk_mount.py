# -*- coding: utf-8 -*-
"""Inspect mount options and I/O scheduler for the edge data volume.

Reads /proc (no ``mount`` binary). Distroless-safe. Never raises to callers.
"""
from __future__ import annotations

import logging
import os
import re
from typing import Any

_LOGGER = logging.getLogger("pyautomation.metrics")
_warned_noatime = False

_DEFAULT_DATA_DIR = os.path.join(".", "db")


def data_dir() -> str:
    env = os.environ.get("AUTOMATION_DATA_DIR", "").strip()
    if env:
        return os.path.abspath(env)
    try:
        from ..persistence.config import SafConfig

        cfg = SafConfig.from_app_config(None)
        parent = os.path.dirname(os.path.abspath(cfg.journal_path))
        return parent or os.path.abspath(_DEFAULT_DATA_DIR)
    except Exception:
        return os.path.abspath(_DEFAULT_DATA_DIR)


def parse_mountinfo(text: str) -> list[dict[str, Any]]:
    """Parse ``/proc/self/mountinfo`` (Linux). See proc(5)."""
    rows: list[dict[str, Any]] = []
    for line in text.splitlines():
        if " - " not in line:
            continue
        left, right = line.split(" - ", 1)
        left_parts = left.split()
        right_parts = right.split()
        if len(left_parts) < 6 or len(right_parts) < 2:
            continue
        mount_point = left_parts[4]
        options = left_parts[5]
        fstype = right_parts[0]
        source = right_parts[1]
        super_opts = right_parts[2] if len(right_parts) > 2 else ""
        opt_set = {part.strip() for part in f"{options},{super_opts}".split(",") if part.strip()}
        rows.append(
            {
                "mount_point": mount_point,
                "fstype": fstype,
                "source": source,
                "options": opt_set,
            }
        )
    return rows


def _read_mountinfo(path: str = "/proc/self/mountinfo") -> list[dict[str, Any]]:
    try:
        with open(path, encoding="utf-8") as handle:
            return parse_mountinfo(handle.read())
    except OSError:
        return []


def mount_covering(target: str, mounts: list[dict[str, Any]] | None = None) -> dict[str, Any] | None:
    """Longest mount-point prefix of ``target``."""
    abs_target = os.path.abspath(target or ".")
    best: dict[str, Any] | None = None
    best_len = -1
    for row in mounts if mounts is not None else _read_mountinfo():
        point = str(row.get("mount_point") or "")
        if not point:
            continue
        if abs_target == point or abs_target.startswith(point.rstrip("/") + "/") or (
            point == "/" and abs_target.startswith("/")
        ):
            if len(point) > best_len:
                best = row
                best_len = len(point)
    return best


def has_noatime(target: str | None = None, mounts: list[dict[str, Any]] | None = None) -> bool | None:
    row = mount_covering(target or data_dir(), mounts)
    if row is None:
        return None
    options = row.get("options") or set()
    return "noatime" in options


def io_scheduler(source: str) -> str | None:
    """Active I/O scheduler for a block device (``[mq-deadline] none`` → mq-deadline)."""
    name = _block_name(source)
    if not name:
        return None
    path = f"/sys/block/{name}/queue/scheduler"
    try:
        raw = open(path, encoding="utf-8").read().strip()
    except OSError:
        return None
    match = re.search(r"\[([^\]]+)\]", raw)
    if match:
        return match.group(1)
    parts = raw.split()
    return parts[0] if parts else raw or None


def _block_name(source: str) -> str | None:
    device = os.path.basename(str(source or "").strip())
    if not device or device in {"none", "overlay", "tmpfs"}:
        return None
    # nvme0n1p1 → nvme0n1 ; sda1 → sda ; mmcblk0p2 → mmcblk0
    if device.startswith("nvme") and "p" in device:
        return device.rsplit("p", 1)[0]
    if device.startswith("mmcblk") and "p" in device:
        return device.rsplit("p", 1)[0]
    stripped = re.sub(r"\d+$", "", device)
    return stripped or device


def snapshot(target: str | None = None) -> dict[str, Any]:
    directory = os.path.abspath(target or data_dir())
    row = mount_covering(directory)
    payload: dict[str, Any] = {
        "HOST_DISK_MOUNT_PATH": directory,
        "HOST_DISK_FSTYPE": None,
        "HOST_DISK_MOUNT_SOURCE": None,
        "HOST_DISK_NOATIME": None,
        "HOST_DISK_DATA_ORDERED": None,
        "HOST_DISK_IO_SCHEDULER": None,
    }
    if row is None:
        return payload
    options = row.get("options") or set()
    payload["HOST_DISK_FSTYPE"] = row.get("fstype")
    payload["HOST_DISK_MOUNT_SOURCE"] = row.get("source")
    payload["HOST_DISK_NOATIME"] = bool("noatime" in options)
    payload["HOST_DISK_DATA_ORDERED"] = _data_ordered(row.get("fstype"), options)
    payload["HOST_DISK_IO_SCHEDULER"] = io_scheduler(str(row.get("source") or ""))
    return payload


def _data_ordered(fstype: Any, options: set) -> bool | None:
    """ext4 ``data=ordered`` / ``data=journal``; XFS is ordered by design."""
    kind = str(fstype or "").lower()
    if kind in {"xfs", "btrfs", "zfs"}:
        return True
    if kind != "ext4":
        return None
    return bool({"data=ordered", "data=journal"} & set(options))


def warn_if_missing_noatime(target: str | None = None) -> bool:
    """Log once when the data volume lacks ``noatime``. Returns True if options look good."""
    global _warned_noatime
    flag = has_noatime(target)
    if flag is True:
        return True
    if flag is False and not _warned_noatime:
        _warned_noatime = True
        _LOGGER.warning(
            "Data volume %s is mounted without noatime; see docs/HARDWARE_REQUIREMENTS.md",
            target or data_dir(),
        )
    return bool(flag)
