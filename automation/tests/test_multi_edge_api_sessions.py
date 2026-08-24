# -*- coding: utf-8 -*-
"""Sesiones API concurrentes por edge (historiador PostgreSQL compartido)."""
from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from peewee import SqliteDatabase

from automation.dbmodels.core import proxy
from automation.dbmodels.user_api_sessions import UserApiSession
from automation.extensions.api import Api
from automation.modules.users.users import users as cvt_users, User
from automation.modules.users.roles import roles as cvt_roles, Role


class TestMultiEdgeApiSessions(unittest.TestCase):
    def setUp(self) -> None:
        self.db = SqliteDatabase(":memory:")
        proxy.initialize(self.db)
        self.db.create_tables([UserApiSession])
        cvt_users._delete_all()
        cvt_roles._delete_all()
        role = Role(name="operator", level=2, identifier="roleop")
        cvt_roles.add(role)
        user, _ = cvt_users.signup(
            username="op_edge",
            role_name="operator",
            email="op_edge@example.com",
            password="secret",
            encode_password=True,
        )
        self.assertIsNotNone(user)
        self.user = user

        self.node_patcher = patch(
            "automation.utils.user_api_session_store._multi_edge_enabled",
            return_value=True,
        )
        self.identity_patcher = patch(
            "automation.utils.user_api_session_store._node_identity",
            side_effect=[("edge-linea1", "Linea1"), ("edge-linea2", "Linea2")],
        )
        self.db_patcher = patch(
            "automation.utils.user_api_session_store._get_db",
            return_value=self.db,
        )
        self.close_patcher = patch(
            "automation.utils.user_api_session_store._close_historian_socket"
        )
        self.node_patcher.start()
        self.identity_patcher.start()
        self.db_patcher.start()
        self.close_patcher.start()

        from automation.utils.user_api_session_store import register_api_session

        self.register = register_api_session

    def tearDown(self) -> None:
        self.close_patcher.stop()
        self.db_patcher.stop()
        self.identity_patcher.stop()
        self.node_patcher.stop()
        self.db.drop_tables([UserApiSession])
        self.db.close()
        cvt_users._delete_all()
        cvt_roles._delete_all()

    def test_two_edges_keep_distinct_tokens(self):
        token_a = "token-edge-a"
        token_b = "token-edge-b"
        self.assertTrue(self.register(token=token_a, username="op_edge"))
        self.assertTrue(self.register(token=token_b, username="op_edge"))
        self.assertEqual(UserApiSession.select().count(), 2)

        fake_app = MagicMock()
        fake_app.is_db_connected.return_value = True
        db_user = MagicMock()
        db_user.username = "op_edge"
        db_user.token = token_b

        cvt_users.active_users.clear()
        with patch("automation.PyAutomation", return_value=fake_app), patch(
            "automation.extensions.api.Users.get_or_none", return_value=db_user
        ):
            user_a, err_a, status_a = Api._resolve_session_user(token_a)
            self.assertIsNone(err_a)
            self.assertIsNone(status_a)
            self.assertIsNotNone(user_a)
            self.assertEqual(user_a.username, "op_edge")

    def test_same_edge_login_replaces_previous_token(self):
        token_old = "token-old"
        token_new = "token-new"
        self.identity_patcher.stop()
        self.identity_patcher = patch(
            "automation.utils.user_api_session_store._node_identity",
            return_value=("edge-linea2", "Linea2"),
        )
        self.identity_patcher.start()
        self.assertTrue(self.register(token=token_old, username="op_edge"))
        self.assertTrue(self.register(token=token_new, username="op_edge"))
        tokens = [row.token for row in UserApiSession.select()]
        self.assertEqual(tokens, [token_new])


    def test_login_on_edge_b_does_not_clear_edge_a_token_row(self):
        token_a = "token-edge-a"
        token_b = "token-edge-b"
        self.assertTrue(self.register(token=token_a, username="op_edge"))
        self.assertTrue(self.register(token=token_b, username="op_edge"))
        self.assertEqual(UserApiSession.select().count(), 2)

        rows = {
            row.node_id: row.token
            for row in UserApiSession.select().where(UserApiSession.username == "op_edge")
        }
        self.assertEqual(rows.get("edge-linea1"), token_a)
        self.assertEqual(rows.get("edge-linea2"), token_b)

    def test_rebind_restores_both_edge_tokens(self):
        token_a = "token-edge-a"
        token_b = "token-edge-b"
        self.register(token=token_a, username="op_edge")
        self.register(token=token_b, username="op_edge")
        cvt_users.active_users.clear()

        with patch(
            "automation.utils.user_api_session_store.multi_edge_sessions_enabled",
            return_value=True,
        ), patch(
            "automation.utils.user_api_session_store.list_api_sessions",
            return_value=[(token_a, "op_edge"), (token_b, "op_edge")],
        ):
            restored = cvt_users.rebind_sessions_from_db_tokens()

        self.assertEqual(restored, 2)
        self.assertIn(token_a, cvt_users.active_users)
        self.assertIn(token_b, cvt_users.active_users)


if __name__ == "__main__":
    unittest.main()
