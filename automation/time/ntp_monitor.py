# -*- coding: utf-8 -*-
"""Lightweight SNTP client (RFC 4330) for clock offset verification — IPv4/IPv6."""
from __future__ import annotations

import socket
import struct
import time
from datetime import datetime, timezone
from typing import Any

NTP_PORT = 123
NTP_EPOCH_OFFSET = 2208988800  # seconds between 1900-01-01 and 1970-01-01
PROTOCOL_VERSION = "NTP/SNTP v4"

_KISS_AUTH_CODES = frozenset({"AUTH", "DENY", "RSTR", "CRYP", "NKEY", "RATE"})


def _ntp_timestamp_to_unix(data: bytes, offset: int) -> float:
    seconds, fraction = struct.unpack("!II", data[offset : offset + 8])
    return (seconds - NTP_EPOCH_OFFSET) + (fraction / 2**32)


def _normalize_host(host: str) -> str:
    raw = str(host or "").strip()
    if raw.startswith("[") and raw.endswith("]"):
        return raw[1:-1].strip()
    return raw


def _family_label(family: int) -> str:
    if family == socket.AF_INET6:
        return "IPv6"
    if family == socket.AF_INET:
        return "IPv4"
    return "unknown"


def _format_address(sockaddr: tuple) -> str:
    if not sockaddr:
        return ""
    host = sockaddr[0]
    if ":" in host and not host.startswith("["):
        return f"[{host}]"
    return host


def _kiss_code(data: bytes) -> str | None:
    if len(data) < 16:
        return None
    if int(data[1]) != 0:
        return None
    refid = data[12:16].decode("ascii", errors="replace").strip("\x00").strip()
    return refid or None


def _is_authentication_rejection(data: bytes) -> bool:
    code = _kiss_code(data)
    if not code:
        return False
    if code in _KISS_AUTH_CODES:
        return True
    return "AUTH" in code.upper()


def _resolve_udp_targets(host: str, family: int = 0) -> list[tuple[int, int, int, tuple]]:
    """Return getaddrinfo results for UDP/123, deduplicated by sockaddr."""
    normalized = _normalize_host(host)
    if not normalized:
        return []
    try:
        infos = socket.getaddrinfo(
            normalized,
            NTP_PORT,
            family=family,
            type=socket.SOCK_DGRAM,
            proto=socket.IPPROTO_UDP,
        )
    except OSError:
        return []
    seen: set[tuple] = set()
    ordered: list[tuple[int, int, int, tuple]] = []
    for info in infos:
        sockaddr = info[4]
        key = (info[0], sockaddr)
        if key in seen:
            continue
        seen.add(key)
        ordered.append(info)
    return ordered


def _query_ntp_at_address(
    sock_family: int,
    sockaddr: tuple,
    timeout: float,
    *,
    host_label: str,
) -> dict[str, Any]:
    sock = None
    used_address = _format_address(sockaddr)
    used_family = _family_label(sock_family)
    try:
        sock = socket.socket(sock_family, socket.SOCK_DGRAM)
        sock.settimeout(timeout)
        packet = b"\x1b" + 47 * b"\0"
        t1 = time.time()
        sock.sendto(packet, sockaddr)
        data, _addr = sock.recvfrom(1024)
        t4 = time.time()
        if len(data) < 48:
            return {
                "success": False,
                "error": f"short NTP response ({len(data)} bytes)",
                "error_details": f"short NTP response ({len(data)} bytes)",
                "server": host_label,
                "used_address": used_address,
                "used_family": used_family,
                "authentication_required": False,
                "protocol_version": PROTOCOL_VERSION,
            }
        if _is_authentication_rejection(data):
            kiss = _kiss_code(data) or "AUTH"
            return {
                "success": False,
                "error": "Authentication required",
                "error_details": f"NTP kiss-o-death: {kiss}",
                "server": host_label,
                "used_address": used_address,
                "used_family": used_family,
                "authentication_required": True,
                "protocol_version": PROTOCOL_VERSION,
            }
        stratum = int(data[1])
        t2 = _ntp_timestamp_to_unix(data, 32)
        t3 = _ntp_timestamp_to_unix(data, 40)
        offset = ((t2 - t1) + (t3 - t4)) / 2.0
        delay = (t4 - t1) - (t3 - t2)
        if delay < 0:
            delay = abs(delay)
        return {
            "success": True,
            "offset_ms": round(offset * 1000.0, 3),
            "delay_ms": round(max(delay, 0.0) * 1000.0, 3),
            "stratum": stratum,
            "server": host_label,
            "used_address": used_address,
            "used_family": used_family,
            "authentication_required": False,
            "protocol_version": PROTOCOL_VERSION,
            "timestamp_utc": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
        }
    except Exception as exc:
        return {
            "success": False,
            "error": str(exc),
            "error_details": str(exc),
            "server": host_label,
            "used_address": used_address,
            "used_family": used_family,
            "authentication_required": False,
            "protocol_version": PROTOCOL_VERSION,
        }
    finally:
        if sock is not None:
            try:
                sock.close()
            except Exception:
                pass


def query_ntp_server(server: str, timeout: float = 2.0, family: int = 0) -> dict[str, Any]:
    """Query an NTP server via SNTP, trying all resolved IPv4/IPv6 addresses.

    Resolves *server* with ``socket.getaddrinfo`` (``family=0`` → dual-stack).
    Tries each address until one responds successfully.
    """
    host = str(server or "").strip()
    if not host:
        return {
            "success": False,
            "error": "empty server",
            "error_details": "empty server",
            "server": server,
            "authentication_required": False,
            "protocol_version": PROTOCOL_VERSION,
        }

    targets = _resolve_udp_targets(host, family=family)
    if not targets:
        # Literal IP without DNS — try direct connect for v4/v6 literals
        for sock_family in (socket.AF_INET, socket.AF_INET6):
            if family not in (0, sock_family):
                continue
            normalized = _normalize_host(host)
            try:
                sockaddr = (normalized, NTP_PORT)
                if sock_family == socket.AF_INET6 and ":" in normalized:
                    result = _query_ntp_at_address(
                        socket.AF_INET6, (normalized, NTP_PORT, 0, 0), timeout, host_label=host
                    )
                elif sock_family == socket.AF_INET and ":" not in normalized:
                    result = _query_ntp_at_address(
                        socket.AF_INET, (normalized, NTP_PORT), timeout, host_label=host
                    )
                else:
                    continue
                if result.get("success") or result.get("authentication_required"):
                    return result
            except OSError:
                continue
        return {
            "success": False,
            "error": f"could not resolve NTP host: {host}",
            "error_details": f"could not resolve NTP host: {host}",
            "server": host,
            "authentication_required": False,
            "protocol_version": PROTOCOL_VERSION,
        }

    last_error = None
    last_details = None
    auth_seen = False
    for info in targets:
        sock_family = info[0]
        sockaddr = info[4]
        if sock_family == socket.AF_INET6 and len(sockaddr) >= 4:
            addr = (sockaddr[0], sockaddr[1], sockaddr[2], sockaddr[3])
        else:
            addr = (sockaddr[0], sockaddr[1])
        result = _query_ntp_at_address(sock_family, addr, timeout, host_label=host)
        if result.get("success"):
            return result
        if result.get("authentication_required"):
            auth_seen = True
            return result
        last_error = result.get("error")
        last_details = result.get("error_details")

    return {
        "success": False,
        "error": last_error or "all addresses failed",
        "error_details": last_details or last_error or "all addresses failed",
        "server": host,
        "authentication_required": auth_seen,
        "protocol_version": PROTOCOL_VERSION,
    }
