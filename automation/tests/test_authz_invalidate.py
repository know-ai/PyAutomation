# -*- coding: utf-8 -*-
"""CA-REDIS: ACL RAM cache + Redis/PG invalidation bus (grants never stored in Redis)."""
from __future__ import annotations

import json
import time
import unittest
from unittest.mock import MagicMock, patch

from automation.authz.engine import evaluate
from automation.authz.invalidate import (
    PG_CHANNEL,
    REDIS_CHANNEL,
    apply_authz_invalidate,
    notify_authz_invalidated,
    parse_authz_payload,
)
from automation.authz.store import (
    cache_version,
    clear,
    lookup,
    maybe_periodic_reload,
    put_grant,
    reload_cache,
)


class _Role:
    def __init__(self, name, identifier):
        self.name = name
        self.identifier = identifier


class _User:
    def __init__(self, username, role, identifier="user0001"):
        self.username = username
        self.role = role
        self.identifier = identifier


class TestAuthzPayload(unittest.TestCase):
    def test_parse_json_version_and_origin(self):
        version, origin = parse_authz_payload('{"version": 99, "origin": "edge-a"}')
        self.assertEqual(version, 99)
        self.assertEqual(origin, "edge-a")

    def test_parse_bare_timestamp(self):
        version, origin = parse_authz_payload("1700000000000")
        self.assertEqual(version, 1700000000000)
        self.assertEqual(origin, "")

    def test_parse_bytes(self):
        version, origin = parse_authz_payload(b'{"version": 7, "origin": "b"}')
        self.assertEqual(version, 7)
        self.assertEqual(origin, "b")

    def test_parse_empty(self):
        self.assertEqual(parse_authz_payload(None), (0, ""))
        self.assertEqual(parse_authz_payload("not-json"), (0, ""))


class TestAuthzCacheVersion(unittest.TestCase):
    def setUp(self):
        clear()
        self.role = _Role("operator", "roleop01")
        self.user = _User("maria", self.role)

    def tearDown(self):
        clear()

    def test_older_version_does_not_reload(self):
        rows = [
            {
                "subject_type": "role",
                "subject_id": "roleop01",
                "resource_key": "hmi:view.events",
                "action": "view",
                "effect": "allow",
            }
        ]
        with patch("automation.authz.store._rows_from_historian", return_value=rows), patch(
            "automation.authz.store._rows_from_local", return_value=[]
        ):
            n = reload_cache(reason="test", version=100)
            self.assertEqual(n, 1)
            self.assertEqual(cache_version(), 100)
            with patch("automation.authz.store._rows_from_historian") as historian:
                skipped = reload_cache(reason="notify", version=50)
            historian.assert_not_called()
            self.assertEqual(skipped, 1)
            self.assertTrue(evaluate(self.user, "hmi:view.events", "view"))

    def test_newer_version_reloads(self):
        first = [
            {
                "subject_type": "role",
                "subject_id": "roleop01",
                "resource_key": "hmi:view.events",
                "action": "view",
                "effect": "allow",
            }
        ]
        second = [
            {
                "subject_type": "role",
                "subject_id": "roleop01",
                "resource_key": "hmi:view.events",
                "action": "view",
                "effect": "deny",
            }
        ]
        with patch("automation.authz.store._rows_from_historian", return_value=first):
            reload_cache(reason="test", version=10)
        self.assertTrue(evaluate(self.user, "hmi:view.events", "view"))
        with patch("automation.authz.store._rows_from_historian", return_value=second):
            apply_authz_invalidate(version=11, origin="edge-b", reason="pg_notify")
        self.assertFalse(evaluate(self.user, "hmi:view.events", "view"))
        self.assertEqual(cache_version(), 11)

    def test_pg_down_falls_back_to_sqlite(self):
        local = [
            {
                "subject_type": "role",
                "subject_id": "roleop01",
                "resource_key": "hmi:view.tags.definitions",
                "action": "view",
                "effect": "allow",
            }
        ]
        with patch("automation.authz.store._rows_from_historian", return_value=None), patch(
            "automation.authz.store._rows_from_local", return_value=local
        ):
            reload_cache(reason="boot", version=1)
        self.assertEqual(
            lookup("role", "roleop01", "hmi:view.tags.definitions", "view"),
            "allow",
        )

    def test_empty_cache_is_fail_closed(self):
        with patch("automation.authz.store._rows_from_historian", return_value=[]), patch(
            "automation.authz.store._rows_from_local", return_value=[]
        ):
            reload_cache(reason="boot", version=1)
        self.assertFalse(evaluate(self.user, "hmi:view.events", "view"))

    def test_hot_path_does_not_touch_historian(self):
        put_grant("role", "roleop01", "hmi:view.events", "view", "allow")
        with patch("automation.authz.store._rows_from_historian") as historian:
            self.assertTrue(evaluate(self.user, "hmi:view.events", "view"))
        historian.assert_not_called()

    def test_periodic_skips_when_fresh(self):
        with patch("automation.authz.store._rows_from_historian", return_value=[]):
            reload_cache(reason="boot", version=1)
            with patch("automation.authz.store.reload_cache") as inner:
                maybe_periodic_reload(interval_s=300.0)
            inner.assert_not_called()

    def test_periodic_reloads_when_stale(self):
        with patch("automation.authz.store._rows_from_historian", return_value=[]):
            reload_cache(reason="boot", version=1)
        with patch("automation.authz.store.reload_cache", return_value=0) as inner:
            n = maybe_periodic_reload(interval_s=0.0)
        inner.assert_called_once()
        self.assertEqual(n, 0)


class TestAuthzNotifyBus(unittest.TestCase):
    def test_notify_uses_pg_and_redis_not_grant_payload(self):
        db = MagicMock()
        app = MagicMock()
        app.is_db_connected.return_value = True
        app.db_manager.get_db.return_value = db
        redis = MagicMock()
        with patch("automation.PyAutomation", return_value=app), patch(
            "automation.utils.redis_client.get_redis", return_value=redis
        ), patch("automation.authz.invalidate._origin_node", return_value="edge-a"):
            stamp = notify_authz_invalidated(12345)
        self.assertEqual(stamp, 12345)
        sql, params = db.execute_sql.call_args[0]
        self.assertIn("pg_notify", sql)
        self.assertEqual(params[0], PG_CHANNEL)
        payload = json.loads(params[1])
        self.assertEqual(payload["version"], 12345)
        self.assertEqual(payload["origin"], "edge-a")
        self.assertNotIn("grants", payload)
        redis.publish.assert_called_once_with(REDIS_CHANNEL, params[1])

    def test_notify_without_pg_still_publishes_redis(self):
        app = MagicMock()
        app.is_db_connected.return_value = False
        redis = MagicMock()
        with patch("automation.PyAutomation", return_value=app), patch(
            "automation.utils.redis_client.get_redis", return_value=redis
        ):
            notify_authz_invalidated(7)
        redis.publish.assert_called_once()
        app.db_manager.get_db.assert_not_called()

    def test_notify_without_redis_still_notifies_pg(self):
        db = MagicMock()
        app = MagicMock()
        app.is_db_connected.return_value = True
        app.db_manager.get_db.return_value = db
        with patch("automation.PyAutomation", return_value=app), patch(
            "automation.utils.redis_client.get_redis", return_value=None
        ):
            notify_authz_invalidated(8)
        db.execute_sql.assert_called_once()

    def test_cross_edge_apply_under_two_seconds(self):
        started = time.monotonic()
        with patch("automation.authz.store._rows_from_historian", return_value=[]), patch(
            "automation.authz.store._rows_from_local", return_value=[]
        ):
            notify_authz_invalidated(1)
            apply_authz_invalidate(version=2, origin="edge-a", reason="pg_notify")
        self.assertLessEqual(time.monotonic() - started, 2.0)


class TestInvalidateWorkerDispatch(unittest.TestCase):
    def test_drain_pg_dispatches_authz_channel(self):
        from automation.authz.invalidate import PG_CHANNEL as AUTHZ_PG
        from automation.workers.user_invalidate import UserInvalidateWorker

        worker = UserInvalidateWorker()
        notify = MagicMock()
        notify.channel = AUTHZ_PG
        notify.payload = '{"version": 42, "origin": "edge-b"}'
        conn = MagicMock()
        conn.notifies = [notify]
        worker._pg_conn = conn
        with patch("select.select", return_value=([conn], [], [])), patch(
            "automation.workers.user_invalidate.apply_authz_invalidate"
        ) as apply, patch(
            "automation.workers.user_invalidate.apply_user_invalidate"
        ) as users:
            worker._drain_pg()
        apply.assert_called_once_with(version=42, origin="edge-b", reason="pg_notify")
        users.assert_not_called()

    def test_drain_redis_dispatches_authz_channel(self):
        from automation.authz.invalidate import REDIS_CHANNEL as AUTHZ_REDIS
        from automation.workers.user_invalidate import UserInvalidateWorker

        worker = UserInvalidateWorker()
        pubsub = MagicMock()
        pubsub.get_message.side_effect = [
            {
                "type": "message",
                "channel": AUTHZ_REDIS,
                "data": '{"version": 9, "origin": "edge-a"}',
            },
            None,
        ]
        worker._redis_pubsub = pubsub
        with patch("automation.workers.user_invalidate.apply_authz_invalidate") as apply:
            worker._drain_redis()
        apply.assert_called_once_with(version=9, origin="edge-a", reason="redis")

    def test_put_resource_notifies_after_reload(self):
        import inspect

        from automation.modules.authz.resources import authz as authz_res

        source = inspect.getsource(authz_res.AuthzGrantsResource.put)
        self.assertIn("notify_authz_invalidated", source)
        self.assertIn("reload_cache", source)


if __name__ == "__main__":
    unittest.main()
