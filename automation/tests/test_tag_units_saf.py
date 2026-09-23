# -*- coding: utf-8 -*-
"""Tag unit freeze in SAF journal (spec 12 CA-UNIT-01/02/11)."""
from __future__ import annotations

import logging
import os
import unittest
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from ..persistence.records import PersistableRecord
from ..persistence.remote import TagValuePayloadMapper
from ..utils.unit_metrics import (
    get_saf_samples_without_unit,
    reset_unit_metrics,
)


def setUpModule():
    os.environ.setdefault("AUTOMATION_MULTI_EDGE_ENABLED", "false")


class TestTagUnitsSaf(unittest.TestCase):
    def setUp(self):
        reset_unit_metrics()

    def test_ca_unit_01_tag_sample_freezes_unit(self):
        ts = datetime.now(timezone.utc)
        record = PersistableRecord.tag_sample(
            "PI_01",
            101325.0,
            ts,
            unit="Pa",
            unit_source="engine",
            display_unit_at_sample="Pa",
        )
        payload = dict(record.payload())
        self.assertEqual(payload["unit"], "Pa")
        self.assertEqual(payload["unit_source"], "engine")
        self.assertEqual(payload["display_unit_at_sample"], "Pa")

    def test_legacy_tag_sample_omits_unit_key(self):
        record = PersistableRecord.tag_sample(
            "PI_01", 1.0, datetime.now(timezone.utc)
        )
        payload = dict(record.payload())
        self.assertNotIn("unit", payload)

    def test_ca_unit_02_mapper_prefers_frozen_symbol(self):
        frozen = MagicMock(name="PaRow")
        live = MagicMock(name="barRow")
        tag = MagicMock()
        tag.id = 11
        tag.name = "PI_01"
        tag.display_unit = live
        tag.unit = live
        tag.variable = "Pressure"
        mapper = TagValuePayloadMapper(resolve_tag=lambda _n: tag)
        item = {
            "tag": "PI_01",
            "value": 101325.0,
            "timestamp": datetime.now(timezone.utc),
            "unit": "Pa",
        }
        with patch(
            "automation.persistence.remote._historian_unit_for_symbol",
            return_value=frozen,
        ) as lookup:
            row = mapper._map_one(item, logging.getLogger("pyautomation"))
        self.assertIsNotNone(row)
        self.assertIs(row["unit"], frozen)
        lookup.assert_called()
        self.assertEqual(lookup.call_args[0][0], "Pa")

    def test_ca_unit_11_legacy_sample_increments_counter(self):
        live = MagicMock(name="barRow")
        live.id = 3
        tag = MagicMock()
        tag.id = 22
        tag.name = "PI_01"
        tag.display_unit = live
        tag.unit = live
        mapper = TagValuePayloadMapper(
            resolve_tag=lambda _n: tag,
            resolve_unit=lambda _tag: live,
        )
        item = {
            "tag": "PI_01",
            "value": 5.0,
            "timestamp": datetime.now(timezone.utc),
        }
        before = get_saf_samples_without_unit()
        row = mapper._map_one(item, logging.getLogger("pyautomation"))
        self.assertIs(row["unit"], live)
        self.assertEqual(get_saf_samples_without_unit(), before + 1)
