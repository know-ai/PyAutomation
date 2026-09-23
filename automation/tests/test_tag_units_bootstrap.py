# -*- coding: utf-8 -*-
"""Bootstrap must not overwrite persisted tag units (spec 12 CA-UNIT-03/04/05/07)."""
from __future__ import annotations

import os
import unittest
from unittest.mock import MagicMock, patch

from ..logger.datalogger import DataLogger, _set_tag_put_fields
from ..tags.unit_provenance import UNIT_SOURCE_OPERATOR


def setUpModule():
    os.environ.setdefault("AUTOMATION_MULTI_EDGE_ENABLED", "false")


class TestTagUnitsBootstrap(unittest.TestCase):
    def test_ca_unit_03_existing_row_omits_unit_fields(self):
        payload = _set_tag_put_fields(
            update_units=False,
            unit="Pa",
            display_unit="Pa",
            unit_source="engine",
            name="PI_01",
            data_type="float",
            description="",
            display_name="PI_01",
        )
        self.assertNotIn("unit", payload)
        self.assertNotIn("display_unit", payload)
        self.assertNotIn("unit_source", payload)
        self.assertEqual(payload["name"], "PI_01")

    def test_update_units_true_includes_symbols(self):
        payload = _set_tag_put_fields(
            update_units=True,
            unit="bar",
            display_unit="bar",
            unit_source=UNIT_SOURCE_OPERATOR,
            name="PI_01",
            data_type="float",
            description="",
            display_name="PI_01",
        )
        self.assertEqual(payload["unit"], "bar")
        self.assertEqual(payload["display_unit"], "bar")
        self.assertEqual(payload["unit_source"], UNIT_SOURCE_OPERATOR)

    def test_ca_unit_03_set_tag_put_skips_units(self):
        existing = MagicMock()
        existing.id = 7
        logger = DataLogger()
        logger.check_connectivity = MagicMock(return_value=True)
        with patch(
            "automation.logger.datalogger._lookup_tag_row", return_value=existing
        ), patch("automation.logger.datalogger.Tags") as tags_mod, patch(
            "automation.logger.datalogger._mirror_historian_tag_row"
        ):
            logger.set_tag(
                id="abc",
                name="SITE.AREA.PI_01",
                unit="Pa",
                data_type="float",
                description="",
                display_name="PI_01",
                display_unit="Pa",
            )
            kwargs = tags_mod.put.call_args.kwargs
            self.assertNotIn("unit", kwargs)
            self.assertNotIn("display_unit", kwargs)

    def test_ca_unit_04_ten_restarts_stable_put(self):
        dumps = []
        for _ in range(10):
            dumps.append(
                sorted(
                    _set_tag_put_fields(
                        update_units=False,
                        unit="Pa",
                        display_unit="Pa",
                        name="PI_01",
                        data_type="float",
                        description="inlet",
                        display_name="PI_01",
                    ).items()
                )
            )
        self.assertEqual(len(set(tuple(d) for d in dumps)), 1)

    def test_ca_unit_05_new_insert_marks_engine(self):
        logger = DataLogger()
        logger.check_connectivity = MagicMock(return_value=True)
        with patch(
            "automation.logger.datalogger._lookup_tag_row", return_value=None
        ), patch("automation.logger.datalogger.Tags") as tags_mod, patch(
            "automation.logger.datalogger._mirror_historian_tag_row"
        ):
            tags_mod.create.return_value = MagicMock()
            logger.set_tag(
                id="abc",
                name="SITE.AREA.PI_01",
                unit="Pa",
                data_type="float",
                description="",
                display_name="PI_01",
                display_unit="Pa",
            )
            kwargs = tags_mod.create.call_args.kwargs
            self.assertEqual(kwargs["unit"], "Pa")
            self.assertEqual(kwargs["display_unit"], "Pa")
            self.assertEqual(kwargs["unit_source"], "engine")

    def test_persist_tag_to_local_keeps_existing_unit_fk(self):
        tag = MagicMock()
        tag.unit = "Pa"
        tag.display_unit = "Pa"
        tag.data_type = "float"
        tag.name = "PI_01"
        tag.id = "id1"
        existing = {
            "_pk": 3,
            "id": 3,
            "unit": 99,
            "display_unit": 99,
            "unit_source": "operator",
        }
        with patch("automation.catalog.seed.get_catalog_database", return_value=object()), patch(
            "automation.catalog.seed._find_unit_by_symbol", return_value={"_pk": 1, "id": 1}
        ), patch(
            "automation.catalog.seed._find_by_name",
            side_effect=lambda table, name, field="name": (
                existing if table == "tags" else {"_pk": 2, "id": 2, "name": "float"}
            ),
        ), patch("automation.catalog.seed._upsert") as upsert, patch(
            "automation.catalog.seed.align_tag_to_persisted_units", create=True
        ):
            from ..catalog.seed import persist_tag_to_local

            persist_tag_to_local(tag, update_units=False)
            payload = upsert.call_args[0][1]
            self.assertEqual(payload["unit"], 99)
            self.assertEqual(payload["display_unit"], 99)
            self.assertEqual(payload["unit_source"], "operator")
