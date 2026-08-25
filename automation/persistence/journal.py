# -*- coding: utf-8 -*-
"""SQLite WAL journal — Plan A for durability.

The hot path never talks to PostgreSQL. This writer is the only component
allowed to fsync the local outbox. Disk-full is a handled failure, never a
silent WAL corruption.
"""
from __future__ import annotations

import json
import logging
import os
import sqlite3
import threading
import time
from collections import deque
from datetime import datetime, timezone
from typing import Any, Sequence

from .config import SafConfig
from .contracts import IPersistable
from .exceptions import JournalBackpressureError, JournalDiskFullError, JournalError
from .records import utc_now

STATUS_PENDING = "PENDING"
STATUS_REPLICATING = "REPLICATING"
STATUS_SENT = "SENT"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS persistence_journal (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    domain TEXT NOT NULL,
    entity_id TEXT NOT NULL,
    idempotency_key TEXT NOT NULL UNIQUE,
    payload TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'PENDING',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    attempts INTEGER NOT NULL DEFAULT 0,
    last_error TEXT
);
CREATE INDEX IF NOT EXISTS idx_journal_status_id ON persistence_journal (status, id);
CREATE INDEX IF NOT EXISTS idx_journal_created ON persistence_journal (created_at);
CREATE INDEX IF NOT EXISTS idx_journal_domain_status ON persistence_journal (domain, status);
"""

_INSERT = """
INSERT INTO persistence_journal
    (domain, entity_id, idempotency_key, payload, status, created_at, updated_at, attempts)
VALUES (?, ?, ?, ?, 'PENDING', ?, ?, 0)
"""


def _notify_saf_capacity_event(kind: str) -> None:
    """One Events row per outage (60 s cooldown). Never raises into the journal."""
    try:
        from ..utils.audit_metrics import cooldown_allows
        from ..utils.system_event_audit import persist_system_event

        if not cooldown_allows(f"saf:{kind}", 60.0):
            return
        if kind == "disk":
            persist_system_event(
                message="SAF disk full",
                description="kind=disk",
                classification="System",
                priority=5,
                criticity=5,
            )
        else:
            persist_system_event(
                message="SAF backpressure triggered",
                description="kind=backpressure",
                classification="System",
                priority=4,
                criticity=5,
            )
    except Exception:
        logging.getLogger("pyautomation").debug(
            "SAF capacity audit event skipped",
            exc_info=True,
        )


class JournalWriter:
    """Single writer for the local WAL. Thread-safe. Never swallows SQLite errors."""

    def __init__(self, config: SafConfig | None = None):
        self.config = config or SafConfig()
        self._lock = threading.RLock()
        self._conn: sqlite3.Connection | None = None
        self._ring: deque[IPersistable] = deque()
        self._ring_event = threading.Event()
        self._stop = threading.Event()
        self._flusher: threading.Thread | None = None
        self._started = False
        self.dropped_full = 0
        self.enqueued = 0
        self.pending_cap_hits = 0
        self.backpressure = False
        self.last_error = ""
        self._force_flush_hook = None

    def start(self) -> None:
        with self._lock:
            if self._started:
                return
            self._open()
            self._stop.clear()
            self._flusher = threading.Thread(
                target=self._flush_loop,
                name="SafJournalFlusher",
                daemon=True,
            )
            self._flusher.start()
            self._started = True

    def stop(self) -> None:
        self._stop.set()
        self._ring_event.set()
        if self._flusher and self._flusher.is_alive():
            self._flusher.join(timeout=2.0)
        with self._lock:
            self._drain_ring_locked()
            self._commit_locked()
            if self._conn is not None:
                self._conn.close()
                self._conn = None
            self._started = False

    def set_force_flush_hook(self, hook) -> None:
        """Optional callback (LoggerWorker / RemoteReplicator) after a ring drain."""
        self._force_flush_hook = hook

    def _invoke_force_flush_hook(self) -> None:
        hook = self._force_flush_hook
        if not callable(hook):
            return
        try:
            hook()
        except Exception:
            logging.getLogger("pyautomation").debug(
                "SAF force flush hook failed", exc_info=True
            )

    def _drain_ring_for_backpressure_locked(self) -> bool:
        """Persist the in-memory ring to SQLite so enqueue can continue.

        Returns True when the caller should kick remote replication.
        """
        if len(self._ring) < self.config.ring_maxsize:
            return False
        logging.getLogger("pyautomation").warning(
            "SAF ring full; forcing LoggerWorker flush"
        )
        try:
            self._drain_ring_locked()
            self._commit_locked()
        except Exception:
            logging.getLogger("pyautomation").error(
                "SAF ring drain during backpressure failed",
                exc_info=True,
            )
        return True

    def append(self, persistable: IPersistable) -> int:
        """Durable enqueue. Critical records wait for COMMIT; tags use the ring."""
        self.start()
        try:
            if persistable.is_critical():
                with self._lock:
                    return self._insert_commit_locked(persistable)
            return self._enqueue_ring(persistable)
        except JournalBackpressureError:
            _notify_saf_capacity_event("backpressure")
            raise
        except JournalDiskFullError:
            _notify_saf_capacity_event("disk")
            raise

    def append_many(self, persistables: Sequence[IPersistable]) -> int:
        """Hot-path burst enqueue (one lock). Used by high-rate soak / scanners."""
        self.start()
        items = list(persistables)
        if not items:
            return 0
        try:
            kick = False
            with self._lock:
                self._ensure_open_locked()
                self._guard_pending_locked()
                if len(self._ring) + len(items) > self.config.ring_maxsize:
                    kick = self._drain_ring_for_backpressure_locked()
                if len(self._ring) + len(items) > self.config.ring_maxsize:
                    self.backpressure = True
                    self.dropped_full += len(items)
                    raise JournalBackpressureError(
                        f"SAF ring full ({self.config.ring_maxsize}); history backpressure engaged"
                    )
                self._ring.extend(items)
                self.backpressure = False
            if kick:
                self._invoke_force_flush_hook()
        except JournalBackpressureError:
            _notify_saf_capacity_event("backpressure")
            raise
        except JournalDiskFullError:
            _notify_saf_capacity_event("disk")
            raise
        self._ring_event.set()
        return len(items)

    def append_committed_many(self, persistables: Sequence[IPersistable]) -> list[int]:
        """Durable enqueue of critical records with one lock and one COMMIT."""
        self.start()
        items = list(persistables)
        if not items:
            return []
        try:
            with self._lock:
                self._ensure_open_locked()
                row_ids: list[int] = []
                for persistable in items:
                    row_ids.append(self._insert_locked(persistable))
                self._commit_locked()
                return row_ids
        except JournalBackpressureError:
            _notify_saf_capacity_event("backpressure")
            raise
        except JournalDiskFullError:
            _notify_saf_capacity_event("disk")
            raise

    def flush_sync(self) -> None:
        self.start()
        with self._lock:
            self._drain_ring_locked()
            self._commit_locked()

    def pending_count(self) -> int:
        self.start()
        with self._lock:
            self._ensure_open_locked()
            row = self._conn.execute(
                "SELECT COUNT(*) FROM persistence_journal WHERE status IN (?, ?)",
                (STATUS_PENDING, STATUS_REPLICATING),
            ).fetchone()
            return int(row[0]) + len(self._ring)

    def fetch_pending(self, limit: int) -> list[dict[str, Any]]:
        self.start()
        with self._lock:
            self._ensure_open_locked()
            rows = self._conn.execute(
                """
                SELECT id, domain, entity_id, idempotency_key, payload, created_at, attempts
                FROM persistence_journal
                WHERE status = ?
                ORDER BY CASE domain WHEN 'tag' THEN 0 ELSE 1 END, id ASC
                LIMIT ?
                """,
                (STATUS_PENDING, int(limit)),
            ).fetchall()
            return [dict(row) for row in rows]

    def mark_replicating(self, journal_ids: Sequence[int]) -> None:
        self._set_status(journal_ids, STATUS_REPLICATING)

    def mark_pending(self, journal_ids: Sequence[int], error: str = "") -> None:
        if not journal_ids:
            return
        now = utc_now().isoformat()
        with self._lock:
            self._ensure_open_locked()
            self._conn.executemany(
                """
                UPDATE persistence_journal
                SET status = ?, updated_at = ?, attempts = attempts + 1, last_error = ?
                WHERE id = ?
                """,
                [(STATUS_PENDING, now, error[:512], int(jid)) for jid in journal_ids],
            )
            self._commit_locked()

    def mark_sent(self, journal_ids: Sequence[int]) -> None:
        self._set_status(journal_ids, STATUS_SENT)

    def gc_sent(self, older_than_s: float, limit: int) -> int:
        cutoff = datetime.now(timezone.utc).timestamp() - float(older_than_s)
        cutoff_iso = datetime.fromtimestamp(cutoff, tz=timezone.utc).isoformat()
        with self._lock:
            self._ensure_open_locked()
            cur = self._conn.execute(
                """
                DELETE FROM persistence_journal
                WHERE id IN (
                    SELECT id FROM persistence_journal
                    WHERE status = ? AND updated_at <= ?
                    ORDER BY id ASC
                    LIMIT ?
                )
                """,
                (STATUS_SENT, cutoff_iso, int(limit)),
            )
            deleted = cur.rowcount if cur.rowcount is not None else 0
            self._commit_locked()
            return int(deleted)

    def evict_sent_oldest(self, limit: int) -> int:
        """Controlled eviction: SENT only. PENDING is sacred."""
        with self._lock:
            self._ensure_open_locked()
            cur = self._conn.execute(
                """
                DELETE FROM persistence_journal
                WHERE id IN (
                    SELECT id FROM persistence_journal
                    WHERE status = ?
                    ORDER BY id ASC
                    LIMIT ?
                )
                """,
                (STATUS_SENT, int(limit)),
            )
            deleted = cur.rowcount if cur.rowcount is not None else 0
            self._commit_locked()
            return int(deleted)

    def disk_bytes(self) -> int:
        total = 0
        for suffix in ("", "-wal", "-shm"):
            path = self.config.journal_path + suffix
            if os.path.exists(path):
                total += os.path.getsize(path)
        return total

    def oldest_pending_age_s(self) -> float:
        with self._lock:
            self._ensure_open_locked()
            row = self._conn.execute(
                "SELECT created_at FROM persistence_journal WHERE status = ? ORDER BY id ASC LIMIT 1",
                (STATUS_PENDING,),
            ).fetchone()
        if not row:
            return 0.0
        try:
            created = datetime.fromisoformat(row["created_at"])
            if created.tzinfo is None:
                created = created.replace(tzinfo=timezone.utc)
            return max(0.0, (datetime.now(timezone.utc) - created).total_seconds())
        except (TypeError, ValueError):
            return 0.0

    def _set_status(self, journal_ids: Sequence[int], status: str) -> None:
        if not journal_ids:
            return
        now = utc_now().isoformat()
        with self._lock:
            self._ensure_open_locked()
            self._conn.executemany(
                "UPDATE persistence_journal SET status = ?, updated_at = ? WHERE id = ?",
                [(status, now, int(jid)) for jid in journal_ids],
            )
            self._commit_locked()

    def _pending_rows_locked(self) -> int:
        row = self._conn.execute(
            "SELECT COUNT(*) FROM persistence_journal WHERE status IN (?, ?)",
            (STATUS_PENDING, STATUS_REPLICATING),
        ).fetchone()
        return int(row[0]) + len(self._ring)

    def _guard_pending_locked(self) -> None:
        max_rows = int(getattr(self.config, "max_pending_rows", 0) or 0)
        if max_rows <= 0:
            return
        if self._pending_rows_locked() < max_rows:
            return
        self.pending_cap_hits += 1
        self.backpressure = True
        raise JournalBackpressureError(
            f"SAF pending rows reached cap max_pending_rows={max_rows}; history backpressure engaged"
        )

    def _enqueue_ring(self, persistable: IPersistable) -> int:
        kick = False
        with self._lock:
            self._ensure_open_locked()
            self._guard_pending_locked()
            if len(self._ring) >= self.config.ring_maxsize:
                kick = self._drain_ring_for_backpressure_locked()
            if len(self._ring) >= self.config.ring_maxsize:
                self.backpressure = True
                self.dropped_full += 1
                raise JournalBackpressureError(
                    f"SAF ring full ({self.config.ring_maxsize}); history backpressure engaged"
                )
            self._ring.append(persistable)
            self.backpressure = False
        self._ring_event.set()
        if kick:
            self._invoke_force_flush_hook()
        return 0

    def _flush_loop(self) -> None:
        interval = max(0.001, self.config.tag_flush_interval_s)
        while not self._stop.is_set():
            self._ring_event.wait(timeout=interval)
            self._ring_event.clear()
            try:
                with self._lock:
                    self._drain_ring_locked()
                    self._commit_locked()
            except JournalDiskFullError:
                logging.getLogger("pyautomation").critical("SAF journal disk full during flush")
            except sqlite3.Error:
                logging.getLogger("pyautomation").error("SAF journal flush failed", exc_info=True)

    def _drain_ring_locked(self) -> None:
        if not self._ring:
            return
        self._ensure_open_locked()
        batch = self.config.tag_batch_size
        while self._ring:
            chunk = []
            while self._ring and len(chunk) < batch:
                chunk.append(self._ring.popleft())
            for persistable in chunk:
                self._insert_locked(persistable)

    def _insert_commit_locked(self, persistable: IPersistable) -> int:
        self._ensure_open_locked()
        row_id = self._insert_locked(persistable)
        self._commit_locked()
        return row_id

    def _insert_locked(self, persistable: IPersistable) -> int:
        self._guard_disk_locked()
        self._guard_pending_locked()
        now = utc_now().isoformat()
        payload = json.dumps(dict(persistable.payload()), default=str)
        try:
            cur = self._conn.execute(
                _INSERT,
                (
                    persistable.domain(),
                    persistable.entity_id(),
                    persistable.idempotency_key(),
                    payload,
                    now,
                    now,
                ),
            )
            self.enqueued += 1
            return int(cur.lastrowid)
        except sqlite3.IntegrityError:
            row = self._conn.execute(
                "SELECT id FROM persistence_journal WHERE idempotency_key = ?",
                (persistable.idempotency_key(),),
            ).fetchone()
            return int(row["id"]) if row else 0
        except sqlite3.OperationalError as err:
            self._raise_operational(err)

    def _commit_locked(self) -> None:
        if self._conn is None:
            return
        try:
            self._conn.commit()
        except sqlite3.OperationalError as err:
            self._raise_operational(err)

    def _raise_operational(self, err: sqlite3.OperationalError) -> None:
        message = str(err).lower()
        self.last_error = str(err)
        if "full" in message or "database or disk is full" in message:
            self.dropped_full += 1
            self.backpressure = True
            raise JournalDiskFullError(str(err)) from err
        raise JournalError(str(err)) from err

    def _guard_disk_locked(self) -> None:
        usage = self.disk_bytes()
        if usage < self.config.max_disk_bytes:
            return
        freed = self.evict_sent_oldest(self.config.gc_batch)
        if freed <= 0 or self.disk_bytes() >= self.config.max_disk_bytes:
            self.dropped_full += 1
            self.backpressure = True
            raise JournalDiskFullError(
                f"SAF journal exceeds max_disk_bytes={self.config.max_disk_bytes}"
            )

    def _open(self) -> None:
        directory = os.path.dirname(os.path.abspath(self.config.journal_path))
        try:
            os.makedirs(directory, exist_ok=True)
        except OSError as err:
            raise JournalError(
                f"Unable to create SAF journal directory {directory!r}: {err}. "
                "Ensure ./db (Docker: /app/db volume) is writable by the process user."
            ) from err
        if not os.path.isdir(directory):
            raise JournalError(
                f"Unable to open SAF journal: directory {directory!r} is missing. "
                "Ensure ./db (Docker: /app/db volume) is writable by the process user."
            )
        self._ensure_open_locked()

    def _ensure_open_locked(self) -> None:
        if self._conn is not None:
            return
        try:
            self._conn = sqlite3.connect(
                self.config.journal_path,
                timeout=30.0,
                isolation_level="DEFERRED",
                check_same_thread=False,
            )
            self._conn.row_factory = sqlite3.Row
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA synchronous=FULL")
            self._conn.execute("PRAGMA temp_store=MEMORY")
            self._conn.execute(f"PRAGMA wal_autocheckpoint={int(self.config.wal_autocheckpoint)}")
            self._conn.execute("PRAGMA foreign_keys=ON")
            self._conn.executescript(_SCHEMA)
            self._conn.commit()
        except sqlite3.Error as err:
            self.last_error = str(err)
            raise JournalError(f"Unable to open SAF journal: {err}") from err
