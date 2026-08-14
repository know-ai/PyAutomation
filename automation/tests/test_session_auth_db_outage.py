import unittest
from unittest.mock import MagicMock, patch

from ..extensions.api import Api
from ..modules.users.users import users as cvt_users, User
from ..modules.users.roles import roles as cvt_roles, Role


class TestSessionAuthDuringDbOutage(unittest.TestCase):
    def setUp(self) -> None:
        cvt_users._delete_all()
        cvt_roles._delete_all()
        role = Role(name="operator", level=2, identifier="roleop")
        cvt_roles.add(role)
        user, _ = cvt_users.signup(
            username="op_session",
            role_name="operator",
            email="op_session@example.com",
            password="secret",
            encode_password=True,
        )
        self.assertIsNotNone(user)
        logged, _ = cvt_users.login(password="secret", username="op_session")
        self.assertIsNotNone(logged)
        self.token = logged.token
        self.user = logged

    def tearDown(self) -> None:
        cvt_users._delete_all()
        cvt_roles._delete_all()

    def test_memory_session_survives_db_marked_down(self):
        fake_app = MagicMock()
        fake_app.is_db_connected.return_value = False
        with patch("automation.PyAutomation", return_value=fake_app):
            user, err, status = Api._resolve_session_user(self.token)
        self.assertIsNone(err)
        self.assertIsNone(status)
        self.assertIsNotNone(user)
        self.assertEqual(user.username, "op_session")

    def test_missing_memory_session_with_db_down_is_503_not_invalid_token(self):
        cvt_users.active_users.pop(self.token, None)
        fake_app = MagicMock()
        fake_app.is_db_connected.return_value = False
        with patch("automation.PyAutomation", return_value=fake_app):
            user, err, status = Api._resolve_session_user(self.token)
        self.assertIsNone(user)
        self.assertEqual(status, 503)
        self.assertEqual(err["code"], "AUTH_BACKEND_UNAVAILABLE")

    def test_login_revokes_previous_session(self):
        old_token = self.token
        user2, _ = cvt_users.login(password="secret", username="op_session")
        self.assertIsNotNone(user2)
        self.assertNotEqual(old_token, user2.token)
        self.assertTrue(cvt_users.is_revoked_token(old_token))
        self.assertIsNone(cvt_users.get_active_user(token=old_token))
        fake_app = MagicMock()
        fake_app.is_db_connected.return_value = True
        with patch("automation.PyAutomation", return_value=fake_app), patch(
            "automation.extensions.api.Users.get_or_none", return_value=None
        ):
            user, err, status = Api._resolve_session_user(old_token)
        self.assertIsNone(user)
        self.assertEqual(status, 401)
        self.assertEqual(err["code"], "SESSION_SUPERSEDED")

    def test_activate_session_from_db_record(self):
        cvt_users.active_users.pop(self.token, None)
        db_user = MagicMock()
        db_user.username = "op_session"
        db_user.token = self.token
        restored = cvt_users.activate_session_from_db_record(db_user, token=self.token)
        self.assertIsNotNone(restored)
        self.assertIs(cvt_users.get_active_user(token=self.token), self.user)

    def test_key_missing(self):
        user, err, status = Api._resolve_session_user("")
        self.assertIsNone(user)
        self.assertEqual(status, 401)
        self.assertEqual(err["code"], "AUTH_KEY_MISSING")
