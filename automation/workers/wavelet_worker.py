# -*- coding: utf-8 -*-
"""Wavelet filter worker — sample-interval synchronized, off the OPC hot path."""
from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from .worker import BaseWorker
from ..signal_conditioning.filtered_tags import ensure_filtered_tag, tag_filter_enabled
from ..signal_conditioning.wavelet_block import FilterStatus, WaveletBlockFilter

if TYPE_CHECKING:
    from datetime import datetime

_LOGGER = logging.getLogger("pyautomation.wavelet")

_DEFAULT_TICK_MS = 50
_worker: "WaveletWorker | None" = None
_worker_lock = threading.Lock()


@dataclass
class _TagEntry:
    filter: WaveletBlockFilter
    sample_interval: float
    next_pub: float
    source_name: str
    persist: bool = False
    machines: set[str] = field(default_factory=set)


class WaveletWorker(BaseWorker):
    """Publishes ``.f`` tags at each source tag's machine ``sample_interval``."""

    def __init__(self, tick_ms: float = _DEFAULT_TICK_MS):
        super().__init__()
        self.name = "WaveletWorker"
        self.daemon = True
        self._tick_s = max(0.01, float(tick_ms) / 1000.0)
        self._tags: dict[str, _TagEntry] = {}
        self._lock = threading.Lock()

    def register_tag(
        self,
        source_name: str,
        *,
        sample_interval: float,
        wavelet: str = "db4",
        level: int = 4,
        threshold_factor: float = 3.0,
        persist: bool = False,
        machine_name: str | None = None,
    ) -> None:
        interval = max(0.05, float(sample_interval))
        now = time.monotonic()
        with self._lock:
            entry = self._tags.get(source_name)
            if entry is None:
                entry = _TagEntry(
                    filter=WaveletBlockFilter(wavelet, level, threshold_factor),
                    sample_interval=interval,
                    next_pub=now + interval,
                    source_name=source_name,
                    persist=persist,
                )
                self._tags[source_name] = entry
            else:
                entry.sample_interval = interval
                entry.persist = persist
                entry.filter.reconfigure(
                    wavelet=wavelet,
                    level=level,
                    threshold_factor=threshold_factor,
                )
            if machine_name:
                entry.machines.add(machine_name)

    def unregister_tag(self, source_name: str, machine_name: str | None = None) -> None:
        with self._lock:
            entry = self._tags.get(source_name)
            if entry is None:
                return
            if machine_name:
                entry.machines.discard(machine_name)
                if entry.machines:
                    return
            self._tags.pop(source_name, None)

    def update_sample_interval(self, source_name: str, sample_interval: float) -> None:
        interval = max(0.05, float(sample_interval))
        with self._lock:
            entry = self._tags.get(source_name)
            if entry is not None:
                entry.sample_interval = interval

    def ingest_sample(
        self,
        source_name: str,
        raw: float,
        timestamp: "datetime",
        quality: float = 1.0,
    ) -> None:
        with self._lock:
            entry = self._tags.get(source_name)
            if entry is None:
                return
            entry.filter.update(raw, timestamp, quality)

    def ensure_ingest(
        self,
        source_name: str,
        raw: float,
        timestamp: "datetime",
        quality: float = 1.0,
        *,
        default_interval: float = 1.0,
    ) -> None:
        """Hot-path enqueue; lazily creates filter state if not yet registered."""
        with self._lock:
            entry = self._tags.get(source_name)
            if entry is None:
                interval = max(0.05, float(default_interval))
                entry = _TagEntry(
                    filter=WaveletBlockFilter(),
                    sample_interval=interval,
                    next_pub=time.monotonic() + interval,
                    source_name=source_name,
                )
                self._tags[source_name] = entry
            entry.filter.update(raw, timestamp, quality)

    def run(self) -> None:
        _LOGGER.info("WaveletWorker started tick_ms=%s", int(self._tick_s * 1000))
        while not self.stop_event.is_set():
            now = time.monotonic()
            due: list[tuple[str, _TagEntry]] = []
            with self._lock:
                for name, entry in self._tags.items():
                    if now >= entry.next_pub:
                        due.append((name, entry))
                        entry.next_pub += entry.sample_interval
            for name, entry in due:
                try:
                    self._publish_cycle(name, entry)
                except Exception:
                    _LOGGER.error("Wavelet publish failed tag=%s", name, exc_info=True)
            self.stop_event.wait(self._tick_s)
        _LOGGER.info("WaveletWorker stopped")

    def get_status(self, source_name: str) -> dict | None:
        with self._lock:
            entry = self._tags.get(source_name)
            if entry is None:
                return None
            payload = entry.filter.snapshot_status(entry.sample_interval)
            payload["enabled"] = True
            payload["source"] = source_name
            payload["filtered_tag"] = f"{source_name}.f" if not source_name.endswith(".f") else source_name
            payload["sample_interval"] = entry.sample_interval
            payload["persist"] = entry.persist
            payload["machines"] = sorted(entry.machines)
            return payload

    def list_status(self) -> list[dict]:
        with self._lock:
            names = list(self._tags.keys())
        return [status for name in names if (status := self.get_status(name))]

    def _publish_cycle(self, source_name: str, entry: _TagEntry) -> None:
        result = entry.filter.process()
        if result is None:
            return
        if result.status not in (FilterStatus.OK, FilterStatus.WARMUP, FilterStatus.HOLD):
            return
        from .. import PyAutomation

        app = PyAutomation()
        source = app.cvt.get_tag_by_name(source_name)
        if source is None:
            return
        derived = ensure_filtered_tag(source, persist=entry.persist)
        if derived is None:
            return
        app.cvt.set_value(derived.id, result.value, result.timestamp, quality=result.quality)

    def sync_from_tag(self, tag, *, sample_interval: float, machine_name: str | None = None) -> None:
        if not tag_filter_enabled(tag):
            return
        from ..signal_conditioning.filtered_tags import resolve_filter_config

        cfg = resolve_filter_config(tag)
        self.register_tag(
            tag.name,
            sample_interval=sample_interval,
            wavelet=cfg["wavelet"],
            level=cfg["level"],
            threshold_factor=cfg["threshold_factor"],
            persist=cfg["persist"],
            machine_name=machine_name,
        )


def get_wavelet_worker() -> WaveletWorker | None:
    return _worker


def start_wavelet_worker(tick_ms: float = _DEFAULT_TICK_MS) -> WaveletWorker:
    global _worker
    with _worker_lock:
        if _worker is not None and _worker.is_alive():
            return _worker
        _worker = WaveletWorker(tick_ms=tick_ms)
        _worker.start()
        return _worker


def stop_wavelet_worker() -> None:
    global _worker
    with _worker_lock:
        if _worker is not None:
            _worker.stop()
            if _worker.is_alive():
                _worker.join(timeout=5.0)
            _worker = None


def reset_wavelet_worker_for_tests() -> None:
    stop_wavelet_worker()
