import unittest

from ..utils.system_user import is_system_username, system_user_path_allowed


class TestSystemUserHttpScope(unittest.TestCase):
    def test_username_match(self):
        self.assertTrue(is_system_username("system"))
        self.assertTrue(is_system_username("System"))
        self.assertFalse(is_system_username("admin"))
        self.assertFalse(is_system_username(None))

    def test_allows_user_management(self):
        self.assertTrue(system_user_path_allowed("/api/users/"))
        self.assertTrue(system_user_path_allowed("/api/users"))
        self.assertTrue(system_user_path_allowed("/api/users/update_role"))
        self.assertTrue(system_user_path_allowed("/api/users/logout"))
        self.assertTrue(system_user_path_allowed("/api/users/roles/"))
        self.assertTrue(system_user_path_allowed("/api/users/roles/add"))
        self.assertTrue(system_user_path_allowed("/api/health/db"))
        self.assertTrue(system_user_path_allowed("/api/healthcheck/"))
        self.assertTrue(system_user_path_allowed("/api/healthcheck/ready"))
        self.assertTrue(system_user_path_allowed("/api/healthcheck/detection"))
        self.assertTrue(system_user_path_allowed("/api/system/timezone"))
        self.assertTrue(system_user_path_allowed("/api/authz/me"))
        self.assertTrue(system_user_path_allowed("/api/authz/grants"))
        self.assertTrue(system_user_path_allowed("/api/users/create_tpt"))

    def test_denies_operational_and_tpt(self):
        self.assertFalse(system_user_path_allowed("/api/tags/"))
        self.assertFalse(system_user_path_allowed("/api/alarms/"))
        self.assertFalse(system_user_path_allowed("/api/machines/"))
        self.assertFalse(system_user_path_allowed("/api/events/filter_by"))
        self.assertFalse(system_user_path_allowed("/api/settings/"))
        self.assertFalse(system_user_path_allowed("/api/database/"))
        self.assertFalse(system_user_path_allowed("/api/opcua/clients/"))
