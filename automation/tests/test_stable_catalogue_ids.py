# -*- coding: utf-8 -*-
"""Stable unit/variable IDs must match on historian and SAF catalog."""
from __future__ import annotations

import os
import tempfile
import unittest

from peewee import CharField, ForeignKeyField, IntegerField, Model, SqliteDatabase

from ..variables.stable_catalogue import (
    STABLE_UNIT_ID_BY_SYMBOL,
    STABLE_UNITS,
    STABLE_VARIABLES,
)
from ..variables.stable_seed import ensure_stable_catalogue_historian


def setUpModule():
    os.environ.setdefault("AUTOMATION_MULTI_EDGE_ENABLED", "false")


class TestStableCatalogueFrozen(unittest.TestCase):
    def test_adim_and_m3_ids(self):
        self.assertEqual(STABLE_UNIT_ID_BY_SYMBOL["adim"], 168)
        self.assertEqual(STABLE_UNIT_ID_BY_SYMBOL["m3"], 171)
        self.assertEqual(STABLE_UNIT_ID_BY_SYMBOL["%"], 167)
        self.assertEqual(STABLE_UNIT_ID_BY_SYMBOL["mW"], 90)
        self.assertEqual(STABLE_UNIT_ID_BY_SYMBOL["MW"], 86)

    def test_no_duplicate_ids_or_symbols(self):
        ids = [u[0] for u in STABLE_UNITS]
        symbols = [u[2] for u in STABLE_UNITS]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertEqual(len(symbols), len(set(symbols)))
        self.assertEqual(len(STABLE_VARIABLES), len({v[0] for v in STABLE_VARIABLES}))


class TestStableSeedHistorianSqlite(unittest.TestCase):
    def test_cold_seed_and_idempotent(self):
        from ..dbmodels import tags as tags_mod

        fd, path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        db = SqliteDatabase(path)
        try:
            class Variables(Model):
                name = CharField(unique=True)

                class Meta:
                    database = db
                    table_name = "variables"

            class Units(Model):
                name = CharField(unique=True)
                unit = CharField(unique=True)
                variable_id = ForeignKeyField(Variables, backref="units")

                class Meta:
                    database = db
                    table_name = "units"

            class Tags(Model):
                name = CharField(unique=True)
                unit = ForeignKeyField(Units, column_name="unit_id")
                display_unit = ForeignKeyField(Units, column_name="display_unit_id")

                class Meta:
                    database = db
                    table_name = "tags"

            class TagValue(Model):
                unit = ForeignKeyField(Units, column_name="unit_id", null=True)

                class Meta:
                    database = db
                    table_name = "tagvalue"

            db.bind([Variables, Units, Tags, TagValue])
            db.connect()
            db.create_tables([Variables, Units, Tags, TagValue])

            # Patch dbmodels used by ensure
            orig = (
                tags_mod.Variables,
                tags_mod.Units,
                tags_mod.Tags,
                tags_mod.TagValue,
            )
            tags_mod.Variables = Variables
            tags_mod.Units = Units
            tags_mod.Tags = Tags
            tags_mod.TagValue = TagValue
            try:
                stats = ensure_stable_catalogue_historian()
                self.assertEqual(stats["units_fixed"], len(STABLE_UNITS))
                adim = Units.get(Units.unit == "adim")
                m3 = Units.get(Units.unit == "m3")
                self.assertEqual(adim.id, 168)
                self.assertEqual(m3.id, 171)
                again = ensure_stable_catalogue_historian()
                self.assertEqual(again["units_fixed"], 0)
                self.assertEqual(Units.select().count(), len(STABLE_UNITS))
            finally:
                tags_mod.Variables, tags_mod.Units, tags_mod.Tags, tags_mod.TagValue = orig
        finally:
            try:
                db.close()
            except Exception:
                pass
            try:
                os.unlink(path)
            except OSError:
                pass


if __name__ == "__main__":
    unittest.main()
