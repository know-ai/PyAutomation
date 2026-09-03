# -*- coding: utf-8 -*-
import unittest

from automation import server
from automation.authz.app_hooks import (
    extra_rest_keys,
    register_bootstrap_hook,
    register_rest_resource_keys,
    run_bootstrap_hooks,
)
from automation.authz.catalog import collect_rest_keys
from automation.authz.bootstrap import bootstrap_authz


class TestAuthzAppHooks(unittest.TestCase):
    def tearDown(self):
        from automation.authz import app_hooks as mod

        mod._hooks.clear()
        mod._extra_rest_keys.clear()

    def test_register_rest_resource_keys(self):
        register_rest_resource_keys(["rest:GET /api/custom/ping"])
        self.assertIn("rest:GET /api/custom/ping", collect_rest_keys(server))

    def test_bootstrap_hook_mounts_routes_before_seed(self):
        seen: list[str] = []

        def _hook(app):
            seen.append("hook")
            register_rest_resource_keys(["rest:POST /api/host/only"])

        register_bootstrap_hook(_hook)
        with server.app_context():
            bootstrap_authz(server)
        self.assertEqual(seen, ["hook"])
        self.assertIn("rest:POST /api/host/only", extra_rest_keys())


if __name__ == "__main__":
    unittest.main()
