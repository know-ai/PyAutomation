# -*- coding: utf-8 -*-
"""Runtime tag → historian catalog (SAF) registration."""
from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch


class TestEnsureTagHistorianCatalog(unittest.TestCase):
    def test_notify_tag_catalog_changed_emits_socket_event(self):
        app = MagicMock()
        app.sio = MagicMock()

        with patch("automation.PyAutomation", return_value=app):
            from automation.catalog.runtime_tag import notify_tag_catalog_changed

            notify_tag_catalog_changed(
                "Supe.Linea2.TI_02",
                action="upsert",
                reason="create_tag",
            )

        app.sio.emit.assert_called_once_with(
            "on.tag_catalog",
            data={
                "name": "Supe.Linea2.TI_02",
                "action": "upsert",
                "reason": "create_tag",
            },
        )

    def test_persists_local_nudges_and_clears_saf_retry(self):
        tag = SimpleNamespace(name="Supe.Linea2.TI_02", id="tid-1")
        worker = MagicMock()
        app = MagicMock()
        app.is_db_connected.return_value = False

        with patch(
            "automation.catalog.runtime_tag.persist_tag_to_local",
            create=True,
        ) as persist, patch(
            "automation.catalog.seed.persist_tag_to_local",
            persist,
        ), patch(
            "automation.catalog.runtime_tag.PyAutomation",
            create=True,
        ), patch(
            "automation.PyAutomation",
            return_value=app,
        ), patch(
            "automation.catalog.runtime_tag.nudge_tag_catalog_push",
            create=True,
        ) as nudge, patch(
            "automation.persistence.remote.nudge_tag_catalog_push",
            nudge,
        ), patch(
            "automation.catalog.runtime_tag.clear_missing_tag_retry",
            create=True,
        ) as clear_retry, patch(
            "automation.persistence.remote.clear_missing_tag_retry",
            clear_retry,
        ), patch(
            "automation.catalog.runtime_tag.get_catalog_replicator",
            create=True,
            return_value=worker,
        ), patch(
            "automation.catalog.replicator.get_catalog_replicator",
            return_value=worker,
        ):
            from automation.catalog.runtime_tag import ensure_tag_historian_catalog

            ok = ensure_tag_historian_catalog(tag, reason="test")

        self.assertFalse(ok)
        persist.assert_called_once_with(tag, update_units=False)
        nudge.assert_called_once_with("Supe.Linea2.TI_02")
        clear_retry.assert_called_once_with("Supe.Linea2.TI_02")
        worker.request_full_sync.assert_called_once()
        app.logger_engine.set_tag.assert_not_called()
        app.sio.emit.assert_called_once_with(
            "on.tag_catalog",
            data={"name": "Supe.Linea2.TI_02", "action": "upsert", "reason": "test"},
        )

    def test_writes_historian_when_db_connected(self):
        tag = SimpleNamespace(name="Supe.Linea2.TI_02", id="tid-1")
        worker = MagicMock()
        app = MagicMock()
        app.is_db_connected.return_value = True

        with patch(
            "automation.catalog.seed.persist_tag_to_local",
        ), patch(
            "automation.PyAutomation",
            return_value=app,
        ), patch(
            "automation.persistence.remote.nudge_tag_catalog_push",
        ), patch(
            "automation.persistence.remote.clear_missing_tag_retry",
        ), patch(
            "automation.catalog.replicator.get_catalog_replicator",
            return_value=worker,
        ), patch(
            "automation.dbmodels.tags.Tags.read_by_name",
            return_value=SimpleNamespace(id=1),
        ):
            from automation.catalog.runtime_tag import ensure_tag_historian_catalog

            ok = ensure_tag_historian_catalog(tag, reason="test")

        self.assertTrue(ok)
        app.logger_engine.set_tag.assert_called_once_with(tag=tag)


if __name__ == "__main__":
    unittest.main()
