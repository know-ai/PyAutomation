# -*- coding: utf-8 -*-
"""WD-09 / WD-10: mount options, SMART parse, sampler SSD alarm."""
from __future__ import annotations

import json
import unittest
from unittest.mock import mock_open, patch

from automation.utils.disk_mount import (
    _data_ordered,
    has_noatime,
    io_scheduler,
    mount_covering,
    parse_mountinfo,
)
from automation.utils.ssd_health import alarm_active, parse_smartctl_json
from automation.workers.metrics_sampler import MetricsSamplerWorker


_MOUNTINFO = """\
22 1 8:1 / / rw,relatime - ext4 /dev/sda1 rw,data=ordered
36 22 8:2 / /app/db rw,noatime - ext4 /dev/sdb1 rw,data=ordered
"""

_MOUNTINFO_ATIME = """\
22 1 8:1 / / rw,relatime - ext4 /dev/sda1 rw,data=ordered
36 22 8:2 / /app/db rw,relatime - ext4 /dev/sdb1 rw,data=ordered
"""


class TestDiskMount(unittest.TestCase):
    def test_noatime_detected_on_data_volume(self):
        mounts = parse_mountinfo(_MOUNTINFO)
        row = mount_covering("/app/db/saf/edge-a/journal.db", mounts)
        self.assertEqual(row["mount_point"], "/app/db")
        self.assertTrue(has_noatime("/app/db", mounts))

    def test_missing_noatime_is_false(self):
        mounts = parse_mountinfo(_MOUNTINFO_ATIME)
        self.assertFalse(has_noatime("/app/db", mounts))

    def test_ext4_data_ordered_on_data_volume(self):
        mounts = parse_mountinfo(_MOUNTINFO)
        row = mount_covering("/app/db", mounts)
        self.assertTrue(_data_ordered(row["fstype"], row["options"]))

    def test_scheduler_bracket_token(self):
        with patch("builtins.open", mock_open(read_data="none [mq-deadline] kyber\n")):
            self.assertEqual(io_scheduler("/dev/sda1"), "mq-deadline")


class TestSsdHealth(unittest.TestCase):
    def test_parse_nvme_json(self):
        parsed = parse_smartctl_json(
            {
                "nvme_smart_health_information_log": {
                    "percentage_used": 12,
                    "temperature": 41,
                }
            }
        )
        self.assertTrue(parsed["available"])
        self.assertEqual(parsed["wear_percent"], 12.0)
        self.assertEqual(parsed["temp_c"], 41.0)

    def test_parse_ata_attributes(self):
        parsed = parse_smartctl_json(
            {
                "ata_smart_attributes": {
                    "table": [
                        {"id": 194, "name": "Temperature_Celsius", "raw": {"value": 48}},
                        {"id": 177, "name": "Wear_Leveling_Count", "raw": {"value": 81}},
                    ]
                }
            }
        )
        self.assertEqual(parsed["temp_c"], 48.0)
        self.assertEqual(parsed["wear_percent"], 81.0)

    def test_alarm_when_wear_exceeds_warn(self):
        sample = {"available": True, "wear_percent": 85.0, "temp_c": 40.0}
        self.assertTrue(alarm_active(sample, wear_warn=80.0, temp_warn=65.0))
        self.assertFalse(alarm_active(sample, wear_warn=90.0, temp_warn=65.0))

    def test_no_alarm_when_smart_unavailable(self):
        self.assertFalse(alarm_active({"available": False, "wear_percent": 99, "temp_c": 90}))


class TestSamplerSsd(unittest.TestCase):
    def test_sample_ssd_sets_alarm_metric(self):
        worker = MetricsSamplerWorker(interval_seconds=5)
        worker._smart_at = 0.0
        payload = {}
        fake = {
            "available": True,
            "wear_percent": 90.0,
            "temp_c": 40.0,
            "device": "/dev/nvme0n1",
            "source": "smartctl",
        }
        with patch("automation.utils.ssd_health.collect", return_value=fake), patch(
            "automation.utils.ssd_health.wear_warn_percent", return_value=80.0
        ), patch("automation.utils.ssd_health.temp_warn_c", return_value=65.0), patch(
            "automation.utils.audit_metrics.cooldown_allows", return_value=True
        ), patch(
            "automation.utils.system_event_audit.persist_system_event"
        ) as persist:
            worker._sample_ssd(payload)
        self.assertEqual(payload["HOST_SSD_ALARM"], 1.0)
        self.assertEqual(payload["HOST_SSD_WEAR_PERCENT"], 90.0)
        persist.assert_called_once()

    def test_sample_ssd_quiet_when_unavailable(self):
        worker = MetricsSamplerWorker(interval_seconds=5)
        payload = {}
        with patch(
            "automation.utils.ssd_health.collect",
            return_value={"available": False, "wear_percent": None, "temp_c": None, "device": None},
        ):
            worker._sample_ssd(payload)
        self.assertEqual(payload["HOST_SSD_ALARM"], 0.0)
        self.assertFalse(payload["HOST_SSD_SMART_AVAILABLE"])


if __name__ == "__main__":
    unittest.main()
