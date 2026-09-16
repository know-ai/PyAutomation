# -*- coding: utf-8 -*-
"""GATE-37: docker restart of local PG (app_db) preserves 1M seed rows."""
from __future__ import annotations

import subprocess
import time
import unittest

import psycopg2


class TestPGRestartResilience(unittest.TestCase):
    def test_seed_survives_container_restart(self):
        conn = psycopg2.connect(
            host="127.0.0.1", port=32800, user="postgres", password="postgres", dbname="app_db"
        )
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM alarmsummary")
        before = cur.fetchone()[0]
        conn.close()
        self.assertGreaterEqual(before, 1_000_000)
        subprocess.run(["docker", "restart", "app_db"], check=True)
        deadline = time.time() + 45
        last = None
        while time.time() < deadline:
            try:
                conn = psycopg2.connect(
                    host="127.0.0.1",
                    port=32800,
                    user="postgres",
                    password="postgres",
                    dbname="app_db",
                )
                cur = conn.cursor()
                cur.execute("SELECT COUNT(*) FROM alarmsummary")
                after = cur.fetchone()[0]
                conn.close()
                self.assertEqual(after, before)
                print(f"PG restart OK rows={after}")
                return
            except Exception as exc:
                last = exc
                time.sleep(1.0)
        self.fail(f"PG no reconectó: {last}")
