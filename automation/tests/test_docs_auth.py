# -*- coding: utf-8 -*-
import os
import unittest

from automation import server
from automation.extensions.docs_auth import authenticate_docs_user
from automation.modules.users.roles import Role, roles as cvt_roles
from automation.modules.users.users import Users as CVTUsers


class TestDocsAuth(unittest.TestCase):
    def setUp(self):
        os.environ["DOCS_SYSTEM_PASSWORD"] = "docs-system-secret"
        os.environ["DOCS_RATE_LIMIT"] = "5 per minute"
        self.client = server.test_client()
        cvt_roles._delete_all()
        CVTUsers()._delete_all()
        integrator = Role(name="integrator", level=0, identifier="roleint0")
        admin = Role(name="admin", level=1, identifier="roleadm1")
        cvt_roles.add(integrator)
        cvt_roles.add(admin)
        user, _ = CVTUsers().signup(
            username="integrator_docs",
            role_name="integrator",
            email="integrator@example.com",
            password="integrator-pass",
            encode_password=True,
        )
        self.assertIsNotNone(user)
        CVTUsers().signup(
            username="admin_docs",
            role_name="admin",
            email="admin@example.com",
            password="admin-pass",
            encode_password=True,
        )

    def tearDown(self):
        CVTUsers()._delete_all()
        cvt_roles._delete_all()
        from automation.extensions import docs_auth

        docs_auth._blocked_until.clear()

    def test_authenticate_system_user(self):
        user = authenticate_docs_user("system", "docs-system-secret")
        self.assertIsNotNone(user)
        self.assertEqual(user.username, "system")

    def test_authenticate_integrator(self):
        user = authenticate_docs_user("integrator_docs", "integrator-pass")
        self.assertIsNotNone(user)
        self.assertEqual(user.username, "integrator_docs")

    def test_reject_admin(self):
        self.assertIsNone(authenticate_docs_user("admin_docs", "admin-pass"))

    def test_docs_redirects_to_login(self):
        response = self.client.get("/api/docs", follow_redirects=False)
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login-docs", response.headers.get("Location", ""))

    def test_integrator_can_access_docs(self):
        with self.client.session_transaction() as sess:
            sess["_user_id"] = "integrator_docs"
            sess["_fresh"] = True
        response = self.client.get("/api/docs", follow_redirects=False)
        self.assertIn(response.status_code, {200, 308})

    def test_login_docs_success(self):
        response = self.client.post(
            "/login-docs",
            data={"username": "integrator_docs", "password": "integrator-pass"},
            follow_redirects=False,
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn("/api/docs", response.headers.get("Location", ""))

    def test_login_docs_rejects_admin(self):
        response = self.client.post(
            "/login-docs",
            data={"username": "admin_docs", "password": "admin-pass"},
            follow_redirects=False,
        )
        self.assertEqual(response.status_code, 401)
        self.assertIn(b"Credenciales", response.data)

    def test_logout_docs(self):
        with self.client.session_transaction() as sess:
            sess["_user_id"] = "integrator_docs"
            sess["_fresh"] = True
        response = self.client.get("/logout-docs", follow_redirects=False)
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login-docs", response.headers.get("Location", ""))

    def test_login_rate_limit(self):
        for _ in range(5):
            self.client.post(
                "/login-docs",
                data={"username": "admin_docs", "password": "wrong"},
            )
        response = self.client.post(
            "/login-docs",
            data={"username": "admin_docs", "password": "wrong"},
        )
        self.assertEqual(response.status_code, 429)


if __name__ == "__main__":
    unittest.main()
