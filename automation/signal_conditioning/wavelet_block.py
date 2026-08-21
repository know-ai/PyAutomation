# -*- coding: utf-8 -*-
"""Sliding-window DWT denoise — runs in WaveletWorker, not on the OPC hot path."""
from __future__ import annotations

import logging
import math
import time
import warnings
from dataclasses import dataclass
from datetime import datetime
from enum import Enum

import numpy as np
import pywt

from .quality import GOOD, UNCERTAIN, is_good_sample, publication_quality_label
from .sample_ring import SampleRing

_LOGGER = logging.getLogger("pyautomation.wavelet")
_LEVEL_CLAMP_LOG_COOLDOWN_S = 60.0


class FilterStatus(str, Enum):
    IDLE = "idle"
    OK = "ok"
    WARMUP = "warmup"
    HOLD = "hold"
    FAILED = "failed"
    NO_DATA = "no_data"


@dataclass(frozen=True)
class WaveletFilterResult:
    value: float
    timestamp: datetime
    quality: float
    status: FilterStatus


_MAX_DWT_LEVEL = 10
_MAX_THRESHOLD_FACTOR = 10.0
_MAX_WINDOW_SAMPLES = 8192


def _clamp_level(level: int) -> int:
    return max(1, min(int(level), _MAX_DWT_LEVEL))


def _clamp_threshold_factor(value: float) -> float:
    return max(1.0, min(float(value), _MAX_THRESHOLD_FACTOR))


def _wavelet_filter_len(wavelet: str) -> int:
    try:
        return int(pywt.Wavelet(wavelet).dec_len)
    except Exception:
        return 8


def _window_size(level: int, wavelet: str = "db4") -> int:
    """Power-of-two sample window large enough for the requested DWT level."""
    level = _clamp_level(level)
    filter_len = max(2, _wavelet_filter_len(wavelet))
    # pywt: max_level ≈ floor(log2(n / (filter_len - 1)))
    min_samples = (filter_len - 1) * (1 << level)
    size = 16
    while size < min_samples and size < _MAX_WINDOW_SAMPLES:
        size <<= 1
    return size


def _safe_dwt_level(sample_count: int, wavelet: str, requested_level: int) -> int:
    """Clamp decomposition level to what the sample window can support."""
    requested = max(1, int(requested_level))
    if sample_count < 2:
        return 1
    try:
        max_level = int(pywt.dwt_max_level(sample_count, _wavelet_filter_len(wavelet)))
    except Exception:
        max_level = requested
    max_level = max(1, max_level)
    return min(requested, max_level)


def _emit_wavelet_warning(message: str) -> None:
    """Console WARNING matching the PyAutomation startup/runtime log style."""
    from ..utils import _colorize_message

    str_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(_colorize_message(f"[{str_date}] [WARNING] {message}", "WARNING"))
    _LOGGER.warning(message)


class WaveletBlockFilter:
    """Collects raw samples O(1); DWT+threshold+IDWT on ``process()`` only."""

    def __init__(
        self,
        wavelet: str = "db4",
        level: int = 4,
        threshold_factor: float = 3.0,
    ):
        self.wavelet = str(wavelet or "db4")
        self.level = _clamp_level(level)
        self.threshold_factor = _clamp_threshold_factor(threshold_factor)
        self._window = _window_size(self.level, self.wavelet)
        self._ring = SampleRing(capacity=self._window * 2)
        self._last_result: WaveletFilterResult | None = None
        self._status = FilterStatus.IDLE
        self._last_pub_mono: float | None = None
        self._raw_count = 0
        self._drop_count = 0
        self._cycle_raw = 0
        self._hold_active = False
        self._last_input_quality = GOOD
        self._last_good_value: float | None = None
        self._last_publication_quality = GOOD
        self._last_level_clamp_key: tuple | None = None
        self._last_level_clamp_mono: float = 0.0
        self._effective_level = self.level

    def _log_level_clamp(self, requested: int, effective: int, sample_count: int) -> None:
        key = (self.wavelet, requested, effective, self._window, sample_count)
        now = time.monotonic()
        if key == self._last_level_clamp_key and (now - self._last_level_clamp_mono) < _LEVEL_CLAMP_LOG_COOLDOWN_S:
            return
        self._last_level_clamp_key = key
        self._last_level_clamp_mono = now
        _emit_wavelet_warning(
            "Wavelet DWT level clamped: "
            f"configured={requested} safe_max={effective} wavelet={self.wavelet} "
            f"window={sample_count} samples — using level {effective} to avoid boundary effects. "
            "Lower the decomposition level or increase the sample window."
        )

    def reconfigure(
        self,
        *,
        wavelet: str | None = None,
        level: int | None = None,
        threshold_factor: float | None = None,
    ) -> dict:
        """
        Update filter parameters without discarding the raw sample ring.

        Returns a summary of what changed. Warmup is only required when the
        ring has fewer samples than the new DWT window (typically after a
        level increase). Family / threshold changes apply on the next process().
        """
        changed = {
            "wavelet": False,
            "level": False,
            "threshold_factor": False,
            "window": False,
            "resized_ring": False,
            "needs_warmup": False,
        }
        if wavelet is not None:
            new_wavelet = str(wavelet or "db4")
            if new_wavelet != self.wavelet:
                self.wavelet = new_wavelet
                changed["wavelet"] = True
        if threshold_factor is not None:
            new_factor = _clamp_threshold_factor(threshold_factor)
            if new_factor != self.threshold_factor:
                self.threshold_factor = new_factor
                changed["threshold_factor"] = True
        if level is not None:
            new_level = _clamp_level(level)
            if new_level != self.level:
                self.level = new_level
                changed["level"] = True

        new_window = _window_size(self.level, self.wavelet)
        if new_window != self._window:
            self._window = new_window
            changed["window"] = True

        needed_capacity = self._window * 2
        if self._ring.capacity < needed_capacity:
            self._ring.resize(needed_capacity)
            changed["resized_ring"] = True
        elif changed["window"] and self._ring.capacity > needed_capacity * 2:
            # Shrink only when capacity is clearly oversized; keep recent samples.
            self._ring.resize(needed_capacity)
            changed["resized_ring"] = True

        if len(self._ring) < self._window:
            changed["needs_warmup"] = True
            self._status = FilterStatus.WARMUP
        elif (
            changed["wavelet"] or changed["level"] or changed["threshold_factor"]
        ) and self._status == FilterStatus.FAILED:
            # Clear a previous hard failure so the new operator can run.
            self._status = FilterStatus.OK if self._last_result else FilterStatus.IDLE

        _LOGGER.info(
            "WaveletBlockFilter reconfigured wavelet=%s level=%s threshold=%s window=%s ring=%s/%s needs_warmup=%s",
            self.wavelet,
            self.level,
            self.threshold_factor,
            self._window,
            len(self._ring),
            self._ring.capacity,
            changed["needs_warmup"],
        )
        return changed

    def update(self, raw: float, timestamp: datetime, quality: float = GOOD) -> None:
        self._cycle_raw += 1
        self._last_input_quality = float(quality) if quality is not None else GOOD
        if not is_good_sample(raw, quality):
            self._drop_count += 1
            self._hold_active = True
            if self._last_result is not None:
                self._status = FilterStatus.HOLD
            return
        self._hold_active = False
        try:
            self._ring.append(float(raw), timestamp, float(quality))
            self._raw_count += 1
        except (TypeError, ValueError):
            self._drop_count += 1
            _LOGGER.debug("WaveletBlockFilter skipped non-numeric sample", exc_info=True)

    def process(self) -> WaveletFilterResult | None:
        if self._hold_active and self._last_result is not None:
            last = self._last_result
            hold_value = self._last_good_value if self._last_good_value is not None else last.value
            result = WaveletFilterResult(
                value=hold_value,
                timestamp=last.timestamp,
                quality=UNCERTAIN,
                status=FilterStatus.HOLD,
            )
            self._last_result = result
            self._status = FilterStatus.HOLD
            self._last_publication_quality = UNCERTAIN
            self._last_pub_mono = time.monotonic()
            self._cycle_raw = 0
            return result

        points = self._ring.snapshot()
        if not points:
            self._status = FilterStatus.NO_DATA
            return None
        if len(points) < self._window:
            latest = points[-1]
            result = WaveletFilterResult(
                value=latest.value,
                timestamp=latest.timestamp,
                quality=UNCERTAIN,
                status=FilterStatus.WARMUP,
            )
            self._last_result = result
            self._status = FilterStatus.WARMUP
            self._last_publication_quality = UNCERTAIN
            if math.isfinite(latest.value):
                self._last_good_value = float(latest.value)
            self._last_pub_mono = time.monotonic()
            self._cycle_raw = 0
            return result

        window = points[-self._window :]
        values = np.asarray([p.value for p in window], dtype=np.float64)
        effective_level = _safe_dwt_level(len(values), self.wavelet, self.level)
        self._effective_level = effective_level
        if effective_level < self.level:
            self._log_level_clamp(self.level, effective_level, len(values))
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", UserWarning)
                coeffs = pywt.wavedec(values, self.wavelet, level=effective_level)
        except ValueError:
            latest = window[-1]
            result = WaveletFilterResult(
                value=latest.value,
                timestamp=latest.timestamp,
                quality=UNCERTAIN,
                status=FilterStatus.WARMUP,
            )
            self._last_result = result
            self._status = FilterStatus.WARMUP
            self._last_publication_quality = UNCERTAIN
            if math.isfinite(latest.value):
                self._last_good_value = float(latest.value)
            self._last_pub_mono = time.monotonic()
            self._cycle_raw = 0
            return result

        detail = coeffs[-1]
        sigma = float(np.median(np.abs(detail))) / 0.6745 if detail.size else 0.0
        threshold = sigma * self.threshold_factor
        coeffs_thresh = [coeffs[0]]
        for band in coeffs[1:]:
            coeffs_thresh.append(pywt.threshold(band, threshold, mode="soft"))
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", UserWarning)
                reconstructed = pywt.waverec(coeffs_thresh, self.wavelet)
        except ValueError:
            latest = window[-1]
            result = WaveletFilterResult(
                value=latest.value,
                timestamp=latest.timestamp,
                quality=UNCERTAIN,
                status=FilterStatus.FAILED,
            )
            self._last_result = result
            self._status = FilterStatus.FAILED
            self._cycle_raw = 0
            return result

        filtered_value = float(reconstructed[-1])
        if not math.isfinite(filtered_value):
            self._status = FilterStatus.FAILED
            self._drop_count += 1
            self._cycle_raw = 0
            return self._last_result

        anchor = window[-1]
        self._last_good_value = filtered_value
        result = WaveletFilterResult(
            value=filtered_value,
            timestamp=anchor.timestamp,
            quality=GOOD,
            status=FilterStatus.OK,
        )
        self._last_result = result
        self._status = FilterStatus.OK
        self._last_publication_quality = GOOD
        self._last_pub_mono = time.monotonic()
        self._cycle_raw = 0
        return result

    def get_filtered(self) -> WaveletFilterResult | None:
        return self._last_result

    def snapshot_status(self, sample_interval: float) -> dict:
        age_ms = None
        if self._last_pub_mono is not None:
            age_ms = round((time.monotonic() - self._last_pub_mono) * 1000.0, 1)
            if age_ms > max(2000.0, 2000.0 * float(sample_interval or 1.0)):
                if self._status not in (FilterStatus.FAILED, FilterStatus.HOLD):
                    self._status = FilterStatus.HOLD
        last = self._last_result
        interval = max(0.05, float(sample_interval or 1.0))
        ring_fill = len(self._ring)
        remaining = max(0, self._window - ring_fill)
        warmup_eta_s = None
        if remaining > 0:
            points = self._ring.snapshot()
            eta = remaining * interval
            if len(points) >= 2:
                try:
                    span = (points[-1].timestamp - points[0].timestamp).total_seconds()
                    if span > 0:
                        rate = (len(points) - 1) / span
                        if rate > 0:
                            eta = remaining / rate
                except Exception:
                    pass
            warmup_eta_s = round(max(0.0, eta), 1)
        elif self._status == FilterStatus.OK:
            warmup_eta_s = 0.0
        return {
            "status": self._status.value,
            "age_ms": age_ms,
            "last_publication_ts": last.timestamp.isoformat() if last else None,
            "last_value": last.value if last else None,
            "raw_count": self._raw_count,
            "drop_count": self._drop_count,
            "bad_samples_dropped": self._drop_count,
            "last_publication_quality": publication_quality_label(self._last_publication_quality),
            "last_good_value": self._last_good_value,
            "raw_rate": round(1.0 / interval, 3),
            "window": self._window,
            "ring_fill": ring_fill,
            "warmup_remaining": remaining,
            "warmup_eta_s": warmup_eta_s,
            "configured_level": self.level,
            "effective_level": self._effective_level,
        }
