# -*- coding: utf-8 -*-
"""Historian delete_tag must not call Tags.get_or_create (custom create signature)."""
from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch


class TestDataLoggerDeleteTag(unittest.TestCase):
    def test_delete_tag_uses_lookup_not_get_or_create(self):
        tag_row = SimpleNamespace(id=42, name="Supe.Linea2.TI_02")

        with patch(
            "automation.logger.datalogger._lookup_tag_row",
            return_value=tag_row,
        ) as lookup, patch(
            "automation.logger.datalogger.Tags.put",
        ) as put, patch(
            "automation.logger.datalogger.Tags.get_or_create",
        ) as get_or_create, patch(
            "automation.catalog.mutations.soft_deactivate_tag_local",
        ):
            from automation.logger.datalogger import DataLogger

            dl = DataLogger.__new__(DataLogger)
            dl.check_connectivity = MagicMock(return_value=True)
            dl.delete_tag(id="tag-uuid-1")

        lookup.assert_called_once_with(name="", identifier="tag-uuid-1")
        get_or_create.assert_not_called()
        put.assert_called_once_with(id=42, active=False)

    def test_delete_tag_missing_row_does_not_create(self):
        with patch(
            "automation.logger.datalogger._lookup_tag_row",
            return_value=None,
        ), patch(
            "automation.logger.datalogger.Tags.put",
        ) as put, patch(
            "automation.logger.datalogger.Tags.get_or_create",
        ) as get_or_create, patch(
            "automation.catalog.mutations.soft_deactivate_tag_local",
        ) as soft_delete:
            from automation.logger.datalogger import DataLogger

            dl = DataLogger.__new__(DataLogger)
            dl.check_connectivity = MagicMock(return_value=True)
            result = dl.delete_tag(id="missing-id")

        self.assertIsNone(result)
        get_or_create.assert_not_called()
        put.assert_not_called()
        soft_delete.assert_called_once_with(identifier="missing-id", name=None)


if __name__ == "__main__":
    unittest.main()
