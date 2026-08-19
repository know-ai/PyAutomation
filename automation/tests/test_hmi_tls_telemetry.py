# -*- coding: utf-8 -*-
"""Tests for debounced HMI TLS telemetry."""
from __future__ import annotations

import ssl
import unittest
from unittest.mock import patch

from automation.utils.hmi_tls_telemetry import (
    is_quiet_client_tls_error,
    record_client_tls_failure,
    reset_for_tests,
)


class TestHmiTlsTelemetry(unittest.TestCase):
    def setUp(self):
        reset_for_tests()

    def test_certificate_unknown_is_quiet(self):
        err = ssl.SSLError(1, "[SSL: SSLV3_ALERT_CERTIFICATE_UNKNOWN] certificate unknown (_ssl.c:992)")
        self.assertTrue(is_quiet_client_tls_error(err))

    def test_debounced_event_emits_once_per_ip(self):
        err = ssl.SSLError(1, "[SSL: SSLV3_ALERT_CERTIFICATE_UNKNOWN] certificate unknown")
        timeline = iter([0.0, 1.0, 2.0, 301.0])
        with patch("automation.utils.hmi_tls_telemetry._IP_RATE_S", 300.0):
            with patch("automation.utils.hmi_tls_telemetry.time.monotonic", lambda: next(timeline)):
                with patch("automation.utils.system_event_audit.persist_system_event") as mock_event:
                    record_client_tls_failure(err, origin="10.0.0.8")
                    record_client_tls_failure(err, origin="10.0.0.8")
                    record_client_tls_failure(err, origin="10.0.0.8")
                    self.assertEqual(mock_event.call_count, 0)
                    record_client_tls_failure(err, origin="10.0.0.8")
                    self.assertEqual(mock_event.call_count, 1)
                    description = mock_event.call_args.kwargs.get("description") or ""
                    self.assertIn("origin=10.0.0.8", description)
                    self.assertIn("count=4", description)

    def test_second_window_can_emit_again_for_same_ip(self):
        err = ssl.SSLError(1, "certificate unknown")
        timeline = iter([0.0, 1.0, 2.0, 301.0, 602.0])
        with patch("automation.utils.hmi_tls_telemetry._IP_RATE_S", 300.0):
            with patch("automation.utils.hmi_tls_telemetry.time.monotonic", lambda: next(timeline)):
                with patch("automation.utils.system_event_audit.persist_system_event") as mock_event:
                    record_client_tls_failure(err, origin="192.168.1.10")
                    record_client_tls_failure(err, origin="192.168.1.10")
                    record_client_tls_failure(err, origin="192.168.1.10")
                    self.assertEqual(mock_event.call_count, 0)
                    record_client_tls_failure(err, origin="192.168.1.10")
                    self.assertEqual(mock_event.call_count, 1)
                    record_client_tls_failure(err, origin="192.168.1.10")
                    self.assertEqual(mock_event.call_count, 2)


if __name__ == "__main__":
    unittest.main()
