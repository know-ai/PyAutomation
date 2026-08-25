import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

from peewee import SqliteDatabase

from automation.dbmodels.core import proxy
from automation.dbmodels.hmi_sessions import HMISession


class TestHmiSessionStoreGetDb(unittest.TestCase):
    def test_get_db_reopens_closed_greenlet_handle(self):
        from automation.utils.hmi_session_store import _get_db

        db = MagicMock()
        db.is_closed.return_value = True
        app = MagicMock()
        app.is_db_connected.return_value = True
        app.db_manager.get_db.return_value = db
        with patch("automation.PyAutomation", return_value=app), patch(
            "automation.utils.db_connections.ensure_bound_connection"
        ) as ensure:
            self.assertIs(_get_db(), db)
        ensure.assert_called_once_with(db)


class TestHmiSessionStore(unittest.TestCase):
    def setUp(self):
        self.db = SqliteDatabase(":memory:")
        proxy.initialize(self.db)
        self.db.create_tables([HMISession])
        from automation.utils.hmi_session_store import reset_hmi_sessions_for_tests

        reset_hmi_sessions_for_tests()
        self.node_patcher = patch(
            "automation.utils.hmi_session_store.node_identity",
            return_value=("edge-a", "Line1"),
        )
        self.db_patcher = patch(
            "automation.utils.hmi_session_store._get_db",
            return_value=self.db,
        )
        self.close_patcher = patch(
            "automation.utils.hmi_session_store._close_historian_socket"
        )
        self.redis_patcher = patch(
            "automation.utils.redis_client.get_redis",
            return_value=None,
        )
        self.ephemeral_patcher = patch(
            "automation.utils.db_connections.ephemeral_historian",
        )
        self.node_patcher.start()
        self.db_patcher.start()
        self.close_patcher.start()
        self.redis_patcher.start()
        eph = self.ephemeral_patcher.start()
        from contextlib import contextmanager

        @contextmanager
        def _noop(_db):
            yield

        eph.side_effect = lambda db: _noop(db)

    def tearDown(self):
        self.ephemeral_patcher.stop()
        self.redis_patcher.stop()
        self.close_patcher.stop()
        self.db_patcher.stop()
        self.node_patcher.stop()
        self.db.drop_tables([HMISession])
        self.db.close()
        from automation.utils.hmi_session_store import reset_hmi_sessions_for_tests

        reset_hmi_sessions_for_tests()

    def test_upsert_and_count(self):
        from automation.utils.hmi_session_store import count_sessions, upsert_session

        self.assertTrue(upsert_session(sid="sid-1", username="op1", origin="10.0.0.1"))
        self.assertTrue(upsert_session(sid="sid-2", username="op2", origin="10.0.0.2"))
        self.assertEqual(count_sessions(), 2)

    def test_remove_session(self):
        from automation.utils.hmi_session_store import count_sessions, remove_session, upsert_session

        upsert_session(sid="sid-1", username="op1", origin="10.0.0.1")
        snapshot = remove_session("sid-1")
        self.assertIsNotNone(snapshot)
        self.assertEqual(snapshot.username, "op1")
        self.assertEqual(count_sessions(), 0)

    def test_touch_heartbeat(self):
        from automation.utils.hmi_session_store import touch_heartbeat, upsert_session

        upsert_session(sid="sid-1", username="op1", origin="10.0.0.1")
        self.assertTrue(touch_heartbeat("sid-1"))

    def test_cleanup_stale_sessions(self):
        from automation.utils import hmi_session_store as store

        store.upsert_session(sid="sid-stale", username="op1", origin="10.0.0.1")
        stale = datetime.now(timezone.utc) - timedelta(minutes=5)
        with store._STORE._lock:
            store._STORE._fallback_meta["sid-stale"]["last_heartbeat"] = stale
        removed = store.cleanup_stale_sessions(stale_seconds=120)
        self.assertEqual(removed, 1)

    def test_ram_fallback_cache_is_the_hot_path_mirror(self):
        from automation.utils.hmi_session_store import HmiSessionStore, _STORE, upsert_session

        self.assertTrue(hasattr(HmiSessionStore, "upsert"))
        self.assertTrue(hasattr(_STORE, "_fallback_cache"))
        upsert_session(sid="sid-ram", username="op1", origin="10.0.0.1")
        self.assertIn("sid-ram", _STORE._fallback_cache.get("edge-a") or set())

    def test_upsert_does_not_write_postgres(self):
        from automation.utils.hmi_session_store import upsert_session

        with patch.object(HMISession, "insert") as insert:
            upsert_session(sid="sid-hot", username="op1", origin="10.0.0.1")
        insert.assert_not_called()
        self.assertEqual(HMISession.select().count(), 0)

    def test_flush_pg_snapshot_writes(self):
        from automation.utils.hmi_session_store import flush_pg_snapshot, upsert_session

        upsert_session(sid="sid-bg", username="op1", origin="10.0.0.1")
        flushed = flush_pg_snapshot()
        self.assertGreaterEqual(flushed, 1)
        self.assertEqual(HMISession.select().where(HMISession.sid == "sid-bg").count(), 1)


class TestHmiSocketAuditAplus(unittest.TestCase):
    @patch("automation.utils.hmi_socket_audit.persist_system_event", return_value=True)
    @patch("automation.utils.hmi_socket_audit.get_system_user")
    @patch("automation.utils.hmi_socket_audit.count_sessions", return_value=1)
    @patch("automation.utils.hmi_socket_audit.upsert_session", return_value=True)
    def test_valid_connect(self, upsert, _count, get_user, persist):
        from automation.utils.hmi_socket_audit import attempt_hmi_socket_connect

        user = MagicMock(username="operator")
        get_user.return_value = user
        with patch(
            "automation.utils.hmi_socket_audit.resolve_connect_user",
            return_value=(user, "operator", ""),
        ), patch(
            "automation.utils.hmi_socket_audit.socket_request_origin",
            return_value="192.168.10.20",
        ), patch(
            "automation.utils.hmi_socket_audit._edge_label",
            return_value="Plant.Line1",
        ):
            self.assertTrue(
                attempt_hmi_socket_connect(auth={"token": "abc"}, sid="sid-abc")
            )
        upsert.assert_called_once()
        self.assertEqual(persist.call_args.kwargs["message"], "HMI client connected")

    @patch("automation.utils.hmi_socket_audit.persist_system_event", return_value=True)
    @patch("automation.utils.hmi_socket_audit.get_system_user")
    @patch("automation.utils.hmi_socket_audit.count_sessions", return_value=0)
    def test_invalid_token_rejected(self, _count, get_user, persist):
        from automation.utils.hmi_socket_audit import attempt_hmi_socket_connect

        get_user.return_value = MagicMock(username="system")
        with patch(
            "automation.utils.hmi_socket_audit.resolve_connect_user",
            return_value=(None, "unknown", "invalid_token"),
        ), patch(
            "automation.utils.hmi_socket_audit.socket_request_origin",
            return_value="192.168.10.20",
        ), patch(
            "automation.utils.hmi_socket_audit._edge_label",
            return_value="Plant.Line1",
        ):
            self.assertFalse(
                attempt_hmi_socket_connect(auth={"token": "bad"}, sid="sid-x")
            )
        self.assertEqual(
            persist.call_args.kwargs["message"], "HMI client connection rejected"
        )
        self.assertIn("invalid_token", persist.call_args.kwargs["description"])

    @patch("automation.utils.hmi_socket_audit.persist_system_event", return_value=True)
    @patch("automation.utils.hmi_socket_audit.count_sessions", return_value=0)
    @patch("automation.utils.hmi_socket_audit.upsert_session", return_value=False)
    def test_session_store_unavailable_still_accepts(self, _upsert, _count, persist):
        """Local catalog autonomy: Socket.IO must not depend on historian sessions."""
        from automation.utils.hmi_socket_audit import attempt_hmi_socket_connect

        user = MagicMock(username="operator")
        with patch(
            "automation.utils.hmi_socket_audit.resolve_connect_user",
            return_value=(user, "operator", ""),
        ), patch(
            "automation.utils.hmi_socket_audit.socket_request_origin",
            return_value="192.168.10.20",
        ), patch(
            "automation.utils.hmi_socket_audit._edge_label",
            return_value="Plant.Line1",
        ):
            self.assertTrue(
                attempt_hmi_socket_connect(auth={"token": "abc"}, sid="sid-abc")
            )
        self.assertIn(
            "session_store_degraded",
            persist.call_args.kwargs["description"],
        )

    @patch("automation.utils.hmi_socket_audit.persist_system_event", return_value=True)
    @patch("automation.utils.hmi_socket_audit.get_system_user")
    @patch("automation.utils.hmi_socket_audit.count_sessions", return_value=0)
    @patch("automation.utils.hmi_socket_audit.remove_session")
    def test_disconnect_after_remove(self, remove_session, _count, get_user, persist):
        from automation.utils.hmi_session_store import StoredSession
        from automation.utils.hmi_socket_audit import register_hmi_socket_disconnect

        get_user.return_value = MagicMock(username="system")
        remove_session.return_value = StoredSession(
            sid="sid-abc",
            node_id="edge-a",
            username="operator",
            origin="192.168.10.20",
            area="Line1",
        )
        register_hmi_socket_disconnect(sid="sid-abc", reason="transport close")
        self.assertEqual(persist.call_args.kwargs["message"], "HMI client disconnected")


class TestHmiTlsTelemetryPerIp(unittest.TestCase):
    def setUp(self):
        from automation.utils.hmi_tls_telemetry import reset_for_tests

        reset_for_tests()

    def test_per_ip_rate_limit(self):
        import ssl

        from automation.utils.hmi_tls_telemetry import record_client_tls_failure

        err = ssl.SSLError(1, "certificate unknown")
        timeline = iter([0.0, 1.0, 301.0])
        with patch("automation.utils.hmi_tls_telemetry._IP_RATE_S", 300.0):
            with patch("automation.utils.hmi_tls_telemetry.time.monotonic", lambda: next(timeline)):
                with patch("automation.utils.system_event_audit.persist_system_event") as mock_event:
                    record_client_tls_failure(err, origin="10.0.0.55")
                    record_client_tls_failure(err, origin="10.0.0.55")
                    self.assertEqual(mock_event.call_count, 0)
                    record_client_tls_failure(err, origin="10.0.0.55")
                    self.assertEqual(mock_event.call_count, 1)
                    description = mock_event.call_args.kwargs.get("description") or ""
                    self.assertIn("origin=10.0.0.55", description)
                    self.assertEqual(
                        mock_event.call_args.kwargs.get("message"),
                        "HMI TLS handshake failure",
                    )


class FakeRedis:
    def __init__(self):
        self.kv = {}
        self.sets = {}

    def ping(self):
        return True

    def pipeline(self, transaction=True):
        return FakeRedisPipeline(self)

    def setex(self, key, _ttl, value):
        self.kv[key] = value
        return True

    def get(self, key):
        return self.kv.get(key)

    def delete(self, key):
        return 1 if self.kv.pop(key, None) is not None else 0

    def sadd(self, key, *members):
        bucket = self.sets.setdefault(key, set())
        before = len(bucket)
        bucket.update(members)
        return len(bucket) - before

    def srem(self, key, *members):
        bucket = self.sets.get(key)
        if not bucket:
            return 0
        removed = 0
        for member in members:
            if member in bucket:
                bucket.remove(member)
                removed += 1
        return removed

    def smembers(self, key):
        return set(self.sets.get(key) or ())

    def scard(self, key):
        return len(self.sets.get(key) or ())

    def expire(self, key, _ttl):
        return key in self.kv or key in self.sets

    def exists(self, key):
        return int(key in self.kv or key in self.sets)

    def publish(self, _channel, _payload):
        return 1


class FakeRedisPipeline:
    def __init__(self, client: FakeRedis):
        self.client = client
        self._ops = []

    def setex(self, *args, **kwargs):
        self._ops.append(("setex", args, kwargs))
        return self

    def sadd(self, *args, **kwargs):
        self._ops.append(("sadd", args, kwargs))
        return self

    def expire(self, *args, **kwargs):
        self._ops.append(("expire", args, kwargs))
        return self

    def delete(self, *args, **kwargs):
        self._ops.append(("delete", args, kwargs))
        return self

    def srem(self, *args, **kwargs):
        self._ops.append(("srem", args, kwargs))
        return self

    def execute(self):
        results = []
        for name, args, kwargs in self._ops:
            results.append(getattr(self.client, name)(*args, **kwargs))
        self._ops.clear()
        return results


class TestRedisHmiSessionStore(unittest.TestCase):
    def setUp(self):
        from automation.utils.hmi_session_store import reset_hmi_sessions_for_tests
        from automation.utils.redis_client import reset_redis_for_tests

        reset_hmi_sessions_for_tests()
        reset_redis_for_tests()
        self.fake = FakeRedis()
        self.node_patcher = patch(
            "automation.utils.hmi_session_store.node_identity",
            return_value=("edge-a", "Line1"),
        )
        self.redis_patcher = patch(
            "automation.utils.redis_client.get_redis",
            return_value=self.fake,
        )
        self.node_patcher.start()
        self.redis_patcher.start()

    def tearDown(self):
        self.redis_patcher.stop()
        self.node_patcher.stop()
        from automation.utils.hmi_session_store import reset_hmi_sessions_for_tests
        from automation.utils.redis_client import reset_redis_for_tests

        reset_hmi_sessions_for_tests()
        reset_redis_for_tests()

    def test_sadd_and_scard_per_node(self):
        from automation.utils.hmi_session_store import count_sessions, upsert_session

        upsert_session(sid="sid-a", username="op1", origin="10.0.0.1")
        upsert_session(sid="sid-b", username="op2", origin="10.0.0.2")
        self.assertEqual(count_sessions("edge-a"), 2)
        self.assertEqual(self.fake.scard("hmi:sessions:edge-a"), 2)

    def test_connect_handler_p99_under_5ms(self):
        import time

        from automation.utils.hmi_session_store import upsert_session

        samples = []
        for i in range(50):
            started = time.perf_counter()
            upsert_session(sid=f"sid-{i}", username="op", origin="10.0.0.1")
            samples.append((time.perf_counter() - started) * 1000.0)
        samples.sort()
        p99 = samples[int(0.99 * (len(samples) - 1))]
        self.assertLess(p99, 5.0)

    def test_redis_down_falls_back_to_memory(self):
        from automation.utils.hmi_session_store import count_sessions, upsert_session

        self.redis_patcher.stop()
        with patch("automation.utils.redis_client.get_redis", return_value=None):
            upsert_session(sid="sid-mem", username="op1", origin="10.0.0.1")
            self.assertEqual(count_sessions("edge-a"), 1)
        self.redis_patcher = patch(
            "automation.utils.redis_client.get_redis",
            return_value=self.fake,
        )
        self.redis_patcher.start()


class TestRedisConfigWarning(unittest.TestCase):
    def test_warns_when_url_missing(self):
        from automation.utils.redis_client import reset_redis_for_tests, warn_if_redis_unconfigured

        reset_redis_for_tests()
        with patch.dict("os.environ", {"AUTOMATION_REDIS_URL": ""}, clear=False), patch(
            "automation.utils.redis_client._LOGGER"
        ) as logger:
            warn_if_redis_unconfigured()
        logger.warning.assert_called()
        self.assertIn("AUTOMATION_REDIS_URL", logger.warning.call_args[0][0])


if __name__ == "__main__":
    unittest.main()
