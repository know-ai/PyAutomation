# -*- coding: utf-8 -*-
"""Acceptance tests for local SQLite catalog mirror (spec 11)."""
from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from werkzeug.security import generate_password_hash

from automation.catalog.conflict import VersionStamp, resolve
from automation.catalog.schema import (
    CATALOG_TABLES_COUNT,
    REPLICATED_TABLES,
    SYNC_ORDER,
    historian_dbtype_allowed,
)


class TestHistorianDbtype(unittest.TestCase):
    """CA-CATALOG-11"""

    def test_sqlite_rejected(self):
        self.assertFalse(historian_dbtype_allowed("sqlite"))
        self.assertTrue(historian_dbtype_allowed("postgresql"))
        self.assertTrue(historian_dbtype_allowed("mysql"))


class TestSchemaOrder(unittest.TestCase):
    """CA-CATALOG-12"""

    def test_parents_before_children(self):
        names = [t.name for t in SYNC_ORDER]
        self.assertLess(names.index("roles"), names.index("users"))
        self.assertLess(names.index("datatypes"), names.index("tags"))
        self.assertLess(names.index("tags"), names.index("alarms"))
        self.assertIn("hmi_sessions", names)
        self.assertNotIn("hmi_sessions", REPLICATED_TABLES)
        self.assertGreaterEqual(CATALOG_TABLES_COUNT, 17)


class TestConflictResolver(unittest.TestCase):
    """CA-CATALOG-04 — dirty local vs clean mirror / remote SoT."""

    def test_clean_local_defers_to_remote_even_if_newer(self):
        self.assertEqual(resolve(VersionStamp(20), VersionStamp(10)), "remote")

    def test_dirty_newer_local_wins(self):
        self.assertEqual(resolve(VersionStamp(20), VersionStamp(10), local_dirty=True), "local")

    def test_dirty_older_local_loses(self):
        self.assertEqual(resolve(VersionStamp(10), VersionStamp(20), local_dirty=True), "remote")

    def test_tie_goes_to_remote(self):
        self.assertEqual(resolve(VersionStamp(10), VersionStamp(10), local_dirty=True), "remote")

    def test_missing_local(self):
        self.assertEqual(resolve(None, VersionStamp(1)), "remote")


class TestLocalCatalogRoundtrip(unittest.TestCase):
    """CA-CATALOG-01 / 06 helpers"""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.path = os.path.join(self._tmp.name, "catalog.db")
        from automation.catalog.bootstrap import bootstrap_local_catalog
        from automation.catalog.local_db import close_catalog_db

        close_catalog_db()
        bootstrap_local_catalog(self.path)

    def tearDown(self):
        from automation.catalog.local_db import close_catalog_db

        close_catalog_db()
        self._tmp.cleanup()

    def test_upsert_and_version(self):
        from automation.catalog.local_provider import LocalCatalogProvider
        from automation.catalog.versions import get_local

        provider = LocalCatalogProvider()
        pk = provider.upsert(
            "roles",
            {"name": "OPERATOR", "level": 10, "identifier": "abcd"},
            node_id="edge-a",
            version=111,
        )
        self.assertTrue(pk)
        row = provider.read("roles", pk)
        self.assertEqual(row["name"], "OPERATOR")
        ver = get_local("roles", pk)
        self.assertEqual(int(ver.version), 111)
        self.assertEqual(ver.node_id, "edge-a")

    def test_login_local_catalog(self):
        from automation.catalog.auth import login_local
        from automation.catalog.local_provider import LocalCatalogProvider

        provider = LocalCatalogProvider()
        role_pk = provider.upsert(
            "roles",
            {"name": "GUEST", "level": 256, "identifier": "guest1"},
            node_id="edge-a",
            version=1,
        )
        hashed = generate_password_hash("secret")
        provider.upsert(
            "users",
            {
                "username": "alice_local",
                "email": "alice@local.test",
                "password": hashed,
                "identifier": "u1",
                "role_id": role_pk,
            },
            node_id="edge-a",
            version=2,
        )
        user, msg = login_local("secret", username="alice_local")
        self.assertIsNotNone(user, msg)
        self.assertIn("local", msg.lower())
        self.assertTrue(getattr(user, "token", None), "local login must mint apiKey/token")
        bad, _ = login_local("wrong", username="alice_local")
        self.assertIsNone(bad)

    def test_app_login_offline_returns_auth_error_not_db_config(self):
        """Failed offline login must not coerce into historian/DB config messages."""
        from automation import PyAutomation
        from automation.catalog.local_provider import LocalCatalogProvider

        provider = LocalCatalogProvider()
        role_pk = provider.upsert(
            "roles",
            {"name": "GUEST", "level": 256, "identifier": "guest1"},
            node_id="edge-a",
            version=1,
        )
        hashed = generate_password_hash("secret")
        provider.upsert(
            "users",
            {
                "username": "bob_offline",
                "email": "bob@local.test",
                "password": hashed,
                "identifier": "u2",
                "role_id": role_pk,
            },
            node_id="edge-a",
            version=2,
        )

        app = PyAutomation()
        # Ensure historian path is not used (no remote connection in this test env).
        self.assertFalse(app.is_db_connected())

        missing, msg_missing = app.login("anything", username="does_not_exist")
        self.assertIsNone(missing)
        self.assertIn("authentication error", msg_missing.lower())
        self.assertNotIn("database is not configured", msg_missing.lower())
        self.assertNotIn("connecting database error", msg_missing.lower())

        wrong, msg_wrong = app.login("wrong", username="bob_offline")
        self.assertIsNone(wrong)
        self.assertIn("authentication error", msg_wrong.lower())
        self.assertNotIn("connecting database error", msg_wrong.lower())

        ok, msg_ok = app.login("secret", username="bob_offline")
        self.assertIsNotNone(ok, msg_ok)
        self.assertTrue(getattr(ok, "token", None))


class TestColdStartLocalSeed(unittest.TestCase):
    """Cold start without historian: defaults land in catalog.db."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.path = os.path.join(self._tmp.name, "catalog.db")
        from automation.catalog.bootstrap import bootstrap_local_catalog
        from automation.catalog.local_db import close_catalog_db

        close_catalog_db()
        bootstrap_local_catalog(self.path)

    def tearDown(self):
        from automation.catalog.local_db import close_catalog_db

        close_catalog_db()
        self._tmp.cleanup()

    def test_seed_defaults_and_system_user(self):
        from automation.catalog.auth import login_local
        from automation.catalog.local_provider import LocalCatalogProvider
        from automation.catalog.seed import (
            persist_alarm_to_local,
            persist_tag_to_local,
            seed_local_catalog_defaults,
        )

        counts = seed_local_catalog_defaults(system_password="cold_start_pw")
        self.assertFalse(counts.get("skipped"))
        provider = LocalCatalogProvider()
        role_names = {str(r.get("name") or "").upper() for r in provider.read_all("roles")}
        self.assertIn("SUDO", role_names)
        self.assertGreaterEqual(len(provider.read_all("datatypes")), 1)
        self.assertGreaterEqual(len(provider.read_all("units")), 1)
        self.assertGreaterEqual(len(provider.read_all("alarmtypes")), 1)
        self.assertGreaterEqual(len(provider.read_all("alarmstates")), 1)
        user, msg = login_local("cold_start_pw", username="system")
        self.assertIsNotNone(user, msg)

        # Idempotent second seed
        again = seed_local_catalog_defaults(system_password="cold_start_pw")
        self.assertEqual(again.get("system_user"), 0)
        self.assertEqual(again.get("datatypes"), 0)
        self.assertEqual(again.get("variables_units"), 0)
        self.assertEqual(again.get("roles"), 0)

        class _Tag:
            id = "tid1"
            name = "SYS.TEST.Flag"
            unit = "adim"
            display_unit = "adim"
            data_type = "boolean"
            description = "test"
            display_name = "Test Flag"
            opcua_address = None
            node_namespace = None
            scan_time = None
            dead_band = None
            kp = None
            area = None
            owner_node = None
            filter_enabled = False
            filter_wavelet = "db4"
            filter_level = 4
            filter_threshold_factor = 3.0
            filter_persist = False
            out_of_range_detection = False
            outlier_detection = False
            frozen_data_detection = False

            def get_opcua_client_name(self):
                return None

        self.assertIsNotNone(persist_tag_to_local(_Tag()))
        self.assertIsNotNone(
            persist_alarm_to_local(
                identifier="aid1",
                name="ALM.TEST.Flag",
                tag_name="SYS.TEST.Flag",
                trigger_type="BOOL",
                trigger_value=True,
                description="test alarm",
            )
        )
        self.assertTrue(any(t.get("name") == "SYS.TEST.Flag" for t in provider.read_all("tags")))
        self.assertTrue(any(a.get("name") == "ALM.TEST.Flag" for a in provider.read_all("alarms")))

        from automation.catalog.seed import persist_machine_to_local

        self.assertIsNotNone(
            persist_machine_to_local(
                identifier="m1",
                name="Linea1.LDS",
                interval=1.0,
                description="LDS",
                classification="Leak Detection",
                buffer_size=10,
                area="Linea1",
            )
        )
        self.assertTrue(any(m.get("name") == "Linea1.LDS" for m in provider.read_all("machines")))

    def test_seed_does_not_overwrite_existing_units(self):
        from automation.catalog.local_provider import LocalCatalogProvider
        from automation.catalog.seed import seed_local_catalog_defaults, seed_variables_and_units

        seed_local_catalog_defaults(system_password="cold_start_pw")
        provider = LocalCatalogProvider()
        before = {r.get("unit"): r.get("variable_id") for r in provider.read_all("units")}
        self.assertIn("bar", before)
        # Operator-authored symbol must survive a second seed pass.
        provider.upsert(
            "units",
            {
                "name": "operator_custom",
                "unit": "baz",
                "variable_id": before["bar"],
            },
        )
        self.assertEqual(seed_variables_and_units(), 0)
        after = {r.get("unit"): r.get("variable_id") for r in provider.read_all("units")}
        self.assertEqual(after.get("bar"), before.get("bar"))
        self.assertIn("baz", after)
        self.assertEqual(after["baz"], before["bar"])

    def test_tag_upsert_does_not_blank_unit_fk(self):
        from automation.catalog.local_provider import LocalCatalogProvider
        from automation.catalog.seed import persist_tag_to_local, seed_local_catalog_defaults

        seed_local_catalog_defaults(system_password="cold_start_pw")
        provider = LocalCatalogProvider()

        class _Tag:
            id = "tid-bar"
            name = "PT.BAR"
            unit = "bar"
            display_unit = "bar"
            data_type = "float"
            description = "pressure"
            display_name = "PT BAR"
            opcua_address = "opc.tcp://x"
            opcua_client_name = "PLC"
            node_namespace = "ns=2;i=1"
            scan_time = 1000
            dead_band = None
            kp = None
            area = None
            owner_node = None
            variable = "Pressure"
            filter_enabled = False
            filter_wavelet = "db4"
            filter_level = 4
            filter_threshold_factor = 3.0
            filter_persist = False
            out_of_range_detection = False
            outlier_detection = False
            frozen_data_detection = False

            def get_opcua_client_name(self):
                return self.opcua_client_name

            def set_opcua_address(self, value):
                self.opcua_address = value

            def set_opcua_client_name(self, name, opcua_address=None):
                self.opcua_client_name = name

            def set_node_namespace(self, value):
                self.node_namespace = value

            def set_scan_time(self, value):
                self.scan_time = value

        self.assertIsNotNone(persist_tag_to_local(_Tag()))
        row = next(t for t in provider.read_all("tags") if t.get("name") == "PT.BAR")
        unit_id = row.get("unit") or row.get("unit_id")
        self.assertTrue(unit_id)
        # Blank unit must not wipe the FK (restart / partial payload).
        provider.upsert(
            "tags",
            {
                "id": row.get("_pk") or row.get("id"),
                "name": "PT.BAR",
                "unit": None,
                "unit_id": None,
                "description": "still pressure",
            },
        )
        again = next(t for t in provider.read_all("tags") if t.get("name") == "PT.BAR")
        self.assertEqual(again.get("unit") or again.get("unit_id"), unit_id)
        self.assertEqual(again.get("description"), "still pressure")

    def test_persist_opcua_client_and_preserve_tag_opc_mapping(self):
        from automation.catalog.local_provider import LocalCatalogProvider
        from automation.catalog.seed import (
            delete_opcua_client_from_local,
            persist_opcua_client_to_local,
            persist_tag_to_local,
            seed_local_catalog_defaults,
        )

        seed_local_catalog_defaults(system_password="cold_start_pw")
        self.assertIsNotNone(
            persist_opcua_client_to_local(
                client_name="PLC",
                host="172.20.0.1",
                port=4840,
                owner_node="edge-linea1",
            )
        )
        provider = LocalCatalogProvider()
        clients = {c.get("client_name"): c for c in provider.read_all("opcua")}
        self.assertIn("PLC", clients)
        self.assertEqual(clients["PLC"].get("host"), "172.20.0.1")
        self.assertEqual(int(clients["PLC"].get("port")), 4840)

        class _Tag:
            id = "tid-pi02"
            name = "Supe.Linea1.PI_02"
            unit = "adim"
            display_unit = "adim"
            data_type = "float"
            description = "Outlet Pressure"
            display_name = "Supe.Linea1.PI_02"
            opcua_address = "opc.tcp://172.20.0.1:4840"
            node_namespace = "ns=2;i=3"
            scan_time = 1000
            dead_band = 0.0
            kp = None
            area = "Linea1"
            owner_node = "edge-linea1"
            filter_enabled = False
            filter_wavelet = "db4"
            filter_level = 4
            filter_threshold_factor = 3.0
            filter_persist = False
            out_of_range_detection = True
            outlier_detection = True
            frozen_data_detection = True
            opcua_client_name = "PLC"

            def get_opcua_client_name(self):
                return self.opcua_client_name

            def set_opcua_address(self, opcua_address):
                self.opcua_address = opcua_address

            def set_opcua_client_name(self, client_name, opcua_address=None):
                self.opcua_client_name = client_name
                if opcua_address:
                    self.opcua_address = opcua_address

            def set_node_namespace(self, node_namespace):
                self.node_namespace = node_namespace

            def set_scan_time(self, scan_time):
                self.scan_time = scan_time

        self.assertIsNotNone(persist_tag_to_local(_Tag()))
        # Re-seed without OPC fields must not wipe the catalog mapping.
        blank = _Tag()
        blank.opcua_address = ""
        blank.node_namespace = ""
        blank.scan_time = 0
        blank.opcua_client_name = None
        self.assertIsNotNone(persist_tag_to_local(blank))
        row = next(t for t in provider.read_all("tags") if t.get("name") == "Supe.Linea1.PI_02")
        self.assertEqual(row.get("opcua_client_name"), "PLC")
        self.assertEqual(row.get("opcua_address"), "opc.tcp://172.20.0.1:4840")
        self.assertEqual(row.get("node_namespace"), "ns=2;i=3")
        self.assertEqual(int(row.get("scan_time") or 0), 1000)
        # CVT-side blank tag should be restored from catalog during merge.
        self.assertEqual(blank.opcua_client_name, "PLC")
        self.assertEqual(blank.node_namespace, "ns=2;i=3")

        delete_opcua_client_from_local("PLC")
        self.assertFalse(any(c.get("client_name") == "PLC" for c in provider.read_all("opcua")))

    def test_offline_catalog_mutations_parity(self):
        from automation.catalog.local_provider import LocalCatalogProvider
        from automation.catalog.mutations import (
            delete_lrs_point_local,
            list_lrs_points_local,
            persist_alarm_fields_local,
            persist_lrs_point_local,
            persist_machine_fields_local,
            persist_opcua_server_local,
            persist_tagsmachines_bind,
            persist_tagsmachines_unbind,
            soft_deactivate_tag_local,
            soft_delete_alarm_local,
            update_opcua_server_access_local,
        )
        from automation.catalog.seed import (
            persist_alarm_to_local,
            persist_machine_to_local,
            persist_tag_to_local,
            seed_local_catalog_defaults,
        )

        seed_local_catalog_defaults(system_password="cold_start_pw")
        provider = LocalCatalogProvider()

        class _Tag:
            id = "tid-mut"
            name = "Linea1.MUT.Tag"
            unit = "adim"
            display_unit = "adim"
            data_type = "float"
            description = "mutation"
            display_name = "Linea1.MUT.Tag"
            opcua_address = None
            node_namespace = None
            scan_time = None
            dead_band = None
            kp = 12.5
            area = "Linea1"
            owner_node = "edge-linea1"
            manufacturer = "Supe"
            segment = "Linea1"
            filter_enabled = False
            filter_wavelet = "db4"
            filter_level = 4
            filter_threshold_factor = 3.0
            filter_persist = False
            out_of_range_detection = False
            outlier_detection = False
            frozen_data_detection = False

            def get_opcua_client_name(self):
                return None

        self.assertIsNotNone(persist_tag_to_local(_Tag()))
        self.assertIsNotNone(
            persist_machine_to_local(
                identifier="m-mut",
                name="Linea1.MUT",
                interval=1.0,
                description="mut",
                classification="Test",
                buffer_size=10,
                area="Linea1",
            )
        )
        self.assertIsNotNone(
            persist_alarm_to_local(
                identifier="aid-mut",
                name="ALM.MUT.Tag",
                tag_name="Linea1.MUT.Tag",
                trigger_type="HIGH",
                trigger_value=1.0,
                description="mut alarm",
            )
        )
        persist_alarm_fields_local(
            identifier="aid-mut",
            description="updated alarm",
            trigger_value=2.5,
        )
        alarm = next(a for a in provider.read_all("alarms") if a.get("name") == "ALM.MUT.Tag")
        self.assertEqual(alarm.get("description"), "updated alarm")
        self.assertEqual(float(alarm.get("trigger_value")), 2.5)

        persist_tagsmachines_bind(
            tag_name="Linea1.MUT.Tag",
            machine_name="Linea1.MUT",
            default_tag_name="PV",
        )
        self.assertTrue(provider.read_all("tagsmachines"))
        persist_tagsmachines_unbind(tag_name="Linea1.MUT.Tag", machine_name="Linea1.MUT")
        self.assertFalse(provider.read_all("tagsmachines"))

        persist_machine_fields_local(name="Linea1.MUT", threshold=7.5, buffer_size=20)
        machine = next(m for m in provider.read_all("machines") if m.get("name") == "Linea1.MUT")
        self.assertEqual(float(machine.get("threshold")), 7.5)
        self.assertEqual(int(machine.get("buffer_size")), 20)

        # Offline attribute edit must create the row when missing (HMI machines/detailed).
        persist_machine_fields_local(name="Linea1.NEW_OFFLINE", on_delay=12, interval=2.0)
        created = next(
            (m for m in provider.read_all("machines") if m.get("name") == "Linea1.NEW_OFFLINE"),
            None,
        )
        self.assertIsNotNone(created)
        self.assertEqual(int(created.get("on_delay")), 12)
        machine = next(m for m in provider.read_all("machines") if m.get("name") == "Linea1.MUT")
        self.assertEqual(float(machine.get("threshold")), 7.5)
        self.assertEqual(int(machine.get("buffer_size")), 20)

        persist_opcua_server_local(name="NodeA", namespace="ns=2;i=9", access_type="Read")
        update_opcua_server_access_local(namespace="ns=2;i=9", access_type="Write")
        opc = next(r for r in provider.read_all("opcuaserver") if r.get("namespace") == "ns=2;i=9")
        access_pk = opc.get("access_type_id") or opc.get("access_type")
        access = next(
            a for a in provider.read_all("accesstype") if str(a.get("_pk") or a.get("id")) == str(access_pk)
        )
        self.assertEqual(str(access.get("name")), "Write")

        point = persist_lrs_point_local(
            segment_name="Linea1",
            kp=100.0,
            latitude=10.0,
            longitude=20.0,
            elevation=1.0,
        )
        self.assertIsNotNone(point)
        self.assertEqual(len(list_lrs_points_local(segment_name="Linea1")), 1)
        self.assertTrue(delete_lrs_point_local(point_id=point["id"]))
        self.assertEqual(list_lrs_points_local(segment_name="Linea1"), [])

        soft_delete_alarm_local(identifier="aid-mut")
        soft_deactivate_tag_local(identifier="tid-mut", name="Linea1.MUT.Tag")
        tag = next(t for t in provider.read_all("tags") if t.get("name") == "Linea1.MUT.Tag")
        self.assertFalse(bool(tag.get("active")))

    def test_user_role_update_prefers_role_id_column(self):
        """Offline role changes must persist when payload has stale ``role`` + new ``role_id``."""
        from automation.catalog.local_provider import LocalCatalogProvider
        from automation.catalog.models import local_model
        from automation.catalog.rows import apply_raw, upsert_model
        from automation.catalog.seed import seed_local_catalog_defaults

        seed_local_catalog_defaults(system_password="cold_start_pw")
        provider = LocalCatalogProvider()
        roles = {
            str(r.get("name") or "").upper(): r.get("_pk") or r.get("id")
            for r in provider.read_all("roles")
        }
        guest_pk = roles["GUEST"]
        admin_pk = roles["ADMIN"]
        provider.upsert(
            "users",
            {
                "username": "crivero",
                "email": "crivero@example.com",
                "password": "x",
                "identifier": "u-crivero",
                "name": "",
                "lastname": "",
                "role_id": guest_pk,
            },
        )
        row = next(u for u in provider.read_all("users") if u.get("username") == "crivero")
        # Simulate the buggy offline update path (copy row, set only role_id).
        payload = dict(row)
        payload["role_id"] = admin_pk
        Users = local_model("users")
        applied = apply_raw(Users, payload)
        self.assertEqual(int(applied["role"]), int(admin_pk))
        upsert_model(Users, payload)
        updated = next(u for u in provider.read_all("users") if u.get("username") == "crivero")
        self.assertEqual(int(updated.get("role_id") or updated.get("role")), int(admin_pk))


class TestReplicatorStartupGrace(unittest.TestCase):
    def test_cycle_skips_during_grace_unless_forced(self):
        from automation.catalog.replicator import CatalogReplicatorWorker

        worker = CatalogReplicatorWorker(sync_interval=30.0, startup_grace_s=60.0)
        skipped = worker.cycle()
        self.assertEqual(skipped.get("reason"), "startup-grace")
        forced = worker.cycle(force=True)
        self.assertNotEqual(forced.get("reason"), "startup-grace")


class TestHmiCatalogSurfaces(unittest.TestCase):
    """CA-CATALOG-05 / 11 static HMI"""

    def _hmi(self, relative: str) -> str:
        root = Path(__file__).resolve().parents[2]
        return (root / "hmi" / "src" / relative).read_text(encoding="utf-8")

    def test_sqlite_removed_from_historian_forms(self):
        form = self._hmi("components/DatabaseConfigForm.tsx")
        self.assertNotIn('value="sqlite"', form)
        panel = self._hmi("components/DatabaseConnectivityPanel.tsx")
        self.assertNotIn('id: "sqlite"', panel)
        self.assertNotIn('value="sqlite"', panel)

    def test_banner_mentions_local_catalog(self):
        en = (Path(__file__).resolve().parents[2] / "hmi" / "src" / "locales" / "en.json").read_text(
            encoding="utf-8"
        )
        self.assertIn("local catalog", en.lower())

    def test_user_management_not_remote_db_gated(self):
        routes = (
            Path(__file__).resolve().parents[2]
            / "hmi"
            / "src"
            / "config"
            / "dbDependentRoutes.ts"
        ).read_text(encoding="utf-8")
        self.assertNotIn('"/user-management"', routes)

    def test_ops_admin_access_includes_supervisor(self):
        access = (
            Path(__file__).resolve().parents[2] / "hmi" / "src" / "utils" / "access.ts"
        ).read_text(encoding="utf-8")
        self.assertIn('"admin"', access)
        self.assertIn('"supervisor"', access)
        self.assertIn('"sudo"', access)
        sidebar = (
            Path(__file__).resolve().parents[2] / "hmi" / "src" / "layouts" / "Sidebar.tsx"
        ).read_text(encoding="utf-8")
        self.assertIn("canViewSettings", sidebar)
        self.assertIn("canViewUserManagement", sidebar)


class TestApiSqliteRejected(unittest.TestCase):
    """CA-CATALOG-11 API"""

    def test_connect_rejects_sqlite(self):
        from unittest.mock import patch

        from automation.modules.database.resources import database as db_res

        resource = db_res.DatabaseConnectResource()
        fake_payload = {
            "dbtype": "sqlite",
            "dbfile": "app.db",
        }
        with patch.object(db_res, "api") as mock_api:
            mock_api.payload = fake_payload
            body, status = resource.post()
        self.assertEqual(status, 400)
        self.assertIn("SQLite", body.get("message", ""))


class TestRuntimeDbLayout(unittest.TestCase):
    def test_ensure_runtime_db_layout_creates_tree(self):
        import tempfile
        from pathlib import Path
        from automation import PyAutomation

        with tempfile.TemporaryDirectory() as tmp:
            cwd = Path.cwd()
            try:
                os.chdir(tmp)
                app = PyAutomation()
                root = app.ensure_runtime_db_layout()
                self.assertTrue(Path(root).is_dir())
                self.assertTrue((Path(root) / "saf").is_dir())
                self.assertTrue((Path(root) / "backups").is_dir())
                self.assertIsNone(app.get_db_config())
                app.set_db_config(
                    dbtype="postgresql",
                    user="u",
                    password="p",
                    host="127.0.0.1",
                    port=5432,
                    name="app_db",
                )
                self.assertTrue((Path(root) / "db_config.json").is_file())
                cfg = app.get_db_config()
                self.assertEqual(cfg.get("dbtype"), "postgresql")
            finally:
                os.chdir(cwd)


class TestCatalogIdentity(unittest.TestCase):
    """Natural-key sync + FK remap (reconnect after offline)."""

    def test_identity_and_fk_remap_for_push(self):
        from automation.catalog.identity import (
            identity_key,
            index_by_identity,
            prepare_push_row,
        )

        local_roles = [{"_pk": "1", "id": 1, "name": "SUDO", "level": 0}]
        remote_roles = [{"_pk": "99", "id": 99, "name": "SUDO", "level": 0}]
        local_users = [
            {
                "_pk": "2",
                "id": 2,
                "username": "system",
                "role": 1,
                "role_id": 1,
                "email": "system@intelcon.com",
                "identifier": "abc",
            }
        ]
        local_index = {
            "roles": index_by_identity("roles", local_roles),
            "users": index_by_identity("users", local_users),
        }
        remote_index = {
            "roles": index_by_identity("roles", remote_roles),
            "users": {},
        }
        self.assertEqual(identity_key("users", local_users[0]), "SYSTEM")
        payload = prepare_push_row(
            "users",
            local_users[0],
            local_index=local_index,
            remote_index=remote_index,
        )
        self.assertEqual(int(payload.get("role") or payload.get("role_id")), 99)
        self.assertNotEqual(str(payload.get("_pk") or ""), "2")

    def test_identity_matches_same_tag_across_pks(self):
        from automation.catalog.identity import identity_key

        local = {"_pk": "24", "identifier": "6ba65fb2", "name": "Supe.Linea1.FI_02"}
        remote = {"_pk": "900", "identifier": "6ba65fb2", "name": "Supe.Linea1.FI_02"}
        self.assertEqual(identity_key("tags", local), identity_key("tags", remote))

    def test_units_upsert_keeps_mm_and_Mm_distinct(self):
        from peewee import CharField, Model, SqliteDatabase

        from automation.catalog.identity import identity_key
        from automation.catalog.rows import upsert_model

        mm = {"name": "mm", "unit": "mm"}
        mega = {"name": "Mm", "unit": "Mm"}
        self.assertEqual(identity_key("units", mm), "mm")
        self.assertEqual(identity_key("units", mega), "Mm")
        self.assertNotEqual(identity_key("units", mm), identity_key("units", mega))

        db = SqliteDatabase(":memory:")

        class UnitsProbe(Model):
            name = CharField(unique=True)
            unit = CharField(unique=True)

            class Meta:
                database = db
                table_name = "units"

        db.connect()
        db.create_tables([UnitsProbe])
        try:
            a = upsert_model(UnitsProbe, mm)
            b = upsert_model(UnitsProbe, mega)
            self.assertNotEqual(a.id, b.id)
            again = upsert_model(UnitsProbe, mm)
            self.assertEqual(again.id, a.id)
            self.assertEqual(UnitsProbe.select().count(), 2)
        finally:
            db.close()

    def test_upsert_model_bypasses_custom_create(self):
        """Historian dbmodels override create(); catalog sync must use ORM insert."""
        from peewee import CharField, FloatField, IntegerField, Model, SqliteDatabase

        from automation.catalog.rows import upsert_model

        db = SqliteDatabase(":memory:")

        class MachinesProbe(Model):
            identifier = CharField(unique=True)
            name = CharField(unique=True)
            interval = FloatField()
            execution_interval = FloatField(null=True)
            description = CharField(null=True)
            classification = CharField(null=True)
            buffer_size = IntegerField(null=True)
            buffer_roll_type = CharField(null=True)
            criticity = IntegerField(null=True)
            priority = IntegerField(null=True)

            class Meta:
                database = db
                table_name = "machines"

            @classmethod
            def create(cls, *args, **kwargs):
                raise TypeError(
                    "Machines.create() got an unexpected keyword argument 'execution_interval'"
                )

        db.connect()
        db.create_tables([MachinesProbe])
        try:
            inst = upsert_model(
                MachinesProbe,
                {
                    "identifier": "m1",
                    "name": "Linea1",
                    "interval": 1.0,
                    "execution_interval": 2.5,
                    "description": "d",
                    "classification": "c",
                    "buffer_size": 10,
                    "buffer_roll_type": "fifo",
                    "criticity": 1,
                    "priority": 1,
                },
            )
            self.assertIsNotNone(inst.id)
            self.assertEqual(inst.execution_interval, 2.5)
            # Update by unique name must not call custom create either.
            again = upsert_model(
                MachinesProbe,
                {
                    "name": "Linea1",
                    "identifier": "m1",
                    "interval": 3.0,
                    "execution_interval": 3.0,
                },
            )
            self.assertEqual(again.id, inst.id)
            self.assertEqual(again.interval, 3.0)
        finally:
            db.close()

    def test_upsert_model_updates_opcuaserver_by_namespace(self):
        from peewee import CharField, Model, SqliteDatabase

        from automation.catalog.rows import upsert_model

        db = SqliteDatabase(":memory:")

        class OPCUAServerProbe(Model):
            name = CharField(unique=True)
            namespace = CharField(unique=True)

            class Meta:
                database = db
                table_name = "opcuaserver"

            @classmethod
            def create(cls, *args, **kwargs):
                return None

        db.connect()
        db.create_tables([OPCUAServerProbe])
        try:
            first = OPCUAServerProbe(name="TagA", namespace="ns=2;s=old")
            first.save(force_insert=True)
            updated = upsert_model(
                OPCUAServerProbe,
                {"name": "TagA", "namespace": "ns=2;s=old"},
            )
            self.assertEqual(updated.id, first.id)
            # Same name, new namespace → update existing name row (unique name).
            moved = upsert_model(
                OPCUAServerProbe,
                {"name": "TagA", "namespace": "ns=2;s=new"},
            )
            self.assertEqual(moved.id, first.id)
            self.assertEqual(moved.namespace, "ns=2;s=new")
        finally:
            db.close()


class TestSoakDocumented(unittest.TestCase):
    def test_runbook_exists(self):
        runbook = Path(__file__).resolve().parents[2] / "docs" / "catalog-sqlite-runbook.md"
        self.assertTrue(runbook.is_file())
        text = runbook.read_text(encoding="utf-8")
        self.assertIn("CA-CATALOG-07", text)
        self.assertIn("CA-CATALOG-14", text)

    @unittest.skip("Soak 24 h de planta — docs/catalog-sqlite-runbook.md")
    def test_ca_catalog_07_hot_path(self):
        self.fail("plant soak")

    @unittest.skip("Soak 24 h de planta — docs/catalog-sqlite-runbook.md")
    def test_ca_catalog_14_multi_edge(self):
        self.fail("plant soak")


if __name__ == "__main__":
    unittest.main()
