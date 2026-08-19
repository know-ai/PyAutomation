# -*- coding: utf-8 -*-
"""Tests for NTP monitor (CA-NTP)."""
from __future__ import annotations

import socket
import struct
import time
import unittest
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from automation.time.ntp_config import load_ntp_config, parse_server_list, validate_server_list
from automation.time.ntp_monitor import NTP_EPOCH_OFFSET, query_ntp_server
from automation.workers.ntp_monitor import NtpMonitorWorker, _CONSECUTIVE_FAILURE_ALARM, _MAX_RETRIES


def _build_ntp_response(
    *,
    stratum: int = 2,
    t2_unix: float | None = None,
    t3_unix: float | None = None,
    refid: bytes = b"GPS ",
) -> bytes:
    now = time.time()
    t2 = t2_unix if t2_unix is not None else now
    t3 = t3_unix if t3_unix is not None else now
    packet = bytearray(48)
    packet[0] = 0x1C
    packet[1] = stratum
    packet[12:16] = refid.ljust(4)[:4]
    for offset, value in ((32, t2), (40, t3)):
        seconds = int(value + NTP_EPOCH_OFFSET)
        fraction = int((value - int(value)) * 2**32)
        struct.pack_into("!II", packet, offset, seconds, fraction)
    return bytes(packet)


def _mock_getaddrinfo_v4(host, port, family=0, type=None, proto=None):
    return [(socket.AF_INET, socket.SOCK_DGRAM, 17, "", ("127.0.0.1", port))]


def _mock_getaddrinfo_v6_then_v4(host, port, family=0, type=None, proto=None):
    return [
        (socket.AF_INET6, socket.SOCK_DGRAM, 17, "", ("::1", port, 0, 0)),
        (socket.AF_INET, socket.SOCK_DGRAM, 17, "", ("127.0.0.1", port)),
    ]


class TestNtpConfig(unittest.TestCase):
    def test_parse_server_list_deduplicates(self):
        servers = parse_server_list("ntp1.local, ntp2.local, ntp1.local")
        self.assertEqual(servers, ["ntp1.local", "ntp2.local"])

    def test_validate_server_list_rejects_invalid(self):
        ok, err = validate_server_list(["bad host"])
        self.assertFalse(ok)
        self.assertIn("Invalid", err or "")

    def test_validate_server_list_accepts_ipv6(self):
        ok, err = validate_server_list(["[2001:db8::1]", "2001:db8::2"])
        self.assertTrue(ok)
        self.assertIsNone(err)

    def test_load_ntp_config_persisted_beats_env(self):
        with patch.dict(
            "os.environ",
            {
                "AUTOMATION_NTP_SERVERS": "ntp.env.local",
                "AUTOMATION_NTP_CHECK_INTERVAL_S": "120",
            },
            clear=False,
        ):
            cfg = load_ntp_config(
                {
                    "ntp_servers": "ntp.hmi.local",
                    "ntp_check_interval_s": 3600,
                }
            )
        self.assertEqual(cfg["ntp_servers_list"], ["ntp.hmi.local"])
        self.assertEqual(cfg["ntp_check_interval_s"], 3600)

    def test_load_ntp_config_step_threshold(self):
        cfg = load_ntp_config({"ntp_step_threshold_ms": 1500})
        self.assertEqual(cfg["ntp_step_threshold_ms"], 1500)


class TestNtpMonitorQuery(unittest.TestCase):
    def _fake_socket_factory(self, response: bytes | None, *, fail_first: bool = False):
        calls = {"n": 0}

        class FakeSocket:
            def __init__(self, *args, **kwargs):
                self.timeout = None

            def settimeout(self, value):
                self.timeout = value

            def sendto(self, packet, addr):
                self._addr = addr

            def recvfrom(self, size):
                calls["n"] += 1
                if fail_first and calls["n"] == 1:
                    raise TimeoutError("timed out")
                if response is None:
                    raise OSError("network unreachable")
                return response, self._addr

            def close(self):
                pass

        return FakeSocket

    def test_query_ntp_server_success(self):
        response = _build_ntp_response()
        with patch("automation.time.ntp_monitor.socket.getaddrinfo", _mock_getaddrinfo_v4):
            with patch(
                "automation.time.ntp_monitor.socket.socket",
                self._fake_socket_factory(response),
            ):
                result = query_ntp_server("127.0.0.1", timeout=1.0)
        self.assertTrue(result["success"])
        self.assertIsNotNone(result["offset_ms"])
        self.assertEqual(result["stratum"], 2)
        self.assertEqual(result["used_family"], "IPv4")

    def test_ca_ntp_14_ipv6_success(self):
        response = _build_ntp_response()

        def v6_only(host, port, family=0, type=None, proto=None):
            return [(socket.AF_INET6, socket.SOCK_DGRAM, 17, "", ("::1", port, 0, 0))]

        with patch("automation.time.ntp_monitor.socket.getaddrinfo", v6_only):
            with patch(
                "automation.time.ntp_monitor.socket.socket",
                self._fake_socket_factory(response),
            ):
                result = query_ntp_server("ntp6.local", timeout=1.0)
        self.assertTrue(result["success"])
        self.assertEqual(result["used_family"], "IPv6")

    def test_ca_ntp_15_ipv6_fail_ipv4_success(self):
        response = _build_ntp_response()
        attempts = {"v6": 0, "v4": 0}

        class FamilyAwareSocket:
            def __init__(self, family, *args, **kwargs):
                self.family = family
                self.timeout = None

            def settimeout(self, value):
                self.timeout = value

            def sendto(self, packet, addr):
                self._addr = addr

            def recvfrom(self, size):
                if self.family == socket.AF_INET6:
                    attempts["v6"] += 1
                    raise TimeoutError("ipv6 timeout")
                attempts["v4"] += 1
                return response, self._addr

            def close(self):
                pass

        def socket_factory(family, *args, **kwargs):
            return FamilyAwareSocket(family)

        with patch("automation.time.ntp_monitor.socket.getaddrinfo", _mock_getaddrinfo_v6_then_v4):
            with patch("automation.time.ntp_monitor.socket.socket", side_effect=socket_factory):
                result = query_ntp_server("dual.local", timeout=1.0)
        self.assertTrue(result["success"])
        self.assertEqual(result["used_family"], "IPv4")
        self.assertGreaterEqual(attempts["v6"], 1)
        self.assertGreaterEqual(attempts["v4"], 1)

    def test_query_ntp_server_auth_rejection(self):
        response = _build_ntp_response(stratum=0, refid=b"AUTH")
        with patch("automation.time.ntp_monitor.socket.getaddrinfo", _mock_getaddrinfo_v4):
            with patch(
                "automation.time.ntp_monitor.socket.socket",
                self._fake_socket_factory(response),
            ):
                result = query_ntp_server("127.0.0.1", timeout=1.0)
        self.assertFalse(result["success"])
        self.assertTrue(result["authentication_required"])

    def test_query_ntp_server_failure(self):
        with patch("automation.time.ntp_monitor.socket.getaddrinfo", _mock_getaddrinfo_v4):
            with patch(
                "automation.time.ntp_monitor.socket.socket",
                self._fake_socket_factory(None),
            ):
                result = query_ntp_server("127.0.0.1", timeout=1.0)
        self.assertFalse(result["success"])
        self.assertIn("error", result)


class TestNtpMonitorWorker(unittest.TestCase):
    def _worker(self, config: dict) -> NtpMonitorWorker:
        return NtpMonitorWorker(config_provider=lambda: config)

    def test_ca_ntp_02_disabled_without_servers(self):
        worker = self._worker({"ntp_enabled": True, "ntp_servers": ""})
        worker._run_check()
        status = worker.get_status()
        self.assertFalse(status["enabled"])

    @patch("automation.workers.ntp_monitor.set_ntp_out_of_sync")
    def test_ca_ntp_01_alarm_on_large_offset(self, mock_alarm):
        worker = self._worker(
            {
                "ntp_enabled": True,
                "ntp_servers": "ntp.local",
                "ntp_alarm_offset_ms": 100,
            }
        )
        worker._query_servers = MagicMock(
            return_value={
                "success": True,
                "offset_ms": 500.0,
                "delay_ms": 1.0,
                "stratum": 2,
                "server": "ntp.local",
                "used_address": "127.0.0.1",
            }
        )
        worker._run_check()
        status = worker.get_status()
        self.assertFalse(status["synced"])
        mock_alarm.assert_called_with(True)

    @patch("automation.workers.ntp_monitor.set_ntp_out_of_sync")
    @patch("automation.workers.ntp_monitor.persist_system_event")
    def test_ca_ntp_05_consecutive_failures(self, mock_event, mock_alarm):
        worker = self._worker(
            {
                "ntp_enabled": True,
                "ntp_servers": "ntp.local",
            }
        )
        worker._state["consecutive_failures"] = _CONSECUTIVE_FAILURE_ALARM - 1
        worker._query_servers = MagicMock(
            return_value={"success": False, "error": "timeout", "server": "ntp.local"}
        )
        worker._run_check()
        status = worker.get_status()
        self.assertFalse(status["synced"])
        mock_alarm.assert_called_with(True)
        mock_event.assert_called()

    @patch("automation.workers.ntp_monitor.set_ntp_out_of_sync")
    @patch("automation.workers.ntp_monitor.persist_system_event")
    def test_ca_ntp_06_transition_events(self, mock_event, mock_alarm):
        worker = self._worker(
            {
                "ntp_enabled": True,
                "ntp_servers": "ntp.local",
                "ntp_alarm_offset_ms": 1000,
            }
        )
        worker._query_servers = MagicMock(
            return_value={
                "success": True,
                "offset_ms": 10.0,
                "delay_ms": 1.0,
                "stratum": 2,
                "server": "ntp.local",
            }
        )
        worker._run_check()
        self.assertFalse(mock_event.called)
        worker._query_servers = MagicMock(
            return_value={
                "success": True,
                "offset_ms": 1500.0,
                "delay_ms": 1.0,
                "stratum": 2,
                "server": "ntp.local",
            }
        )
        worker._run_check()
        self.assertTrue(mock_event.called)

    @patch("automation.workers.ntp_monitor.time.sleep")
    @patch("automation.workers.ntp_monitor.set_ntp_out_of_sync")
    def test_ca_ntp_16_failover_second_server(self, mock_alarm, mock_sleep):
        worker = self._worker({"ntp_enabled": True, "ntp_servers": "bad.local,good.local"})
        worker._probe_server = MagicMock(
            side_effect=[
                {"success": False, "error": "timeout", "server": "bad.local"},
                {
                    "success": True,
                    "offset_ms": 5.0,
                    "delay_ms": 1.0,
                    "stratum": 2,
                    "server": "good.local",
                    "used_address": "10.0.0.2",
                },
            ]
        )
        worker._run_check()
        status = worker.get_status()
        self.assertTrue(status["synced"])
        self.assertEqual(status["server_used"], "good.local")
        mock_alarm.assert_called_with(False)

    @patch("automation.workers.ntp_monitor.time.sleep")
    @patch("automation.workers.ntp_monitor.set_ntp_out_of_sync")
    def test_ca_ntp_17_retries_with_backoff(self, mock_alarm, mock_sleep):
        worker = self._worker({"ntp_enabled": True, "ntp_servers": "ntp.local"})
        worker._probe_server = MagicMock(
            return_value={"success": False, "error": "timeout", "server": "ntp.local"}
        )
        for _ in range(_CONSECUTIVE_FAILURE_ALARM):
            worker._run_check()
        status = worker.get_status()
        self.assertFalse(status["synced"])
        self.assertGreaterEqual(worker._probe_server.call_count, _CONSECUTIVE_FAILURE_ALARM)
        mock_alarm.assert_called_with(True)

    @patch("automation.workers.ntp_monitor.set_ntp_out_of_sync")
    @patch("automation.workers.ntp_monitor.persist_system_event")
    def test_ca_ntp_18_clock_step_without_alarm(self, mock_event, mock_alarm):
        worker = self._worker(
            {
                "ntp_enabled": True,
                "ntp_servers": "ntp.local",
                "ntp_alarm_offset_ms": 5000,
                "ntp_step_threshold_ms": 2000,
            }
        )
        worker._query_servers = MagicMock(
            return_value={
                "success": True,
                "offset_ms": 10.0,
                "delay_ms": 1.0,
                "stratum": 2,
                "server": "ntp.local",
            }
        )
        worker._run_check()
        worker._query_servers = MagicMock(
            return_value={
                "success": True,
                "offset_ms": 3015.0,
                "delay_ms": 1.0,
                "stratum": 2,
                "server": "ntp.local",
            }
        )
        worker._run_check()
        status = worker.get_status()
        self.assertTrue(status["synced"])
        self.assertTrue(status["jump_detected"])
        mock_alarm.assert_called_with(False)
        messages = [call.kwargs.get("message") or call.args[0] for call in mock_event.call_args_list]
        self.assertIn("NTP clock step detected", messages)

    @patch("automation.workers.ntp_monitor.set_ntp_out_of_sync")
    @patch("automation.workers.ntp_monitor.persist_system_event")
    def test_auth_required_no_sync_alarm(self, mock_event, mock_alarm):
        worker = self._worker({"ntp_enabled": True, "ntp_servers": "secure.local"})
        worker._state["synced"] = True
        worker._state["offset_ms"] = 12.0
        worker._query_servers = MagicMock(
            return_value={
                "success": False,
                "error": "Authentication required",
                "authentication_required": True,
                "server": "secure.local",
            }
        )
        worker._run_check()
        status = worker.get_status()
        self.assertTrue(status["auth_required_detected"])
        mock_alarm.assert_called_with(False)
        messages = [call.kwargs.get("message") or call.args[0] for call in mock_event.call_args_list]
        self.assertIn("NTP authentication required", messages)


if __name__ == "__main__":
    unittest.main()
