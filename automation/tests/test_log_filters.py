# -*- coding: utf-8 -*-
"""DedupeFilter: cooldown, bounded cache, ERROR rate window."""
from __future__ import annotations

import logging
import time
import unittest

from ..utils.log_filters import DedupeFilter


class TestDedupeFilter(unittest.TestCase):
    def _record(self, msg="boom", level=logging.ERROR, lineno=10):
        return logging.LogRecord(
            name="pyautomation",
            level=level,
            pathname="/app/core.py",
            lineno=lineno,
            msg=msg,
            args=(),
            exc_info=None,
            func="while_pre_alarming",
        )

    def test_repeated_error_is_dropped_inside_cooldown(self):
        filt = DedupeFilter(cooldown_sec=60, max_entries=16)
        rec = self._record()
        self.assertTrue(filt.filter(rec))
        self.assertFalse(filt.filter(rec))
        self.assertFalse(filt.filter(rec))
        self.assertEqual(filt.dropped, 2)
        self.assertGreaterEqual(filt.error_rate_per_min(), 3)

    def test_cooldown_zero_disables_suppression(self):
        filt = DedupeFilter(cooldown_sec=0)
        rec = self._record()
        self.assertTrue(filt.filter(rec))
        self.assertTrue(filt.filter(rec))
        self.assertEqual(filt.dropped, 0)

    def test_distinct_messages_are_independent(self):
        filt = DedupeFilter(cooldown_sec=60)
        self.assertTrue(filt.filter(self._record("a")))
        self.assertTrue(filt.filter(self._record("b")))
        self.assertFalse(filt.filter(self._record("a")))

    def test_info_is_not_counted_as_error_rate(self):
        filt = DedupeFilter(cooldown_sec=60)
        self.assertTrue(filt.filter(self._record(level=logging.INFO)))
        self.assertEqual(filt.error_rate_per_min(), 0.0)

    def test_cache_is_bounded(self):
        filt = DedupeFilter(cooldown_sec=60, max_entries=8)
        for i in range(40):
            filt.filter(self._record(msg=f"e{i}", lineno=i))
        self.assertLessEqual(len(filt._last), 8)

    def test_snapshot_alerts_above_threshold(self):
        filt = DedupeFilter(cooldown_sec=0, alert_per_min=5)
        rec = self._record()
        for _ in range(6):
            filt.filter(rec)
        snap = filt.snapshot()
        self.assertTrue(snap["LOG_ERROR_ALERT"])
        self.assertGreaterEqual(snap["LOG_ERROR_RATE_PER_MIN"], 6)

    def test_expired_cooldown_allows_again(self):
        filt = DedupeFilter(cooldown_sec=0.05)
        rec = self._record()
        self.assertTrue(filt.filter(rec))
        self.assertFalse(filt.filter(rec))
        time.sleep(0.06)
        self.assertTrue(filt.filter(self._record()))

    def test_reemit_annotates_suppressed_repeats(self):
        filt = DedupeFilter(cooldown_sec=0.05)
        self.assertTrue(filt.filter(self._record()))
        self.assertFalse(filt.filter(self._record()))
        self.assertFalse(filt.filter(self._record()))
        time.sleep(0.06)
        rec = self._record()
        self.assertTrue(filt.filter(rec))
        self.assertIn("repeated 2 times", rec.getMessage())


class TestValidateTypesLogging(unittest.TestCase):
    def test_output_mismatch_does_not_print(self):
        import io
        from contextlib import redirect_stdout

        from ..utils.decorators import validate_types

        @validate_types(output=str)
        def _bad():
            return None

        buf = io.StringIO()
        with self.assertLogs("pyautomation", level="ERROR"):
            with redirect_stdout(buf):
                with self.assertRaises(TypeError):
                    _bad()
        self.assertEqual(buf.getvalue(), "")


if __name__ == "__main__":
    unittest.main()
