# -*- coding: utf-8 -*-
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import jwt

from automation import server
from automation.authz.catalog import HMI_VIEW_KEYS
from automation.authz.engine import evaluate, permissions_for
from automation.authz.roles_policy import validate_role_assignment
from automation.authz.seed import default_allows, seed_default_grants
from automation.authz.store import clear as clear_grants
from automation.authz.store import put_grant
from automation.extensions.api import Api
from automation.modules.users.roles import Role
from automation.modules.users.roles import roles as cvt_roles
from automation.modules.users.users import users as cvt_users


class _Role:
    def __init__(self, name, identifier, level=1):
        self.name = name
        self.identifier = identifier
        self.level = level


class _User:
    def __init__(self, username, role, identifier="user0001"):
        self.username = username
        self.role = role
        self.identifier = identifier


class TestAuthzEngine(unittest.TestCase):
    def setUp(self):
        clear_grants()
        self.role = _Role("operator", "roleop01", level=10)
        self.user = _User("maria", self.role, identifier="user0001")

    def tearDown(self):
        clear_grants()

    def test_fail_closed_without_grants(self):
        self.assertFalse(evaluate(self.user, "hmi:view.tags.definitions", "view"))
        self.assertFalse(evaluate(None, "hmi:view.tags.definitions", "view"))

    def test_precedence_user_deny_beats_role_allow(self):
        put_grant("role", self.role.identifier, "hmi:view.machines.detailed", "view", "allow")
        put_grant("user", self.user.identifier, "hmi:view.machines.detailed", "view", "deny")
        self.assertFalse(evaluate(self.user, "hmi:view.machines.detailed", "view"))

    def test_precedence_user_allow_beats_role_deny(self):
        put_grant("role", self.role.identifier, "hmi:view.tags.definitions", "view", "deny")
        put_grant("user", self.user.identifier, "hmi:view.tags.definitions", "view", "allow")
        self.assertTrue(evaluate(self.user, "hmi:view.tags.definitions", "view"))

    def test_role_deny_beats_missing_user(self):
        put_grant("role", self.role.identifier, "hmi:view.settings", "view", "deny")
        self.assertFalse(evaluate(self.user, "hmi:view.settings", "view"))

    def test_role_allow(self):
        put_grant("role", self.role.identifier, "hmi:view.tags.definitions", "view", "allow")
        self.assertTrue(evaluate(self.user, "hmi:view.tags.definitions", "view"))
        self.assertFalse(evaluate(self.user, "hmi:view.tags.definitions", "use"))


class TestAuthzSeedMatrix(unittest.TestCase):
    def test_integrator_allows_everything(self):
        for key in HMI_VIEW_KEYS:
            self.assertTrue(default_allows("integrator", key, "view"), key)
            self.assertTrue(default_allows("integrator", key, "use"), key)
        self.assertTrue(
            default_allows("integrator", "rest:POST /api/tags/write_value", "use")
        )
        self.assertTrue(
            default_allows("integrator", "rest:PUT /api/machines/<machine_name>/attributes", "use")
        )

    def test_guest_cannot_write_tags(self):
        self.assertFalse(default_allows("guest", "rest:POST /api/tags/write_value", "use"))
        self.assertFalse(default_allows("guest", "hmi:view.tags.definitions", "view"))
        self.assertTrue(default_allows("guest", "hmi:view.real-time-trends", "view"))
        self.assertTrue(default_allows("guest", "hmi:view.machines.summary", "view"))
        self.assertTrue(default_allows("guest", "hmi:view.machines.detailed", "view"))
        self.assertFalse(default_allows("guest", "hmi:view.machines.detailed", "use"))
        self.assertTrue(default_allows("guest", "rest:GET /api/machines/", "view"))
        self.assertTrue(default_allows("guest", "rest:GET /api/tags/", "view"))

    def test_auditor_inherits_guest_and_audit_views(self):
        self.assertTrue(default_allows("auditor", "hmi:view.machines.detailed", "view"))
        self.assertTrue(default_allows("auditor", "hmi:view.alarms.summary", "view"))
        self.assertTrue(default_allows("auditor", "hmi:view.events", "view"))
        self.assertTrue(default_allows("auditor", "hmi:view.tags.datalogger", "view"))
        self.assertTrue(default_allows("auditor", "hmi:view.tags.trends", "view"))
        self.assertFalse(default_allows("auditor", "hmi:view.alarms.definitions", "view"))
        self.assertTrue(default_allows("auditor", "rest:GET /api/events/", "view"))
        self.assertTrue(default_allows("auditor", "rest:GET /api/logs/", "view"))

    def test_operator_inherits_auditor_and_tags_views(self):
        self.assertTrue(default_allows("operator", "hmi:view.tags.definitions", "view"))
        self.assertTrue(default_allows("operator", "hmi:view.alarms.definitions", "view"))
        self.assertFalse(default_allows("operator", "hmi:view.communications.clients", "view"))
        self.assertFalse(default_allows("operator", "hmi:view.tags.definitions", "use"))

    def test_supervisor_inherits_operator_and_ops_views(self):
        self.assertTrue(default_allows("supervisor", "hmi:view.communications.clients", "view"))
        self.assertTrue(default_allows("supervisor", "hmi:view.performance", "view"))
        self.assertFalse(default_allows("supervisor", "hmi:view.settings", "view"))
        self.assertTrue(default_allows("supervisor", "hmi:view.tags.definitions", "use"))
        self.assertTrue(default_allows("supervisor", "rest:GET /api/opcua/clients", "view"))
        self.assertTrue(default_allows("supervisor", "rest:POST /api/opcua/clients/add", "use"))

    def test_custom_role_inherits_guest_matrix(self):
        self.assertFalse(default_allows("plant_viewer", "hmi:view.tags.definitions", "view"))
        self.assertEqual(
            default_allows("plant_viewer", "rest:GET /api/tags/", "view"),
            default_allows("guest", "rest:GET /api/tags/", "view"),
        )
        self.assertEqual(
            default_allows("plant_viewer", "hmi:view.machines.detailed", "view"),
            default_allows("guest", "hmi:view.machines.detailed", "view"),
        )

    def test_operator_cannot_put_machines(self):
        self.assertFalse(
            default_allows("operator", "rest:PUT /api/machines/<machine_name>/attributes", "use")
        )
        self.assertTrue(default_allows("operator", "rest:GET /api/tags/", "view"))
        self.assertTrue(
            default_allows("operator", "rest:POST /api/alarms/acknowledge/<alarm_name>", "use")
        )
        self.assertFalse(default_allows("operator", "rest:POST /api/alarms/add", "use"))

    def test_auditor_no_settings(self):
        self.assertFalse(default_allows("auditor", "hmi:view.settings", "view"))
        self.assertFalse(default_allows("auditor", "rest:GET /api/settings/", "view"))
        self.assertTrue(default_allows("auditor", "hmi:view.events", "view"))
        self.assertFalse(default_allows("auditor", "hmi:view.events", "use"))

    def test_admin_has_settings_not_administration(self):
        self.assertTrue(default_allows("admin", "hmi:view.settings", "view"))
        self.assertFalse(default_allows("admin", "hmi:view.user-management", "view"))
        self.assertFalse(default_allows("admin", "hmi:view.authz", "view"))
        self.assertFalse(default_allows("admin", "hmi:view.settings", "use"))
        self.assertTrue(default_allows("admin", "hmi:view.tags.definitions", "view"))
        self.assertTrue(default_allows("admin", "hmi:view.tags.definitions", "use"))
        self.assertTrue(default_allows("admin", "rest:GET /api/settings/", "view"))
        self.assertTrue(default_allows("admin", "rest:PUT /api/settings/", "use"))
        self.assertFalse(default_allows("admin", "rest:GET /api/database/config", "view"))
        self.assertFalse(default_allows("admin", "rest:POST /api/database/connect", "use"))

    def test_csv_export_capability_by_role(self):
        cap = "hmi:capability.csv-export"
        self.assertFalse(default_allows("guest", cap, "use"))
        self.assertFalse(default_allows("operator", cap, "use"))
        self.assertTrue(default_allows("auditor", cap, "use"))
        self.assertTrue(default_allows("supervisor", cap, "use"))
        self.assertTrue(default_allows("admin", cap, "use"))
        self.assertTrue(default_allows("integrator", cap, "use"))


class TestViewRestBundles(unittest.TestCase):
    def setUp(self):
        clear_grants()
        self.role = _Role("auditor", "roleaud1", 100)
        self.user = _User("auditor1", self.role, identifier="aud00001")

    def tearDown(self):
        clear_grants()

    def test_hmi_view_implies_read_post_filter(self):
        put_grant("role", self.role.identifier, "hmi:view.events", "view", "allow")
        self.assertTrue(evaluate(self.user, "rest:POST /api/events/filter_by", "use"))
        self.assertTrue(evaluate(self.user, "rest:GET /api/users/", "view"))
        self.assertFalse(evaluate(self.user, "rest:POST /api/logs/add", "use"))

    def test_hmi_view_implies_alarms_summary_filter(self):
        put_grant("role", self.role.identifier, "hmi:view.alarms.summary", "view", "allow")
        self.assertTrue(evaluate(self.user, "rest:POST /api/alarms/summary/filter_by", "use"))

    def test_hmi_view_implies_tags_trends_query(self):
        put_grant("role", self.role.identifier, "hmi:view.tags.trends", "view", "allow")
        self.assertTrue(evaluate(self.user, "rest:POST /api/tags/query_trends", "use"))

    def test_hmi_view_implies_tags_definitions_opc_browse(self):
        put_grant("role", self.role.identifier, "hmi:view.tags.definitions", "view", "allow")
        self.assertTrue(
            evaluate(self.user, "rest:GET /api/opcua/clients/tree/<client_name>", "view")
        )
        self.assertTrue(
            evaluate(self.user, "rest:GET /api/opcua/clients/variables/<client_name>", "view")
        )
        self.assertTrue(
            evaluate(self.user, "rest:POST /api/opcua/clients/attrs/<client_name>", "use")
        )

    def test_hmi_view_implies_tags_definitions_write_with_use(self):
        role = _Role("supervisor", "rolesup1", 50)
        user = _User("sup1", role, identifier="sup00001")
        put_grant("role", role.identifier, "hmi:view.tags.definitions", "view", "allow")
        put_grant("role", role.identifier, "hmi:view.tags.definitions", "use", "allow")
        self.assertTrue(evaluate(user, "rest:POST /api/tags/update", "use"))
        self.assertTrue(evaluate(user, "rest:POST /api/tags/add", "use"))

    def test_operator_view_only_cannot_update_tags(self):
        role = _Role("operator", "roleop1", 200)
        user = _User("op1", role, identifier="op000001")
        put_grant("role", role.identifier, "hmi:view.tags.definitions", "view", "allow")
        self.assertTrue(evaluate(user, "rest:GET /api/opcua/clients/variables/<client_name>", "view"))
        self.assertFalse(evaluate(user, "rest:POST /api/tags/update", "use"))

    def test_explicit_rest_deny_beats_view_bundle(self):
        put_grant("role", self.role.identifier, "hmi:view.events", "view", "allow")
        put_grant("role", self.role.identifier, "rest:POST /api/events/filter_by", "use", "deny")
        self.assertFalse(evaluate(self.user, "rest:POST /api/events/filter_by", "use"))

    def test_permissions_for_includes_implied_rest(self):
        put_grant("role", self.role.identifier, "hmi:view.events", "view", "allow")
        perms = permissions_for(self.user, server)
        self.assertIn("rest:POST /api/events/filter_by", perms["rest"])
        self.assertIn("use", perms["rest"]["rest:POST /api/events/filter_by"])


class TestAuthzNewRoleSeed(unittest.TestCase):
    def setUp(self):
        clear_grants()
        cvt_roles._delete_all()
        cvt_roles.add(Role(name="guest", level=256, identifier="roleguest"))
        cvt_roles.add(Role(name="custom_ops", level=300, identifier="rolecust"))

    def tearDown(self):
        clear_grants()
        cvt_roles._delete_all()

    def test_seed_grants_for_new_role_clones_guest_allow(self):
        from automation.authz.engine import evaluate
        from automation.authz.seed import seed_grants_for_new_role

        put_grant("role", "roleguest", "hmi:view.events", "view", "allow")
        created = seed_grants_for_new_role("custom_ops", "rolecust", server, persist=False)
        self.assertGreaterEqual(created, 1)
        user = _User("bob", _Role("custom_ops", "rolecust", 300), identifier="usr0001")
        self.assertTrue(evaluate(user, "hmi:view.events", "view"))
        self.assertFalse(evaluate(user, "hmi:view.tags.definitions", "view"))


class TestAuthzRestSeed(unittest.TestCase):
    @patch("automation.authz.seed._existing_tuple_set", return_value=set())
    @patch(
        "automation.authz.seed._role_rows",
        return_value=[{"name": "integrator", "identifier": "roleint0"}],
    )
    def test_seed_default_grants_includes_rest_for_integrator(self, _roles, _existing):
        clear_grants()
        try:
            created = seed_default_grants(server, persist=False)
            perms = permissions_for(
                _User("integrator", _Role("integrator", "roleint0", 0), identifier="int00001"),
                server,
            )
            rest = perms.get("rest") or {}
            self.assertGreater(created, 0)
            self.assertGreater(len(rest), 0)
            self.assertIn("rest:GET /api/opcua/clients/", rest)
            self.assertIn("use", rest.get("rest:POST /api/opcua/clients/add", []))
        finally:
            clear_grants()

class TestRoleAssignmentPolicy(unittest.TestCase):
    def setUp(self):
        self.system = _User("system", _Role("sudo", "rolesudo", 0), identifier="sys00001")
        self.admin = _User("alice", _Role("admin", "roleadm1", 1), identifier="adm00001")
        self.operator = _User("bob", _Role("operator", "roleop01", 10), identifier="op000001")

    def test_cannot_change_system(self):
        denied = validate_role_assignment(self.admin, self.system, "admin")
        self.assertIsNotNone(denied)
        self.assertEqual(denied[1], 403)

    def test_cannot_assign_sudo(self):
        denied = validate_role_assignment(self.system, self.operator, "sudo")
        self.assertIsNotNone(denied)
        self.assertEqual(denied[1], 403)

    def test_only_system_assigns_integrator(self):
        denied = validate_role_assignment(self.admin, self.operator, "integrator")
        self.assertIsNotNone(denied)
        self.assertEqual(denied[1], 403)
        allowed = validate_role_assignment(self.system, self.operator, "integrator")
        self.assertIsNone(allowed)

    def test_admin_can_assign_operator(self):
        self.assertIsNone(validate_role_assignment(self.admin, self.operator, "supervisor"))


class TestAuthzHttp(unittest.TestCase):
    def setUp(self):
        clear_grants()
        cvt_users._delete_all()
        cvt_roles._delete_all()
        guest_role = Role(name="guest", level=256, identifier="roleguest")
        cvt_roles.add(guest_role)
        user, _ = cvt_users.signup(
            username="guest_acl",
            role_name="guest",
            email="guest_acl@example.com",
            password="secret",
            encode_password=True,
        )
        self.assertIsNotNone(user)
        logged, _ = cvt_users.login(password="secret", username="guest_acl")
        self.token = logged.token
        self.user = logged
        self.client = server.test_client()

    def tearDown(self):
        cvt_users._delete_all()
        cvt_roles._delete_all()
        clear_grants()

    def test_database_config_requires_token(self):
        response = self.client.get("/api/database/config")
        self.assertEqual(response.status_code, 401)

    def test_database_connect_requires_token(self):
        response = self.client.post("/api/database/connect", json={"dbtype": "postgresql"})
        self.assertEqual(response.status_code, 401)

    def test_guest_cannot_write_tags(self):
        response = self.client.post(
            "/api/tags/write_value",
            json={"tag": "x", "value": 1},
            headers={"X-API-KEY": self.token},
        )
        self.assertEqual(response.status_code, 403)
        payload = response.get_json() or {}
        self.assertEqual(payload.get("code"), "AUTHZ_DENIED")

    def test_authz_me_matches_engine(self):
        put_grant("role", self.user.role.identifier, "hmi:view.events", "view", "allow")
        response = self.client.get("/api/authz/me", headers={"X-API-KEY": self.token})
        self.assertEqual(response.status_code, 200)
        body = response.get_json() or {}
        expected = permissions_for(self.user, server)
        self.assertEqual(body.get("views"), expected.get("views"))
        self.assertTrue(evaluate(self.user, "hmi:view.events", "view"))
        self.assertIn("hmi:view.events", body.get("views") or {})

    def test_health_ping_stays_public(self):
        response = self.client.get("/api/health/ping")
        self.assertEqual(response.status_code, 200)


class TestTptAuth(unittest.TestCase):
    def setUp(self):
        cvt_roles._delete_all()
        cvt_roles.add(Role(name="operator", level=10, identifier="roleop01"))
        self.secret = server.config["AUTOMATION_APP_SECRET_KEY"]

    def tearDown(self):
        cvt_roles._delete_all()

    def test_tpt_without_exp_is_rejected(self):
        token = jwt.encode({"role": "operator"}, self.secret, algorithm="HS256")
        self.assertIsNone(Api.decode_tpt(token))
        user, err, status = Api._resolve_session_user(token)
        self.assertIsNone(user)
        self.assertEqual(status, 401)

    def test_tpt_with_role_binds_principal(self):
        exp = int((datetime.now(timezone.utc) + timedelta(hours=1)).timestamp())
        token = jwt.encode({"role": "operator", "exp": exp}, self.secret, algorithm="HS256")
        user, err, status = Api._resolve_session_user(token)
        self.assertIsNone(err)
        self.assertIsNone(status)
        self.assertIsNotNone(user)
        self.assertEqual(user.role.name.lower(), "operator")
        self.assertTrue(str(user.username).startswith("tpt:"))

    def test_expired_tpt_is_rejected(self):
        exp = int((datetime.now(timezone.utc) - timedelta(hours=1)).timestamp())
        token = jwt.encode({"role": "operator", "exp": exp}, self.secret, algorithm="HS256")
        self.assertIsNone(Api.decode_tpt(token))
