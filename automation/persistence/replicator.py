# -*- coding: utf-8 -*-
"""Remote replicator: journal is source of truth; ACK only after remote success.

Never drains PENDING records on failure. Rate-limits recovery. Circuit-breaks
to protect the historian after consecutive faults.
"""
from __future__ import annotations

import json
import logging
import time
from collections import defaultdict
from typing import Any

from .config import SafConfig
from .contracts import IRemoteDB
from .exceptions import ReplicationError
from .journal import JournalWriter
from .records import DOMAIN

_DOMAIN_FLUSH_ORDER = (
    DOMAIN.TAG,
    DOMAIN.ALARM_SUMMARY,
    DOMAIN.ALARM_SUMMARY_UPDATE,
    DOMAIN.EVENT,
    DOMAIN.LOG,
)


def _ordered_domain_batches(grouped: dict[str, list]) -> list[tuple[str, list]]:
    """Flush tag samples before events/logs so history drains under backpressure."""
    ordered: list[tuple[str, list]] = []
    seen: set[str] = set()
    for domain in _DOMAIN_FLUSH_ORDER:
        rows = grouped.get(domain)
        if rows:
            ordered.append((domain, rows))
            seen.add(domain)
    for domain, rows in grouped.items():
        if domain not in seen:
            ordered.append((domain, rows))
    return ordered


def _node_scope():
    try:
        from ..node_scope import get_node_scope

        return get_node_scope()
    except (ImportError, AttributeError):
        return None


_SAF_NTP_MAX_OFFSET_MS = 1000.0


def clock_blocks_replication(status: dict[str, Any] | None) -> str:
    """Keep PENDING (do not ACK) when NTP offset exceeds 1 s.

    Empty string means replication may proceed. NTP disabled or offset still
    unknown does not block (lab / first check). Does not trip the circuit breaker.
    """
    if not status or not status.get("enabled"):
        return ""
    offset = status.get("offset_ms")
    if offset is None:
        return ""
    try:
        abs_ms = abs(float(offset))
    except (TypeError, ValueError):
        return ""
    if abs_ms > _SAF_NTP_MAX_OFFSET_MS:
        return (
            f"clock offset {abs_ms:.1f} ms exceeds "
            f"{_SAF_NTP_MAX_OFFSET_MS:.0f} ms"
        )
    return ""


def _live_clock_status() -> dict[str, Any] | None:
    try:
        from .. import PyAutomation

        worker = getattr(PyAutomation(), "ntp_worker", None)
        if worker is None:
            return None
        return worker.get_status()
    except Exception:
        return None


def _scope_owns_payload(scope, payload: dict[str, Any]) -> bool:
    if scope is None or not getattr(scope, "enabled", False):
        return True
    try:
        owns_area = getattr(scope, "owns_area", None)
        area_owned = (
            bool(owns_area(payload.get("area")))
            if callable(owns_area)
            else payload.get("area") == getattr(scope, "area", None)
        )
        return bool(
            area_owned and scope.owns_node(payload.get("owner_node"))
        )
    except Exception:
        return False


class CircuitBreaker:
    def __init__(self, fail_threshold: int, open_s: float):
        self.fail_threshold = max(1, int(fail_threshold))
        self.open_s = float(open_s)
        self.failures = 0
        self.opened_at = 0.0
        self.state = "closed"

    def allow(self) -> bool:
        if self.state != "open":
            return True
        if (time.monotonic() - self.opened_at) >= self.open_s:
            self.state = "half-open"
            return True
        return False

    def success(self) -> None:
        self.failures = 0
        self.state = "closed"

    def failure(self) -> None:
        self.failures += 1
        if self.failures >= self.fail_threshold:
            self.state = "open"
            self.opened_at = time.monotonic()


class RateLimiter:
    def __init__(self, rate_per_s: int):
        self.rate_per_s = max(1, int(rate_per_s))
        self._window_start = time.monotonic()
        self._used = 0

    def take(self, n: int) -> int:
        now = time.monotonic()
        if now - self._window_start >= 1.0:
            self._window_start = now
            self._used = 0
        remaining = self.rate_per_s - self._used
        granted = max(0, min(int(n), remaining))
        self._used += granted
        return granted


class RemoteReplicator:
    def __init__(self, journal: JournalWriter, remote: IRemoteDB, config: SafConfig | None = None):
        self.journal = journal
        self.remote = remote
        self.config = config or journal.config
        self.circuit = CircuitBreaker(self.config.circuit_fail_threshold, self.config.circuit_open_s)
        self.limiter = RateLimiter(self.config.replicate_rate_per_s)
        self.last_replicated = 0
        self.last_error = ""

    def replicate_once(self) -> int:
        scope = _node_scope()
        if (
            scope is not None
            and getattr(scope, "enabled", False)
            and not getattr(scope, "is_valid", False)
        ):
            self.last_error = "invalid node scope"
            return 0
        if not self.circuit.allow():
            return 0
        reason = clock_blocks_replication(_live_clock_status())
        if reason:
            self.last_error = reason
            return 0
        if not self.remote.is_reachable():
            self.circuit.failure()
            return 0
        allowed = self.limiter.take(self.config.replicate_batch_size)
        if allowed <= 0:
            return 0
        rows = self.journal.fetch_pending(allowed)
        if not rows:
            self.circuit.success()
            self.journal.gc_sent(self.config.gc_sent_after_s, self.config.gc_batch)
            return 0
        owned_rows = []
        foreign_ids = []
        for row in rows:
            payload = _payload(row)
            if _scope_owns_payload(scope, payload):
                owned_rows.append(row)
            else:
                foreign_ids.append(int(row["id"]))
                logging.getLogger("pyautomation").error(
                    "SAF discarded foreign journal row id=%s domain=%s area=%s owner_node=%s",
                    row["id"],
                    row["domain"],
                    payload.get("area"),
                    payload.get("owner_node"),
                )
        if foreign_ids:
            self.journal.mark_sent(foreign_ids)
        rows = owned_rows
        if not rows:
            self.journal.gc_sent(self.config.gc_sent_after_s, self.config.gc_batch)
            return 0
        grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for row in rows:
            grouped[row["domain"]].append(row)
        replicated = 0
        failed_ids: list[int] = []
        last_err = ""
        for domain, domain_rows in _ordered_domain_batches(grouped):
            ids = [int(item["id"]) for item in domain_rows]
            payloads = [_payload(item) for item in domain_rows]
            for payload, source in zip(payloads, domain_rows):
                payload.setdefault("sample_uuid", source.get("idempotency_key"))
                payload.setdefault("idempotency_key", source.get("idempotency_key"))
            self.journal.mark_replicating(ids)
            try:
                outcomes = self._flush_domain_outcomes(domain, payloads)
                sent_ids = [jid for jid, ok in zip(ids, outcomes) if ok]
                failed_batch_ids = [jid for jid, ok in zip(ids, outcomes) if not ok]
                if sent_ids:
                    self.journal.mark_sent(sent_ids)
                    replicated += len(sent_ids)
                if failed_batch_ids:
                    failed_ids.extend(failed_batch_ids)
                    last_err = (
                        f"remote skipped {len(failed_batch_ids)}/{len(ids)} "
                        f"for domain {domain}"
                    )
                    logging.getLogger("pyautomation").error(
                        "SAF replication partial for domain %s: %s/%s kept PENDING",
                        domain,
                        len(failed_batch_ids),
                        len(ids),
                    )
            except Exception as err:
                last_err = str(err)
                failed_ids.extend(ids)
                logging.getLogger("pyautomation").error(
                    "SAF replication failed for domain %s; those rows kept PENDING",
                    domain,
                    exc_info=True,
                )
        if failed_ids:
            self.journal.mark_pending(failed_ids, error=last_err)
            self.last_error = last_err
            if replicated <= 0:
                self.circuit.failure()
            else:
                self.circuit.success()
        else:
            self.circuit.success()
            self.last_error = ""
        self.last_replicated = replicated
        try:
            self.journal.total_replicated = int(getattr(self.journal, "total_replicated", 0) or 0) + int(replicated or 0)
        except Exception:
            pass
        self.journal.gc_sent(self.config.gc_sent_after_s, self.config.gc_batch)
        return replicated

    def flush(self) -> int:
        """ReplicationWorker entry point. No SQL dialects here."""
        return self.replicate_once()

    def _flush_domain_outcomes(self, domain: str, payloads: list[dict[str, Any]]) -> list[bool]:
        writer = getattr(self.remote, "write_batch_outcomes", None)
        if callable(writer):
            return writer(domain, payloads)
        written = self._flush_domain(domain, payloads)
        if written <= 0:
            raise ReplicationError(f"remote wrote 0 rows for domain {domain}")
        return [True] * len(payloads)

    def _flush_domain(self, domain: str, payloads: list[dict[str, Any]]) -> int:
        if domain == "tag":
            return self.remote.batch_insert_with_dedupe(payloads)
        return self.remote.write_batch(domain, payloads)


def _payload(row: dict[str, Any]) -> dict[str, Any]:
    raw = row.get("payload") or "{}"
    if isinstance(raw, dict):
        return raw
    return json.loads(raw)
