# -*- coding: utf-8 -*-
"""Remote replicator: journal is source of truth; ACK only after remote success.

Never drains PENDING records on failure. Rate-limits recovery. Circuit-breaks
to protect the historian after consecutive faults.

Retryable outages keep attempts intact. Only poison payloads may dead-letter.
"""
from __future__ import annotations

import json
import logging
import time
from collections import defaultdict
from typing import Any

from .config import SafConfig
from .contracts import IRemoteDB
from .errors import (
    IDEMPOTENT_OK,
    POISON,
    classify_saf_error,
    normalize_outcomes,
)
from .exceptions import ReplicationError
from .journal import JournalWriter
from .records import DOMAIN, scope_metadata

_DOMAIN_FLUSH_ORDER = (
    DOMAIN.TAG,
    DOMAIN.ALARM_SUMMARY,
    DOMAIN.ALARM_SUMMARY_UPDATE,
    DOMAIN.EVENT,
    DOMAIN.LOG,
    DOMAIN.LEAK,
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


def _stamp_payload_scope(payload: dict[str, Any]) -> dict[str, Any]:
    """Fill missing area/owner_node from the edge scope instead of discarding."""
    area, owner_node = scope_metadata(payload.get("area"), payload.get("owner_node"))
    if not payload.get("area"):
        payload["area"] = area
    if not payload.get("owner_node"):
        payload["owner_node"] = owner_node
    inner = payload.get("payload")
    if isinstance(inner, dict):
        if not inner.get("area"):
            inner["area"] = payload.get("area")
        if not inner.get("owner_node"):
            inner["owner_node"] = payload.get("owner_node")
    return payload


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

    def reset(self) -> None:
        self.failures = 0
        self.opened_at = 0.0
        self.state = "closed"


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

    def _reconnect_only(self) -> None:
        ensure = getattr(self.remote, "_ensure_connection", None)
        if not callable(ensure):
            return
        try:
            ensure()
        except Exception:
            logging.getLogger("pyautomation").debug(
                "SAF reconnect-only while circuit open failed",
                exc_info=True,
            )

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
            self._reconnect_only()
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
            _stamp_payload_scope(payload)
            if isinstance(row.get("payload"), dict):
                row["payload"] = payload
            else:
                row = dict(row)
                row["payload"] = payload
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
        retry_ids: list[int] = []
        retry_errors: dict[int, str] = {}
        poison_ids: list[int] = []
        poison_errors: dict[int, str] = {}
        last_err = ""
        for domain, domain_rows in _ordered_domain_batches(grouped):
            ids = [int(item["id"]) for item in domain_rows]
            try:
                payloads = [_payload(item) for item in domain_rows]
            except Exception as err:
                category = classify_saf_error(err)
                text = str(err)[:512]
                last_err = text
                if category == POISON:
                    poison_ids.extend(ids)
                    poison_errors.update({jid: text for jid in ids})
                else:
                    retry_ids.extend(ids)
                    retry_errors.update({jid: text for jid in ids})
                continue
            for payload, source in zip(payloads, domain_rows):
                payload.setdefault("sample_uuid", source.get("idempotency_key"))
                payload.setdefault("idempotency_key", source.get("idempotency_key"))
            self.journal.mark_replicating(ids)
            sent_ids, domain_retry, domain_poison, domain_retry_err, domain_poison_err, domain_err = (
                self._flush_classified(domain, ids, payloads)
            )
            if sent_ids:
                self.journal.mark_sent(sent_ids)
                replicated += len(sent_ids)
            retry_ids.extend(domain_retry)
            retry_errors.update(domain_retry_err)
            poison_ids.extend(domain_poison)
            poison_errors.update(domain_poison_err)
            if domain_err:
                last_err = domain_err
            if domain_retry:
                logging.getLogger("pyautomation").error(
                    "SAF replication retryable for domain %s: %s/%s kept PENDING (attempts intact)",
                    domain,
                    len(domain_retry),
                    len(ids),
                )
            if domain_poison:
                logging.getLogger("pyautomation").error(
                    "SAF replication poison for domain %s: %s/%s",
                    domain,
                    len(domain_poison),
                    len(ids),
                )
        if poison_ids:
            self.journal.mark_pending(
                poison_ids,
                error=last_err,
                increment_attempts=True,
                errors=poison_errors,
            )
        if retry_ids:
            self.journal.mark_pending(
                retry_ids,
                error=last_err,
                increment_attempts=False,
                errors=retry_errors,
            )
            self.last_error = last_err
            self.circuit.failure()
        else:
            self.circuit.success()
            self.last_error = last_err if poison_ids else ""
        self.last_replicated = replicated
        try:
            self.journal.total_replicated = int(getattr(self.journal, "total_replicated", 0) or 0) + int(replicated or 0)
        except Exception:
            pass
        self.journal.gc_sent(self.config.gc_sent_after_s, self.config.gc_batch)
        return replicated

    def _flush_classified(
        self,
        domain: str,
        ids: list[int],
        payloads: list[dict[str, Any]],
    ) -> tuple[list[int], list[int], list[int], dict[int, str], dict[int, str], str]:
        sent_ids: list[int] = []
        retry_ids: list[int] = []
        poison_ids: list[int] = []
        retry_errors: dict[int, str] = {}
        poison_errors: dict[int, str] = {}
        last_err = ""
        try:
            raw = self._flush_domain_outcomes(domain, payloads)
            outcomes = normalize_outcomes(raw, len(ids))
        except Exception as err:
            category = classify_saf_error(err)
            text = str(err)[:512]
            last_err = text
            if category == IDEMPOTENT_OK:
                return list(ids), [], [], {}, {}, ""
            if category == POISON:
                return [], [], list(ids), {}, {jid: text for jid in ids}, text
            return [], list(ids), [], {jid: text for jid in ids}, {}, text
        for jid, outcome in zip(ids, outcomes):
            if outcome.ok:
                sent_ids.append(jid)
                continue
            category = classify_saf_error(outcome.error)
            text = outcome.error_text() or last_err or "remote skipped"
            last_err = text
            if category == IDEMPOTENT_OK:
                sent_ids.append(jid)
            elif category == POISON:
                poison_ids.append(jid)
                poison_errors[jid] = text
            else:
                retry_ids.append(jid)
                retry_errors[jid] = text
        return sent_ids, retry_ids, poison_ids, retry_errors, poison_errors, last_err

    def flush(self) -> int:
        """ReplicationWorker entry point. No SQL dialects here."""
        return self.replicate_once()

    def _flush_domain_outcomes(self, domain: str, payloads: list[dict[str, Any]]):
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
