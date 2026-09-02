# -*- coding: utf-8 -*-
"""Duplicate signup must return a validation message, not a historian outage."""
from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from ..core import PyAutomation
from ..dbmodels.users import Users
from ..modules.users.roles import Role
from ..modules.users.roles import roles as cvt_roles
from ..modules.users.users import users as cvt_users


class TestSignupDuplicate(unittest.TestCase):
    def setUp(self) -> None:
        cvt_users._delete_all()
        cvt_roles._delete_all()
        cvt_roles.add(role=Role(name="admin", level=1, identifier="roleadmin"))
        user, message = cvt_users.signup(
            username="crivero80",
            role_name="admin",
            email="crivero80@example.com",
            password="secret",
        )
        self.assertIsNotNone(user, message)

    def tearDown(self) -> None:
        cvt_users._delete_all()
        cvt_roles._delete_all()

    def test_create_rejects_none_user(self):
        created, message = Users.create(None)
        self.assertIsNone(created)
        self.assertIn("user is required", message)

    def test_duplicate_username_when_historian_connected(self):
        app = PyAutomation()
        with patch.object(app, "is_db_connected", return_value=True), patch.object(
            app, "db_manager"
        ) as db_manager:
            user, message = app.signup(
                username="crivero80",
                email="other@example.com",
                password="secret",
                role_name="admin",
            )
        self.assertIsNone(user)
        self.assertIn("already exists", message)
        self.assertIn("crivero80", message)
        db_manager.set_user.assert_not_called()

    def test_duplicate_email_when_historian_connected(self):
        app = PyAutomation()
        with patch.object(app, "is_db_connected", return_value=True), patch.object(
            app, "db_manager"
        ) as db_manager:
            user, message = app.signup(
                username="admin",
                email="crivero80@example.com",
                password="secret",
                role_name="admin",
            )
        self.assertIsNone(user)
        self.assertIn("already exists", message)
        self.assertIn("crivero80@example.com", message)
        db_manager.set_user.assert_not_called()

    def test_historian_duplicate_is_returned_as_validation(self):
        app = PyAutomation()
        with patch.object(app, "is_db_connected", return_value=True), patch.object(
            app, "db_manager"
        ) as db_manager:
            db_manager.get_db.return_value = MagicMock()
            db_manager.set_user.return_value = (
                None,
                "username: admin already exists",
            )
            user, message = app.signup(
                username="admin",
                email="admin@example.com",
                password="secret",
                role_name="admin",
            )
        self.assertIsNone(user)
        self.assertIn("already exists", message)
        self.assertIsNone(cvt_users.get_by_username(username="admin"))
