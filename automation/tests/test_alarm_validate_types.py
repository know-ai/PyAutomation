# -*- coding: utf-8 -*-
"""@validate_types must accept every kwarg of alarm APIs (ack/update/create/delete)."""
from __future__ import annotations

import inspect
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock

from automation.alarms import Alarm
from automation.core import PyAutomation
from automation.managers.alarms import AlarmManager
from automation.utils.decorators import validate_types


def _extract_validate_types(fn):
    """Return (validations, original_func) for a @validate_types wrapper, else (None, None)."""
    seen: set[int] = set()

    def walk(current):
        if current is None or not callable(current):
            return None, None
        marker = id(current)
        if marker in seen:
            return None, None
        seen.add(marker)
        code = getattr(current, "__code__", None)
        closure = getattr(current, "__closure__", None)
        if code is not None and closure:
            closed = {
                name: cell.cell_contents
                for name, cell in zip(code.co_freevars, closure)
            }
            if "validations" in closed:
                return dict(closed["validations"]), closed.get("func")
            for value in closed.values():
                found_validations, found_func = walk(value)
                if found_validations is not None:
                    return found_validations, found_func
        return walk(getattr(current, "__wrapped__", None))

    return walk(fn)


def _keyword_params(func) -> list[str]:
    signature = inspect.signature(func)
    names = []
    for parameter in signature.parameters.values():
        if parameter.name == "self":
            continue
        if parameter.kind in (
            inspect.Parameter.POSITIONAL_OR_KEYWORD,
            inspect.Parameter.KEYWORD_ONLY,
        ):
            names.append(parameter.name)
    return names


def _methods_with_validate_types(cls):
    for name, member in inspect.getmembers(cls, predicate=inspect.isfunction):
        validations, original = _extract_validate_types(member)
        if validations is None:
            continue
        yield name, validations, original or member


class TestValidateTypesAllowsSignatureKwargs(unittest.TestCase):
    def test_undeclared_signature_kwarg_does_not_keyerror(self):
        @validate_types(a=int, output=int)
        def sample(a: int, user=None):
            return a

        self.assertEqual(sample(a=1, user="operator"), 1)

    def test_unknown_kwarg_still_keyerrors(self):
        @validate_types(a=int, output=int)
        def sample(a: int):
            return a

        with self.assertRaises(KeyError) as caught:
            sample(a=1, nope=True)
        self.assertIn("nope", str(caught.exception))

    def test_var_keyword_accepts_extra_keys(self):
        @validate_types(a=int, output=int)
        def sample(a: int, **kwargs):
            return a

        self.assertEqual(sample(a=1, extra=True), 1)


class TestAlarmMethodsDeclareValidateTypes(unittest.TestCase):
    def _assert_class_alarm_methods(self, cls, name_filter=None):
        missing = {}
        checked = []
        for name, validations, original in _methods_with_validate_types(cls):
            if name_filter is not None and not name_filter(name):
                continue
            checked.append(name)
            absent = [param for param in _keyword_params(original) if param not in validations]
            if absent:
                missing[f"{cls.__name__}.{name}"] = absent
        self.assertTrue(checked, f"No @validate_types methods matched on {cls.__name__}")
        self.assertEqual(missing, {}, f"validate_types missing kwargs: {missing}")

    def test_pyautomation_alarm_methods_cover_signature(self):
        self._assert_class_alarm_methods(
            PyAutomation,
            name_filter=lambda name: "alarm" in name.lower(),
        )

    def test_alarm_notify_covers_signature(self):
        self._assert_class_alarm_methods(Alarm)

    def test_alarm_manager_methods_cover_signature(self):
        methods = list(_methods_with_validate_types(AlarmManager))
        if not methods:
            return
        missing = {}
        for name, validations, original in methods:
            absent = [param for param in _keyword_params(original) if param not in validations]
            if absent:
                missing[name] = absent
        self.assertEqual(missing, {})


class TestUpdateAlarmAcceptsUser(unittest.TestCase):
    def test_update_alarm_with_user_reaches_manager(self):
        app = PyAutomation.__new__(PyAutomation)
        alarm = MagicMock()
        alarm.tag = MagicMock()
        app.alarm_manager = MagicMock()
        app.alarm_manager.get_alarm.return_value = alarm
        app.alarm_manager.put.return_value = (alarm, "ok")
        app._refresh_node_scope = MagicMock(
            return_value=SimpleNamespace(enabled=False, owns_tag=lambda _tag: True)
        )
        app.is_db_connected = MagicMock(return_value=False)
        app.cvt = MagicMock()

        PyAutomation.update_alarm(
            app,
            id="alarm-1",
            description="ack path",
            user=None,
        )
        app.alarm_manager.put.assert_called_once()
        self.assertEqual(app.alarm_manager.put.call_args.kwargs.get("user"), None)


if __name__ == "__main__":
    unittest.main()
