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
        if not self.circuit.allow():
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
        grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for row in rows:
            grouped[row["domain"]].append(row)
        replicated = 0
        failed_ids: list[int] = []
        last_err = ""
        for domain, domain_rows in grouped.items():
            ids = [int(item["id"]) for item in domain_rows]
            payloads = [_payload(item) for item in domain_rows]
            for payload, source in zip(payloads, domain_rows):
                payload.setdefault("sample_uuid", source.get("idempotency_key"))
                payload.setdefault("idempotency_key", source.get("idempotency_key"))
            self.journal.mark_replicating(ids)
            try:
                written = self._flush_domain(domain, payloads)
                if written <= 0:
                    raise ReplicationError(f"remote wrote 0 rows for domain {domain}")
                if written < len(payloads) and domain != "tag":
                    raise ReplicationError(
                        f"partial remote write for {domain}: {written}/{len(payloads)}"
                    )
                self.journal.mark_sent(ids)
                replicated += len(ids)
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
        self.journal.gc_sent(self.config.gc_sent_after_s, self.config.gc_batch)
        return replicated

    def flush(self) -> int:
        """ReplicationWorker entry point. No SQL dialects here."""
        return self.replicate_once()

    def _flush_domain(self, domain: str, payloads: list[dict[str, Any]]) -> int:
        if domain == "tag":
            return self.remote.batch_insert_with_dedupe(payloads)
        return self.remote.write_batch(domain, payloads)


def _payload(row: dict[str, Any]) -> dict[str, Any]:
    raw = row.get("payload") or "{}"
    if isinstance(raw, dict):
        return raw
    return json.loads(raw)
