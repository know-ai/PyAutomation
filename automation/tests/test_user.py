import unittest
from automation import Users, Roles, Role
from automation.modules.users.users import User

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
        
        self.roles = Roles()
        self.roles._delete_all()
        self.users = Users()

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
        self.assertDictEqual(expected, admin.serialize())
    
    def test_add_role_to_repo(self):
        
        admin = Role(name="admin", level=0)
        self.roles.add(role=admin)
        self.assertIn(admin, self.roles.roles.values())

    def test_get_role(self):
        
        admin = Role(name="admin", level=0)
        admin_id = self.roles.add(role=admin)
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
        role_id = self.roles.add(role=role)
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
        self.assertFalse(self.users.login(password=user.password, username="user1"))

    def test_get_user(self):

        role = Role(name=ROLE_NAME, level=0)
        self.roles.add(role=role)
        user, _ = self.users.signup(username=USERNAME, role_name=ROLE_NAME, email=EMAIL, password=PASSWORD, name=NAME, lastname=LASTNAME)
        self.assertEqual(user, self.users.get(id=user.id))

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

