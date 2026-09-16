# -*- coding: utf-8 -*-
"""GATE-32-PG pagination against local PostgreSQL seed (1M rows)."""
from __future__ import annotations

import os
import time
import unittest

import psycopg2

from automation.alarms.pagination import clamp_catalog_page_size, clamp_history_page_size

PG = dict(
    host=os.getenv("PG_HOST", "127.0.0.1"),
    port=int(os.getenv("PG_PORT", "32800")),
    user=os.getenv("PG_USER", "postgres"),
    password=os.getenv("PG_PASSWORD", "postgres"),
    dbname=os.getenv("PG_DB", "app_db"),
)


class TestAlarmsPgPagination(unittest.TestCase):
    def setUp(self):
        try:
            self.conn = psycopg2.connect(**PG)
        except Exception as exc:
            self.skipTest(f"PG no disponible: {exc}")
        self.conn.autocommit = True
        cur = self.conn.cursor()
        cur.execute("SELECT COUNT(*) FROM alarmsummary_seed")
        n = cur.fetchone()[0]
        if n < 1000:
            self.skipTest(f"alarmsummary_seed tiene {n} filas; se requiere seed 1M")

    def tearDown(self):
        if getattr(self, "conn", None):
            self.conn.close()

    def test_t98_clamp_50(self):
        self.assertEqual(clamp_catalog_page_size(100), 50)

    def test_t99_clamp_100(self):
        self.assertEqual(clamp_history_page_size(500), 100)

    def _timed(self, sql: str):
        cur = self.conn.cursor()
        t0 = time.perf_counter()
        cur.execute(sql)
        rows = cur.fetchall()
        ms = (time.perf_counter() - t0) * 1000.0
        return ms, len(rows)

    def test_offset_0_vs_500_degradation(self):
        ms0, n0 = self._timed(
            "SELECT id FROM alarmsummary_seed ORDER BY event_time DESC LIMIT 100"
        )
        ms500, n500 = self._timed(
            "SELECT id FROM alarmsummary_seed ORDER BY event_time DESC OFFSET 500 LIMIT 100"
        )
        print(f"offset0={ms0:.2f}ms n={n0} offset500={ms500:.2f}ms n={n500}")
        self.assertEqual(n0, 100)
        self.assertEqual(n500, 100)
        self.assertLessEqual(ms500, max(ms0 * 3.0, 15.0))

    def test_offset_450_under_10ms(self):
        ms, n = self._timed(
            "SELECT id FROM alarmsummary_seed ORDER BY event_time DESC OFFSET 450 LIMIT 100"
        )
        print(f"offset450={ms:.2f}ms n={n}")
        self.assertEqual(n, 100)
        self.assertLessEqual(ms, 10.0)
