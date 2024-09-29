import unittest
from automation.modules.users.users import Users, User
from automation.modules.users.roles import roles, Role

USERNAME = "user1"
ROLE_NAME = "admin"
EMAIL = "jhon.doe@gmail.com"
PASSWORD = "123456"
NAME = "Jhon"
LASTNAME = "Doe"

USERNAME2 = "user2"
EMAIL2 = "jhon.doe2@gmail.com"

class TestCore(unittest.TestCase):

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