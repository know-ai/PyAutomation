# -*- coding: utf-8 -*-
"""Background worker that verifies edge clock sync against plant NTP servers."""
from __future__ import annotations

import logging
import threading
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Callable

from .worker import BaseWorker
from ..time.ntp_config import load_ntp_config
from ..time.ntp_monitor import PROTOCOL_VERSION, query_ntp_server
from ..utils.clock_alarms import set_ntp_out_of_sync
from ..utils.system_event_audit import persist_system_event

_LOGGER = logging.getLogger("pyautomation")

_CONSECUTIVE_FAILURE_ALARM = 3
_MANUAL_CHECK_MIN_INTERVAL_S = 60.0
_MAX_RETRIES = 2
_RETRY_BACKOFF_S = (1.0, 2.0)


class NtpMonitorWorker(BaseWorker):
    """Daemon thread; SNTP probes run on the gevent hub threadpool."""

    def __init__(self, config_provider: Callable[[], dict]):
        super().__init__()
        self.name = "NtpMonitorWorker"
        self.daemon = True
        self._config_provider = config_provider
        self._lock = threading.Lock()
        self._state: dict[str, Any] = self._empty_state()
        self._alarm_active = False
        self._was_synced: bool | None = None
        self._previous_offset_ms: float | None = None
        self._last_manual_check = 0.0
        self._config_version = 0

    @staticmethod
    def _empty_state() -> dict[str, Any]:
        return {
            "enabled": False,
            "synced": False,
            "warn": False,
            "offset_ms": None,
            "delay_ms": None,
            "stratum": None,
            "server_used": None,
            "last_check_utc": None,
            "next_check_utc": None,
            "check_interval_s": 3600,
            "warn_offset_ms": 50,
            "alarm_offset_ms": 1000,
            "step_threshold_ms": 2000,
            "fail_closed": False,
            "consecutive_failures": 0,
            "last_error": None,
            "last_address_used": None,
            "auth_required_detected": False,
            "authentication_required": False,
            "jump_detected": False,
            "protocol_version": PROTOCOL_VERSION,
            "host_time_utc": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
        }

    def get_status(self) -> dict[str, Any]:
        with self._lock:
            payload = dict(self._state)
        try:
            from ..node_scope import get_node_scope

            scope = get_node_scope()
            payload["node_id"] = scope.node_id if scope.is_valid else None
        except Exception:
            payload["node_id"] = None
        payload["host_time_utc"] = datetime.now(timezone.utc).isoformat(timespec="milliseconds")
        return payload

    def reconfigure(self) -> None:
        with self._lock:
            self._config_version += 1

    def check_now(self, *, force: bool = False) -> dict[str, Any]:
        if not force:
            now = time.monotonic()
            if now - self._last_manual_check < _MANUAL_CHECK_MIN_INTERVAL_S:
                return {"ok": False, "message": "rate_limited", "status": self.get_status()}
        self._last_manual_check = time.monotonic()
        self._run_check()
        return {"ok": True, "status": self.get_status()}

    def _probe_server(self, server: str, timeout: float) -> dict[str, Any]:
        from ..utils.db_io import run_uncooperative_db_call

        last_result: dict[str, Any] = {
            "success": False,
            "error": "unknown error",
            "server": server,
            "authentication_required": False,
        }
        for attempt in range(_MAX_RETRIES + 1):
            if attempt > 0:
                backoff = _RETRY_BACKOFF_S[min(attempt - 1, len(_RETRY_BACKOFF_S) - 1)]
                time.sleep(backoff)
            try:
                result = run_uncooperative_db_call(
                    lambda host=server: query_ntp_server(host, timeout=timeout),
                    timeout_s=timeout + 2.0,
                )
            except Exception as exc:
                last_result = {
                    "success": False,
                    "error": str(exc),
                    "error_details": str(exc),
                    "server": server,
                    "authentication_required": False,
                }
                continue
            if result.get("success"):
                return result
            last_result = result
            if result.get("authentication_required"):
                return result
        return last_result

    def _query_servers(self, servers: list[str], timeout: float) -> dict[str, Any]:
        last_error = None
        auth_only = True
        for server in servers:
            result = self._probe_server(server, timeout)
            if result.get("success"):
                return result
            if not result.get("authentication_required"):
                auth_only = False
            last_error = result.get("error_details") or result.get("error") or "unknown error"
            if result.get("authentication_required"):
                result.setdefault("auth_only_cycle", auth_only)
                return result
        payload = {
            "success": False,
            "error": last_error or "all servers failed",
            "error_details": last_error or "all servers failed",
            "server": None,
            "authentication_required": False,
            "auth_only_cycle": False,
        }
        return payload

    def _evaluate_sync(self, config: dict, result: dict | None) -> tuple[bool, bool, bool]:
        if result is None or not result.get("success"):
            return False, False, True
        offset = abs(float(result.get("offset_ms") or 0.0))
        warn = offset > float(config.get("ntp_warn_offset_ms", 50))
        alarm = offset > float(config.get("ntp_alarm_offset_ms", 1000))
        synced = not alarm
        return synced, warn, alarm

    def _detect_clock_step(self, config: dict, offset_ms: float | None) -> bool:
        if offset_ms is None:
            return False
        threshold = float(config.get("ntp_step_threshold_ms") or 2000)
        previous = self._previous_offset_ms
        if previous is None:
            return False
        return abs(float(offset_ms) - float(previous)) > threshold

    def _log_step_event(self, offset_ms: float | None, previous: float | None) -> None:
        description = f"Clock step detected: offset_ms={offset_ms} previous={previous}"
        persist_system_event(
            message="NTP clock step detected",
            description=description[:256],
            classification="System",
            priority=3,
            criticity=3,
            plant_wide=False,
        )
        _LOGGER.warning(description)

    def _log_auth_required_event(self, detail: str) -> None:
        persist_system_event(
            message="NTP authentication required",
            description=detail[:256],
            classification="System",
            priority=3,
            criticity=3,
            plant_wide=False,
        )

    def _apply_fail_closed(self, config: dict, critical: bool) -> None:
        if not config.get("ntp_fail_closed"):
            return
        try:
            from automation import PyAutomation

            app = PyAutomation()
            if critical:
                if app.acquisition_ready:
                    app.acquisition_ready = False
                    app.acquisition_blocked_reason = "clock_unsync"
            elif app.acquisition_blocked_reason == "clock_unsync":
                scope = getattr(app, "node_scope", None)
                if scope is not None and scope.is_valid:
                    app.acquisition_ready = True
                    app.acquisition_blocked_reason = None
        except Exception:
            _LOGGER.debug("fail-closed clock policy skipped", exc_info=True)

    def _persist_node_status(self, synced: bool, offset_ms: float | None) -> None:
        try:
            from automation import PyAutomation

            app = PyAutomation()
            if not app.is_db_connected():
                return
            scope = getattr(app, "node_scope", None)
            if scope is None or not scope.is_valid:
                return
            app.db_manager.update_node_clock_status(
                node_id=scope.node_id,
                ntp_synced=synced,
                ntp_offset_ms=offset_ms,
            )
        except Exception:
            _LOGGER.debug("node NTP status persist skipped", exc_info=True)

    def _emit_transition_event(self, synced: bool, offset_ms: float | None, detail: str) -> None:
        if self._was_synced is None:
            self._was_synced = synced
            return
        if synced == self._was_synced:
            return
        if synced:
            message = "NTP sync restored"
            description = f"Edge clock synchronized. offset_ms={offset_ms}"
        else:
            message = "NTP sync lost"
            description = detail[:256]
        persist_system_event(
            message=message,
            description=description,
            classification="System",
            priority=2 if synced else 3,
            criticity=2 if synced else 4,
            plant_wide=False,
        )
        self._was_synced = synced

    def _run_check(self) -> None:
        config = load_ntp_config(self._config_provider())
        now = datetime.now(timezone.utc)
        interval = int(config.get("ntp_check_interval_s") or 3600)
        servers = list(config.get("ntp_servers_list") or [])
        enabled = bool(config.get("effective_enabled"))

        if not enabled:
            with self._lock:
                self._state = self._empty_state()
                self._state.update(
                    {
                        "enabled": False,
                        "check_interval_s": interval,
                        "warn_offset_ms": config.get("ntp_warn_offset_ms"),
                        "alarm_offset_ms": config.get("ntp_alarm_offset_ms"),
                        "step_threshold_ms": config.get("ntp_step_threshold_ms"),
                        "fail_closed": bool(config.get("ntp_fail_closed")),
                        "next_check_utc": (now + timedelta(seconds=interval)).isoformat(timespec="milliseconds"),
                    }
                )
            set_ntp_out_of_sync(False)
            self._alarm_active = False
            self._apply_fail_closed(config, False)
            return

        result = self._query_servers(servers, timeout=2.0)
        auth_required = bool(result.get("authentication_required"))
        success = bool(result.get("success"))
        offset_ms = result.get("offset_ms") if success else None
        jump_detected = False
        if success and offset_ms is not None:
            previous = self._previous_offset_ms
            jump_detected = self._detect_clock_step(config, float(offset_ms))
            if jump_detected:
                self._log_step_event(offset_ms, previous)
            self._previous_offset_ms = float(offset_ms)

        with self._lock:
            prev_failures = int(self._state.get("consecutive_failures") or 0)
            if auth_required:
                failures = prev_failures
            elif success:
                failures = 0
            else:
                failures = prev_failures + 1

            synced, warn, alarm = self._evaluate_sync(config, result if success else None)
            if auth_required:
                alarm = False
                synced = bool(self._state.get("synced")) if self._state.get("offset_ms") is not None else False
            elif not success and failures >= _CONSECUTIVE_FAILURE_ALARM:
                synced = False
                alarm = True

            if not success:
                offset_ms = self._state.get("offset_ms")

            self._state.update(
                {
                    "enabled": True,
                    "synced": synced,
                    "warn": warn and synced,
                    "offset_ms": offset_ms,
                    "delay_ms": result.get("delay_ms"),
                    "stratum": result.get("stratum"),
                    "server_used": result.get("server"),
                    "last_check_utc": now.isoformat(timespec="milliseconds"),
                    "next_check_utc": (now + timedelta(seconds=interval)).isoformat(timespec="milliseconds"),
                    "check_interval_s": interval,
                    "warn_offset_ms": config.get("ntp_warn_offset_ms"),
                    "alarm_offset_ms": config.get("ntp_alarm_offset_ms"),
                    "step_threshold_ms": config.get("ntp_step_threshold_ms"),
                    "fail_closed": bool(config.get("ntp_fail_closed")),
                    "consecutive_failures": failures,
                    "last_error": None if success else (result.get("error_details") or result.get("error")),
                    "last_address_used": result.get("used_address"),
                    "auth_required_detected": auth_required,
                    "authentication_required": auth_required,
                    "jump_detected": jump_detected,
                    "protocol_version": result.get("protocol_version") or PROTOCOL_VERSION,
                }
            )

        if auth_required:
            self._log_auth_required_event(
                str(result.get("error_details") or result.get("error") or "authentication required")
            )

        set_ntp_out_of_sync(alarm)
        self._alarm_active = alarm
        detail = (
            f"offset_ms={offset_ms}"
            if success
            else f"NTP check failed: {result.get('error')}"
        )
        if not auth_required:
            self._emit_transition_event(synced, offset_ms, detail)
            self._persist_node_status(synced, offset_ms)
            self._apply_fail_closed(config, alarm)

        if not success and not auth_required and failures >= _CONSECUTIVE_FAILURE_ALARM:
            persist_system_event(
                message="NTP check failed",
                description=str(result.get("error_details") or result.get("error") or "all servers failed")[:256],
                classification="System",
                priority=3,
                criticity=4,
                plant_wide=False,
            )

    def run(self) -> None:
        _LOGGER.info("NtpMonitorWorker started")
        while True:
            cycle_started = time.monotonic()
            try:
                self._run_check()
            except Exception:
                _LOGGER.error("NTP monitor cycle failed", exc_info=True)
            if self.stop_event.is_set():
                _LOGGER.info("NtpMonitorWorker stopped")
                break
            config = load_ntp_config(self._config_provider())
            interval = float(config.get("ntp_check_interval_s") or 3600)
            elapsed = time.monotonic() - cycle_started
            sleep_s = max(1.0, min(interval, interval - elapsed))
            if self.stop_event.wait(timeout=sleep_s):
                _LOGGER.info("NtpMonitorWorker stopped")
                break
