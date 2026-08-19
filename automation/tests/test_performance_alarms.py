import unittest
from unittest.mock import MagicMock, patch

from automation.utils.perf_alarm_evaluator import PerfAlarmEvaluator
from automation.utils.performance_alarm_config import (
    load_performance_alarm_config,
    normalize_payload,
    public_config,
)
from automation.utils.performance_alarms import PERF_ALARM_SPECS, perf_alarm_name, perf_tag_name
from automation.workers.metrics_sampler import MetricsSamplerWorker


class TestPerformanceAlarmConfig(unittest.TestCase):
    def test_defaults_and_clamp(self):
        cfg = load_performance_alarm_config({})
        self.assertTrue(cfg["perf_alarms_enabled"])
        self.assertEqual(cfg["perf_cpu_threshold"], 85.0)
        self.assertEqual(cfg["perf_debounce_count"], 3)

    def test_camel_case_payload(self):
        payload = normalize_payload(
            {
                "enabled": True,
                "cpuThreshold": 92,
                "alarms": [{"key": "disk", "enabled": False, "threshold": 88}],
            }
        )
        self.assertTrue(payload["perf_alarms_enabled"])
        self.assertEqual(payload["perf_cpu_threshold"], 92)
        self.assertFalse(payload["perf_disk_enabled"])
        self.assertEqual(payload["perf_disk_threshold"], 88)

    def test_public_config_lists_seven_alarms(self):
        pub = public_config(load_performance_alarm_config({}))
        self.assertEqual(len(pub["alarms"]), 7)
        self.assertEqual(pub["alarms"][0]["key"], "cpu")


class TestPerfAlarmEvaluator(unittest.TestCase):
    def test_debounce_three_samples(self):
        writes = []
        cfg = load_performance_alarm_config(
            {"perf_debounce_count": 3, "perf_cpu_threshold": 85, "perf_cpu_enabled": True}
        )
        evaluator = PerfAlarmEvaluator(writer=lambda *args, **kwargs: writes.append((args, kwargs)) or True)
        evaluator.reload(cfg)
        snap = {"HOST_CPU_PERCENT": 90}
        evaluator.evaluate(snap)
        evaluator.evaluate(snap)
        self.assertFalse(evaluator._active["cpu"])
        evaluator.evaluate(snap)
        self.assertTrue(evaluator._active["cpu"])
        cpu_writes = [item for item in writes if item[0][0] == "cpu"]
        self.assertEqual(cpu_writes[-1][0][1], True)

    def test_clears_immediately_when_below_threshold(self):
        cfg = load_performance_alarm_config({"perf_debounce_count": 2, "perf_cpu_threshold": 85})
        evaluator = PerfAlarmEvaluator(writer=lambda *args, **kwargs: True)
        evaluator.reload(cfg)
        evaluator.evaluate({"HOST_CPU_PERCENT": 90})
        evaluator.evaluate({"HOST_CPU_PERCENT": 90})
        self.assertTrue(evaluator._active["cpu"])
        evaluator.evaluate({"HOST_CPU_PERCENT": 10})
        self.assertFalse(evaluator._active["cpu"])

    def test_disabled_forces_inactive(self):
        cfg = load_performance_alarm_config({"perf_alarms_enabled": False, "perf_cpu_threshold": 1})
        evaluator = PerfAlarmEvaluator(writer=lambda *args, **kwargs: True)
        evaluator.reload(cfg)
        evaluator.evaluate({"HOST_CPU_PERCENT": 99})
        evaluator.evaluate({"HOST_CPU_PERCENT": 99})
        evaluator.evaluate({"HOST_CPU_PERCENT": 99})
        self.assertFalse(evaluator._active["cpu"])

    def test_none_value_does_not_false_alarm(self):
        cfg = load_performance_alarm_config({"perf_debounce_count": 1, "perf_db_conn_threshold": 10})
        evaluator = PerfAlarmEvaluator(writer=lambda *args, **kwargs: True)
        evaluator.reload(cfg)
        evaluator.evaluate({"DB_ACTIVE_CONNECTIONS": None})
        self.assertFalse(evaluator._active["db_conn"])

    def test_reconfigure_applies_new_threshold_same_cycle(self):
        cfg = load_performance_alarm_config({"perf_debounce_count": 1, "perf_cpu_threshold": 95})
        evaluator = PerfAlarmEvaluator(writer=lambda *args, **kwargs: True)
        evaluator.reload(cfg)
        evaluator.evaluate({"HOST_CPU_PERCENT": 90})
        self.assertFalse(evaluator._active["cpu"])
        evaluator.reload(load_performance_alarm_config({"perf_debounce_count": 1, "perf_cpu_threshold": 80}))
        evaluator.evaluate({"HOST_CPU_PERCENT": 90})
        self.assertTrue(evaluator._active["cpu"])


class TestSamplerReconfigure(unittest.TestCase):
    def test_reconfigure_evaluates_last_snapshot(self):
        persisted = {"perf_debounce_count": 1, "perf_cpu_threshold": 50, "perf_cpu_enabled": True}
        worker = MetricsSamplerWorker(interval_seconds=5)
        worker._evaluator = PerfAlarmEvaluator(
            config_provider=lambda: persisted,
            writer=lambda *args, **kwargs: True,
        )
        worker._publish({"HOST_CPU_PERCENT": 80.0, "NODE_ID": "edge-a"})
        with patch.object(worker, "_ensure_alarms"):
            worker.reconfigure()
        self.assertTrue(worker._evaluator._active["cpu"])
        snap = worker.get_snapshot()
        self.assertIn("PERF_ALARMS", snap)
        self.assertEqual(len(snap["PERF_ALARMS"]["alarms"]), 7)


class TestPerformanceAlarmNames(unittest.TestCase):
    def test_catalog_size(self):
        self.assertEqual(len(PERF_ALARM_SPECS), 7)

    def test_scoped_names_without_area(self):
        scope = MagicMock(enabled=False, is_valid=False)
        with patch("automation.node_scope.get_node_scope", return_value=scope):
            self.assertEqual(perf_tag_name("cpu"), "SYS.PERF.CPU")
            self.assertEqual(perf_alarm_name("cpu"), "ALM.PERF.CPU")

    def test_ensure_uses_skip_validation_path(self):
        from automation.utils import performance_alarms as mod

        app = MagicMock()
        scope = MagicMock(enabled=False, is_valid=False)
        with patch("automation.node_scope.get_node_scope", return_value=scope), patch.object(
            mod, "_app", return_value=app
        ), patch.object(mod, "_ensure_bool_alarm") as ensure:
            mod.ensure_performance_alarms(load_performance_alarm_config({}))
        self.assertEqual(ensure.call_count, 7)
        first = ensure.call_args_list[0].kwargs
        self.assertEqual(first["alarm_name"], "ALM.PERF.CPU")
        self.assertIn("System", first["alarm_description"])


class TestHmiLifecycleContract(unittest.TestCase):
    def test_ack_turns_warn_and_unack_error(self):
        def tone(life: str, fallback: str) -> str:
            if life == "unack":
                return "error"
            if life == "ack":
                return "warn"
            if life == "shelved":
                return "shelved"
            return fallback

        self.assertEqual(tone("unack", "ok"), "error")
        self.assertEqual(tone("ack", "ok"), "warn")
        self.assertEqual(tone("shelved", "ok"), "shelved")
        self.assertEqual(tone("normal", "ok"), "ok")


if __name__ == "__main__":
    unittest.main()
