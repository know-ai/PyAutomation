import unittest
from . import assert_dict_contains_subset
from ..modules.users.users import Users, User
from ..modules.users.roles import roles, Role

USERNAME = "user1"
ROLE_NAME = "admin"
EMAIL = "jhon.doe@gmail.com"
PASSWORD = "123456"
NAME = "Jhon"
LASTNAME = "Doe"

USERNAME2 = "user2"
EMAIL2 = "jhon.doe2@gmail.com"

class TestUsers(unittest.TestCase):

    def setUp(self) -> None:
        
        self.roles = roles
        self.roles._delete_all()
        self.users = Users()
        self.users._delete_all()

        return super().setUp()

    def tearDown(self) -> None:
        delattr(self, "roles")
        delattr(self, "users")
        return super().tearDown()
    
    def test_create_role(self):
        
        admin = Role(name="admin", level=0)
        expected = {
            "name": "admin",
            "level": 0
        }
        assert_dict_contains_subset(expected, admin.serialize())
    
    def test_add_role_to_repo(self):
        
        admin = Role(name="admin", level=0)
        self.roles.add(role=admin)
        self.assertIn(admin, self.roles.roles.values())

    def test_get_role(self):
        
        admin = Role(name="admin", level=0)
        admin_id, _ = self.roles.add(role=admin)
        self.assertEqual(admin, self.roles.get(id=admin_id))

    def test_get_role_by_name(self):
        
        admin = Role(name="admin", level=0)
        self.roles.add(role=admin)
        self.assertEqual(admin, self.roles.get_by_name(name=admin.name))

    def test_get_role_names(self):
        
        roles = ["sudo", "admin", "operator"]
        for role in roles:
            _role = Role(name=role, level=0)
            self.roles.add(role=_role)

        self.assertListEqual(roles, self.roles.get_names())

    def test_put_role(self):
        
        role = Role(name="admin", level=0)
        role_id, _ = self.roles.add(role=role)
        self.roles.put(id=role_id, name="sudo")
        self.assertEqual(role.name, "sudo")

    def test_delete_role(self):
        
        roles = ["sudo", "admin", "operator"]
        for role in roles:
            _role = Role(name=role, level=0)
            role_id = self.roles.add(role=_role)
        role = self.roles.get(id=role_id)
        self.roles.delete(id=role_id)
        self.assertNotIn(role, self.roles.roles.values())

    def test_signup(self):

        role = Role(name=ROLE_NAME, level=0)
        self.roles.add(role=role)
        user, _ = self.users.signup(username=USERNAME, role_name=ROLE_NAME, email=EMAIL, password=PASSWORD, name=NAME, lastname=LASTNAME)
        self.assertIsInstance(user, User)

    def test_signup_without_email(self):
        role = Role(name=ROLE_NAME, level=0)
        self.roles.add(role=role)
        user1, msg1 = self.users.signup(
            username="noemail1", role_name=ROLE_NAME, email="", password=PASSWORD
        )
        user2, msg2 = self.users.signup(
            username="noemail2", role_name=ROLE_NAME, email=None, password=PASSWORD
        )
        self.assertIsInstance(user1, User)
        self.assertIsInstance(user2, User)
        self.assertEqual(user1.email, "")
        self.assertEqual(user2.email, "")
        self.assertIsNone(self.users.get_by_email(email=""))
        self.assertIn("created successfully", msg1)
        self.assertIn("created successfully", msg2)

    def test_signup_duplicate_username(self):
        role = Role(name=ROLE_NAME, level=0)
        self.roles.add(role=role)
        first, _ = self.users.signup(
            username=USERNAME, role_name=ROLE_NAME, email=EMAIL, password=PASSWORD
        )
        duplicate, message = self.users.signup(
            username=USERNAME, role_name=ROLE_NAME, email=EMAIL2, password=PASSWORD
        )
        self.assertIsInstance(first, User)
        self.assertIsNone(duplicate)
        self.assertIn("already exists", message)
        self.assertIn(USERNAME, message)

    def test_signup_duplicate_email(self):
        role = Role(name=ROLE_NAME, level=0)
        self.roles.add(role=role)
        first, _ = self.users.signup(
            username=USERNAME, role_name=ROLE_NAME, email=EMAIL, password=PASSWORD
        )
        duplicate, message = self.users.signup(
            username=USERNAME2, role_name=ROLE_NAME, email=EMAIL, password=PASSWORD
        )
        self.assertIsInstance(first, User)
        self.assertIsNone(duplicate)
        self.assertIn("already exists", message)
        self.assertIn(EMAIL, message)

    def test_login_logout(self):

        role = Role(name=ROLE_NAME, level=0)
        self.roles.add(role=role)
        user, _ = self.users.signup(username=USERNAME, role_name=ROLE_NAME, email=EMAIL, password=PASSWORD, name=NAME, lastname=LASTNAME)
        with self.subTest("Test Login"):
            
            self.assertTrue(self.users.login(password="123456", username="user1"))

        with self.subTest("Test Active user"):

            self.assertEqual(user, self.users.get_active_user(token=user.token))

        with self.subTest("Test Logout"):

            self.users.logout(user.token)
            self.assertIsNone(self.users.get_active_user(token=user.token))

    def test_login_fail(self):

        role = Role(name=ROLE_NAME, level=0)
        self.roles.add(role=role)
        user, _ = self.users.signup(username=USERNAME, role_name=ROLE_NAME, email=EMAIL, password=PASSWORD, name=NAME, lastname=LASTNAME)
        self.assertFalse(self.users.login(password=user.password, username="user1")[0])

    def test_get_user(self):

        role = Role(name=ROLE_NAME, level=0)
        self.roles.add(role=role)
        user, _ = self.users.signup(username=USERNAME, role_name=ROLE_NAME, email=EMAIL, password=PASSWORD, name=NAME, lastname=LASTNAME)
        self.assertEqual(user, self.users.get(identifier=user.identifier))

    def test_get_by_username(self):

        role = Role(name=ROLE_NAME, level=0)
        self.roles.add(role=role)
        user, _ = self.users.signup(username=USERNAME, role_name=ROLE_NAME, email=EMAIL, password=PASSWORD, name=NAME, lastname=LASTNAME)
        self.assertEqual(user, self.users.get_by_username(username=USERNAME))

    def test_get_by_email(self):

        role = Role(name=ROLE_NAME, level=0)
        self.roles.add(role=role)
        user, _ = self.users.signup(username=USERNAME, role_name=ROLE_NAME, email=EMAIL, password=PASSWORD, name=NAME, lastname=LASTNAME)
        self.assertEqual(user, self.users.get_by_email(email=EMAIL))

    def test_get_active_user(self):

        role = Role(name=ROLE_NAME, level=0)
        self.roles.add(role=role)
        user1, _ = self.users.signup(username=USERNAME, role_name=ROLE_NAME, email=EMAIL, password=PASSWORD, name=NAME, lastname=LASTNAME)
        self.users.signup(username=USERNAME2, role_name=ROLE_NAME, email=EMAIL2, password=PASSWORD, name=NAME, lastname=LASTNAME)
        self.users.login(password=PASSWORD, username=USERNAME)
        self.assertEqual(user1, self.users.get_active_user(token=user1.token))

    def test_get_not_active_user(self):

        role = Role(name=ROLE_NAME, level=0)
        self.roles.add(role=role)
        self.users.signup(username=USERNAME, role_name=ROLE_NAME, email=EMAIL, password=PASSWORD, name=NAME, lastname=LASTNAME)
        user2, _ = self.users.signup(username=USERNAME2, role_name=ROLE_NAME, email=EMAIL2, password=PASSWORD, name=NAME, lastname=LASTNAME)
        self.users.login(password=PASSWORD, username=USERNAME)
        self.assertIsNone(self.users.get_active_user(token=user2.token))

    def test_new_user_is_enabled(self):
        role = Role(name=ROLE_NAME, level=0)
        self.roles.add(role=role)
        user, _ = self.users.signup(
            username=USERNAME, role_name=ROLE_NAME, email=EMAIL, password=PASSWORD
        )
        self.assertTrue(user.enabled)
        self.assertTrue(user.serialize()["enabled"])

    def test_disabled_user_cannot_login_and_loses_session(self):
        role = Role(name=ROLE_NAME, level=0)
        self.roles.add(role=role)
        user, _ = self.users.signup(
            username=USERNAME, role_name=ROLE_NAME, email=EMAIL, password=PASSWORD
        )
        logged, _ = self.users.login(password=PASSWORD, username=USERNAME)
        self.assertIsNotNone(logged)
        token = user.token
        updated, message = self.users.set_enabled(USERNAME, False)
        self.assertFalse(updated.enabled)
        self.assertIn("disabled", message)
        self.assertIsNone(self.users.get_active_user(token=token))
        again, denied = self.users.login(password=PASSWORD, username=USERNAME)
        self.assertIsNone(again)
        self.assertIn("disabled", denied.lower())
        restored, _ = self.users.set_enabled(USERNAME, True)
        self.assertTrue(restored.enabled)
        back, _ = self.users.login(password=PASSWORD, username=USERNAME)
        self.assertIsNotNone(back)

    def test_disabled_token_is_rejected_before_role_acl(self):
        from ..extensions.api import Api

        role = Role(name=ROLE_NAME, level=0)
        self.roles.add(role=role)
        self.users.signup(
            username=USERNAME, role_name=ROLE_NAME, email=EMAIL, password=PASSWORD
        )
        logged, _ = self.users.login(password=PASSWORD, username=USERNAME)
        token = logged.token
        self.users.set_enabled(USERNAME, False)
        principal, err, status = Api._resolve_session_user(token)
        self.assertIsNone(principal)
        self.assertEqual(status, 403)
        self.assertEqual(err["message"], "User is disabled")
        self.assertEqual(err["code"], "USER_DISABLED")
        self.assertEqual(err["error_type"], "user_disabled")
        self.users.set_enabled(USERNAME, True)
        _, after, after_status = Api._resolve_session_user(token)
        self.assertEqual(after_status, 401)
        self.assertEqual(after["code"], "SESSION_SUPERSEDED")


class TestSetEnabledAccess(unittest.TestCase):
    def test_only_integrator_and_administrator(self):
        from ..modules.users.resources.users import actor_may_set_user_enabled

        def _user(role_name):
            return type("U", (), {"role": type("R", (), {"name": role_name})()})()

        self.assertTrue(actor_may_set_user_enabled(_user("integrator")))
        self.assertTrue(actor_may_set_user_enabled(_user("ADMIN")))
        self.assertTrue(actor_may_set_user_enabled(_user("Administrator")))
        self.assertFalse(actor_may_set_user_enabled(_user("sudo")))
        self.assertFalse(actor_may_set_user_enabled(_user("supervisor")))
        self.assertFalse(actor_may_set_user_enabled(_user("operator")))

