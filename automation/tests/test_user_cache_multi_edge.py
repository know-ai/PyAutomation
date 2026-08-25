# -*- coding: utf-8 -*-
"""CA-USER-MULTI: Read-Through login and cross-edge user cache invalidation."""
from __future__ import annotations

import time
import unittest
from unittest.mock import MagicMock, patch

from peewee import OperationalError


class TestLoginReadThrough(unittest.TestCase):
    def _app(self, *, connected: bool):
        from automation.core import PyAutomation

        app = MagicMock()
        app.is_db_connected.return_value = connected
        app._login_local_catalog = lambda password, username="", email="": PyAutomation._login_local_catalog(
            app, password, username, email
        )
        app._format_database_error = lambda *a, **k: "db error"
        return app

    def test_login_uses_remote_when_db_up(self):
        from automation.core import PyAutomation

        app = self._app(connected=True)
        db = MagicMock()
        app.db_manager.get_db.return_value = db
        remote_user = MagicMock(username="alice", password="hash")
        app.db_manager.login.return_value = (remote_user, "Login successful")
        with patch("automation.catalog.auth.login_local") as local, patch(
            "automation.catalog.user_cache.cache_user_locally"
        ) as cache:
            user, message = PyAutomation.login(app, "secret", username="alice")
        local.assert_not_called()
        app.db_manager.login.assert_called_once_with(
            password="secret", username="alice", email=""
        )
        cache.assert_called_once_with(remote_user)
        self.assertIs(user, remote_user)
        self.assertEqual(message, "Login successful")
        db.execute_sql.assert_called()

    def test_login_fallback_local_when_db_down(self):
        from automation.core import PyAutomation

        app = self._app(connected=False)
        local_user = MagicMock(username="alice")
        with patch(
            "automation.catalog.auth.login_local",
            return_value=(local_user, "Login successful (local catalog)"),
        ) as local:
            user, message = PyAutomation.login(app, "secret", username="alice")
        local.assert_called_once()
        app.db_manager.login.assert_not_called()
        self.assertIs(user, local_user)
        self.assertIn("local catalog", message)

    def test_login_fallback_local_when_select_fails(self):
        from automation.core import PyAutomation

        app = self._app(connected=True)
        db = MagicMock()
        db.execute_sql.side_effect = OperationalError("historian down")
        app.db_manager.get_db.return_value = db
        local_user = MagicMock(username="alice")
        with patch(
            "automation.catalog.auth.login_local",
            return_value=(local_user, "Login successful (local catalog)"),
        ) as local:
            user, _message = PyAutomation.login(app, "secret", username="alice")
        local.assert_called_once()
        app.db_manager.login.assert_not_called()
        self.assertIs(user, local_user)

    def test_invalid_remote_credentials_do_not_fallback(self):
        from automation.core import PyAutomation

        app = self._app(connected=True)
        db = MagicMock()
        app.db_manager.get_db.return_value = db
        app.db_manager.login.return_value = (None, "Invalid credentials")
        with patch("automation.catalog.auth.login_local") as local:
            user, message = PyAutomation.login(app, "wrong", username="alice")
        local.assert_not_called()
        self.assertIsNone(user)
        self.assertIn("Invalid credentials", message)


class TestUserInvalidate(unittest.TestCase):
    def test_invalidate_deletes_local_row(self):
        from automation.catalog import user_cache

        with patch.object(user_cache, "delete_local_user", return_value=True) as delete, patch.object(
            user_cache, "drop_cvt_user"
        ) as drop, patch.object(user_cache, "_origin_node", return_value="edge-a"):
            user_cache.apply_user_invalidate(username="alice", origin="edge-b")
        delete.assert_called_once_with("alice")
        drop.assert_called_once_with("alice")

    def test_invalidate_skips_origin_edge(self):
        from automation.catalog import user_cache

        with patch.object(user_cache, "delete_local_user") as delete, patch.object(
            user_cache, "_origin_node", return_value="edge-a"
        ):
            user_cache.apply_user_invalidate(username="alice", origin="edge-a")
        delete.assert_not_called()

    def test_signup_to_login_under_two_seconds(self):
        """CA-USER-03: invalidation is the sync path, not the 30s replicator."""
        from automation.catalog import user_cache

        started = time.monotonic()
        with patch.object(user_cache, "_origin_node", return_value="edge-b"), patch.object(
            user_cache, "delete_local_user", return_value=True
        ), patch.object(user_cache, "drop_cvt_user"):
            user_cache.notify_user_invalidated("alice")
            user_cache.apply_user_invalidate(username="alice", origin="edge-a")
        self.assertLessEqual(time.monotonic() - started, 2.0)

    def test_password_change_notify_is_not_replicator(self):
        from automation.catalog.replicator import _CATCHUP_INTERVAL_S
        from automation.catalog.user_cache import notify_user_invalidated

        self.assertGreaterEqual(_CATCHUP_INTERVAL_S, 30.0)
        with patch("automation.PyAutomation") as pyauto:
            app = MagicMock()
            app.is_db_connected.return_value = True
            db = MagicMock()
            app.db_manager.get_db.return_value = db
            pyauto.return_value = app
            with patch("automation.utils.redis_client.get_redis", return_value=None):
                notify_user_invalidated("alice")
            db.execute_sql.assert_called()
            args = db.execute_sql.call_args[0]
            self.assertIn("pg_notify", args[0])


if __name__ == "__main__":
    unittest.main()
