# -*- coding: utf-8 -*-
import time
import unittest
import warnings
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import numpy as np

from automation.signal_conditioning.filtered_tags import (
    filtered_tag_name,
    is_filtered_derivative_name,
    source_tag_name,
    tag_filter_enabled,
)
from automation.signal_conditioning.quality import BAD, GOOD, UNCERTAIN
from automation.signal_conditioning.sample_ring import SampleRing
from automation.signal_conditioning.wavelet_block import (
    FilterStatus,
    WaveletBlockFilter,
    _safe_dwt_level,
    _window_size,
)
from automation.workers.wavelet_worker import WaveletWorker, reset_wavelet_worker_for_tests


class _TagStub:
    def __init__(self, **kwargs):
        for key, value in kwargs.items():
            setattr(self, key, value)


class TestWaveletNaming(unittest.TestCase):
    def test_filtered_tag_name(self):
        self.assertEqual(filtered_tag_name("Area.P"), "Area.P.f")
        self.assertEqual(filtered_tag_name("Area.P.f"), "Area.P.f")

    def test_is_derivative(self):
        self.assertTrue(is_filtered_derivative_name("x.f"))
        self.assertFalse(is_filtered_derivative_name("x"))

    def test_source_tag_name(self):
        self.assertEqual(source_tag_name("x.f"), "x")

    def test_tag_filter_enabled(self):
        src = _TagStub(name="P", filter_enabled=True)
        derived = _TagStub(name="P.f", filter_enabled=False)
        self.assertTrue(tag_filter_enabled(src))
        self.assertFalse(tag_filter_enabled(derived))


class TestSampleRing(unittest.TestCase):
    def test_append_is_bounded(self):
        ring = SampleRing(capacity=4)
        base = datetime(2026, 1, 1)
        for i in range(10):
            ring.append(float(i), base + timedelta(seconds=i))
        self.assertEqual(len(ring), 4)
        self.assertEqual(ring.latest().value, 9.0)


class TestWaveletBlockFilter(unittest.TestCase):
    def test_warmup_then_ok(self):
        flt = WaveletBlockFilter(wavelet="db4", level=3, threshold_factor=3.0)
        base = datetime(2026, 1, 1)
        rng = np.random.default_rng(0)
        signal = np.sin(np.linspace(0, 4 * np.pi, 40)) + rng.normal(0, 0.05, 40)
        last = None
        for i, value in enumerate(signal):
            flt.update(float(value), base + timedelta(milliseconds=100 * i))
            last = flt.process()
        self.assertIsNotNone(last)
        self.assertIn(last.status, (FilterStatus.OK, FilterStatus.WARMUP))
        if last.status == FilterStatus.OK:
            self.assertTrue(np.isfinite(last.value))

    def test_bad_quality_does_not_enter_ring(self):
        flt = WaveletBlockFilter(level=3)
        base = datetime(2026, 1, 1)
        flt.update(1.0, base, quality=GOOD)
        flt.update(float("nan"), base, quality=GOOD)
        flt.update(2.0, base, quality=BAD)
        self.assertEqual(len(flt._ring), 1)
        status = flt.snapshot_status(0.5)
        self.assertGreaterEqual(status["drop_count"], 2)
        self.assertGreaterEqual(status["bad_samples_dropped"], 2)

    def test_hold_publishes_uncertain_with_last_good(self):
        flt = WaveletBlockFilter(level=3)
        base = datetime(2026, 1, 1)
        for i in range(20):
            flt.update(float(i), base + timedelta(milliseconds=50 * i), quality=GOOD)
        ok = flt.process()
        self.assertIsNotNone(ok)
        self.assertEqual(ok.status, FilterStatus.WARMUP)
        last_good = ok.value
        flt.update(float("nan"), base, quality=BAD)
        hold = flt.process()
        self.assertIsNotNone(hold)
        self.assertEqual(hold.status, FilterStatus.HOLD)
        self.assertEqual(hold.quality, UNCERTAIN)
        self.assertEqual(hold.value, last_good)
        status = flt.snapshot_status(0.5)
        self.assertEqual(status["last_publication_quality"], "UNCERTAIN")
        self.assertIsNotNone(status["last_good_value"])

    def test_good_sample_after_hold_resumes_ok(self):
        flt = WaveletBlockFilter(level=3)
        base = datetime(2026, 1, 1)
        for i in range(20):
            flt.update(float(i), base + timedelta(milliseconds=50 * i), quality=GOOD)
        flt.process()
        flt.update(float("nan"), base, quality=BAD)
        hold = flt.process()
        self.assertEqual(hold.status, FilterStatus.HOLD)
        for i in range(20, 40):
            flt.update(float(i), base + timedelta(milliseconds=50 * i), quality=GOOD)
        recovered = flt.process()
        self.assertIsNotNone(recovered)
        self.assertIn(recovered.status, (FilterStatus.OK, FilterStatus.WARMUP))
        self.assertEqual(recovered.quality, UNCERTAIN if recovered.status == FilterStatus.WARMUP else GOOD)

    def test_reconfigure_preserves_ring_and_skips_warmup(self):
        flt = WaveletBlockFilter(wavelet="db4", level=3, threshold_factor=3.0)
        base = datetime(2026, 1, 1)
        for i in range(flt._window + 8):
            flt.update(float(i), base + timedelta(milliseconds=50 * i), quality=GOOD)
        before = flt.process()
        self.assertIsNotNone(before)
        self.assertEqual(before.status, FilterStatus.OK)
        ring_len = len(flt._ring)
        last_good = flt._last_good_value

        changed = flt.reconfigure(wavelet="sym4", threshold_factor=2.5)
        self.assertTrue(changed["wavelet"])
        self.assertTrue(changed["threshold_factor"])
        self.assertFalse(changed["needs_warmup"])
        self.assertEqual(len(flt._ring), ring_len)
        self.assertEqual(flt._last_good_value, last_good)

        after = flt.process()
        self.assertIsNotNone(after)
        self.assertEqual(after.status, FilterStatus.OK)
        self.assertEqual(after.quality, GOOD)

    def test_reconfigure_level_up_may_need_warmup(self):
        flt = WaveletBlockFilter(wavelet="db4", level=1, threshold_factor=3.0)
        base = datetime(2026, 1, 1)
        # level=1 → window 16; fill exactly the current window
        for i in range(16):
            flt.update(float(i), base + timedelta(milliseconds=50 * i), quality=GOOD)
        self.assertEqual(len(flt._ring), 16)
        # level=6 → window 512 (db4); ring too small → warmup
        changed = flt.reconfigure(level=6)
        self.assertTrue(changed["level"])
        self.assertTrue(changed["window"])
        self.assertEqual(flt._window, 512)
        self.assertTrue(changed["needs_warmup"])
        self.assertEqual(flt._status, FilterStatus.WARMUP)
        self.assertEqual(len(flt._ring), 16)

    def test_window_supports_configured_level(self):
        for level in range(1, 7):
            window = _window_size(level, "db4")
            self.assertGreaterEqual(_safe_dwt_level(window, "db4", level), level)

    def test_high_level_is_clamped_without_pywt_warning(self):
        # Undersized window forces clamp; pywt boundary UserWarning must stay silent.
        self.assertEqual(_safe_dwt_level(32, "db4", 5), 2)
        flt = WaveletBlockFilter(wavelet="db4", level=5, threshold_factor=3.0)
        flt._window = 32
        base = datetime(2026, 1, 1)
        for i in range(32):
            flt.update(float(i), base + timedelta(milliseconds=50 * i), quality=GOOD)
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            result = flt.process()
        pywt_boundary = [
            w
            for w in caught
            if issubclass(w.category, UserWarning)
            and "Level value" in str(w.message)
            and "boundary effects" in str(w.message)
        ]
        self.assertEqual(pywt_boundary, [])
        self.assertIsNotNone(result)
        self.assertEqual(flt._effective_level, 2)
        status = flt.snapshot_status(0.5)
        self.assertEqual(status["configured_level"], 5)
        self.assertEqual(status["effective_level"], 2)


class TestWaveletWorker(unittest.TestCase):
    def tearDown(self):
        reset_wavelet_worker_for_tests()

    def test_register_and_ingest(self):
        worker = WaveletWorker(tick_ms=20)
        worker.register_tag("T1", sample_interval=0.1, wavelet="db4", level=3)
        base = datetime(2026, 1, 1)
        entry = worker._tags["T1"]
        n = entry.filter._window
        for i in range(n):
            worker.ensure_ingest("T1", float(i), base + timedelta(milliseconds=50 * i))
        self.assertEqual(len(entry.filter._ring), n)
        result = entry.filter.process()
        self.assertIsNotNone(result)
        worker.stop()

    def test_reregister_reconfigures_without_clearing_ring(self):
        worker = WaveletWorker(tick_ms=20)
        worker.register_tag("T1", sample_interval=0.1, wavelet="db4", level=3)
        base = datetime(2026, 1, 1)
        entry = worker._tags["T1"]
        for i in range(entry.filter._window + 8):
            worker.ensure_ingest("T1", float(i), base + timedelta(milliseconds=50 * i))
        entry.filter.process()
        ring_len = len(entry.filter._ring)
        worker.register_tag("T1", sample_interval=0.1, wavelet="sym4", level=3, threshold_factor=2.0)
        entry2 = worker._tags["T1"]
        self.assertIs(entry2.filter, entry.filter)
        self.assertEqual(len(entry2.filter._ring), ring_len)
        self.assertEqual(entry2.filter.wavelet, "sym4")
        self.assertEqual(entry2.filter.threshold_factor, 2.0)
        result = entry2.filter.process()
        self.assertEqual(result.status, FilterStatus.OK)
        worker.stop()

    def test_publish_applies_quality_to_derived_tag(self):
        worker = WaveletWorker(tick_ms=20)
        worker.register_tag("Src.P", sample_interval=0.05, level=3)
        base = datetime(2026, 1, 1)
        for i in range(24):
            worker.ensure_ingest("Src.P", float(i), base + timedelta(milliseconds=40 * i), quality=GOOD)
        worker.ensure_ingest("Src.P", float("nan"), base, quality=BAD)

        source = _TagStub(name="Src.P", filter_enabled=True, id="src1")
        derived = _TagStub(name="Src.P.f", id="der1")
        mock_cvt = MagicMock()
        mock_cvt.get_tag_by_name.return_value = source
        mock_app = MagicMock()
        mock_app.cvt = mock_cvt

        with patch("automation.workers.wavelet_worker.ensure_filtered_tag", return_value=derived):
            with patch("automation.PyAutomation", return_value=mock_app):
                entry = worker._tags["Src.P"]
                worker._publish_cycle("Src.P", entry)

        mock_cvt.set_value.assert_called_once()
        _, kwargs = mock_cvt.set_value.call_args
        self.assertEqual(kwargs.get("quality"), UNCERTAIN)


class TestCvtWaveletIngest(unittest.TestCase):
    def tearDown(self):
        reset_wavelet_worker_for_tests()

    def test_set_value_enqueues_without_filtering_raw(self):
        from automation.tags.cvt import CVT
        from automation.tags.tag import Tag

        worker = WaveletWorker(tick_ms=50)
        from automation.workers import wavelet_worker as ww

        ww._worker = worker
        cvt = CVT()
        tag = Tag(
            name="Test.P",
            unit="adim",
            data_type="float",
            variable="Adimentional",
            filter_enabled=True,
            filter_level=3,
            id="abc123",
        )
        cvt._tags[tag.id] = tag
        cvt._name_index[tag.name] = tag.id
        ts = datetime(2026, 1, 1, 12, 0, 0)
        with patch("automation.tags.cvt._scope_owns_tag", return_value=True):
            for i in range(40):
                result = cvt.set_value(id=tag.id, value=float(i), timestamp=ts)
                self.assertEqual(result, float(i))

        self.assertEqual(tag.get_value(), 39.0)
        entry = worker._tags.get("Test.P")
        self.assertIsNotNone(entry)
        self.assertEqual(len(entry.filter._ring), 40)

    def test_deadband_skips_wavelet_ingest(self):
        from automation.tags.cvt import CVT
        from automation.tags.tag import Tag
        from automation.workers import wavelet_worker as ww

        worker = WaveletWorker(tick_ms=50)
        ww._worker = worker
        cvt = CVT()
        tag = Tag(
            name="Test.Dead",
            unit="adim",
            data_type="float",
            variable="Adimentional",
            filter_enabled=True,
            dead_band=0.5,
            id="deadband",
        )
        cvt._tags[tag.id] = tag
        cvt._name_index[tag.name] = tag.id
        ts = datetime(2026, 1, 1, 12, 0, 0)
        with patch("automation.tags.cvt._scope_owns_tag", return_value=True):
            cvt.set_value(id=tag.id, value=10.0, timestamp=ts)
            cvt.set_value(id=tag.id, value=10.2, timestamp=ts)
            cvt.set_value(id=tag.id, value=11.0, timestamp=ts)
        entry = worker._tags.get("Test.Dead")
        self.assertIsNotNone(entry)
        self.assertEqual(len(entry.filter._ring), 2)

    def test_bad_quality_increments_tag_counter(self):
        from automation.tags.cvt import CVT
        from automation.tags.tag import Tag

        cvt = CVT()
        tag = Tag(
            name="Test.Bad",
            unit="adim",
            data_type="float",
            variable="Adimentional",
            filter_enabled=True,
            id="badq",
        )
        cvt._tags[tag.id] = tag
        cvt._name_index[tag.name] = tag.id
        ts = datetime(2026, 1, 1, 12, 0, 0)
        with patch("automation.tags.cvt._scope_owns_tag", return_value=True):
            cvt.set_value(id=tag.id, value=1.0, timestamp=ts, quality=GOOD)
            cvt.set_value(id=tag.id, value=2.0, timestamp=ts, quality=BAD)
        self.assertEqual(tag._bad_samples_dropped, 1)
        self.assertEqual(tag.quality, UNCERTAIN)


if __name__ == "__main__":
    unittest.main()
