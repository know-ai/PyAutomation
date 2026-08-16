import unittest
from unittest.mock import MagicMock, patch


class TestUserSessionAuditHelper(unittest.TestCase):
    def test_unknown_action_is_skipped(self):
        from ..utils.user_session_audit import record_user_session_event

        self.assertFalse(record_user_session_event(action="NOT_A_THING"))

    def test_login_uses_the_authenticated_user(self):
        from ..utils import user_session_audit

        user = MagicMock()
        user.username = "operator1"
        with patch.object(user_session_audit, "persist_system_event", return_value=True) as persist:
            self.assertTrue(
                user_session_audit.record_user_session_event(action="LOGIN", user=user)
            )
        kwargs = persist.call_args.kwargs
        self.assertEqual(kwargs["message"], "User logged in")
        self.assertEqual(kwargs["classification"], "Security")
        self.assertEqual(kwargs["user"], user)
        self.assertIn("username=operator1", kwargs["description"])
        self.assertIn("method=password", kwargs["description"])

    def test_login_failed_does_not_require_a_user_object(self):
        from ..utils import user_session_audit

        system = MagicMock()
        system.username = "system"
        with patch.object(user_session_audit, "get_system_user", return_value=system):
            with patch.object(user_session_audit, "persist_system_event", return_value=True) as persist:
                self.assertTrue(
                    user_session_audit.record_user_session_event(
                        action="LOGIN_FAILED",
                        username="ghost",
                        extra="reason=invalid_credentials",
                    )
                )
        kwargs = persist.call_args.kwargs
        self.assertEqual(kwargs["message"], "User login failed")
        self.assertEqual(kwargs["user"], system)
        self.assertIn("username=ghost", kwargs["description"])
        self.assertIn("reason=invalid_credentials", kwargs["description"])
        self.assertNotIn("password", kwargs["description"].lower())

    def test_password_change_records_actor_and_target(self):
        from ..utils import user_session_audit

        actor = MagicMock()
        actor.username = "admin"
        target = MagicMock()
        target.username = "operator1"
        with patch.object(user_session_audit, "persist_system_event", return_value=True) as persist:
            user_session_audit.record_user_session_event(
                action="PASSWORD_CHANGED",
                user=target,
                actor=actor,
            )
        kwargs = persist.call_args.kwargs
        self.assertIn("username=operator1", kwargs["description"])
        self.assertIn("actor=admin", kwargs["description"])

    def test_session_superseded_logout_keeps_reason(self):
        from ..utils import user_session_audit

        user = MagicMock()
        user.username = "operator1"
        with patch.object(user_session_audit, "persist_system_event", return_value=True) as persist:
            user_session_audit.record_user_session_event(
                action="LOGOUT",
                user=user,
                extra="reason=session_superseded",
            )
        kwargs = persist.call_args.kwargs
        self.assertEqual(kwargs["message"], "User logged out")
        self.assertIn("reason=session_superseded", kwargs["description"])
        self.assertEqual(kwargs["user"], user)

    def test_never_raises(self):
        from ..utils import user_session_audit

        with patch.object(user_session_audit, "persist_system_event", side_effect=RuntimeError("db")):
            self.assertFalse(
                user_session_audit.record_user_session_event(action="LOGOUT", username="x")
            )
