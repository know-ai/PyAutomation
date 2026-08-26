# -*- coding: utf-8 -*-
"""DomainConfigurable contract: neutrality of machines API and serialize()."""
from __future__ import annotations

import re
import unittest
from pathlib import Path
from unittest.mock import patch

from flask import Flask

from ..domain_config import (
    audit_domain_config_change,
    diff_domain_config,
    domain_config_action,
    supports_domain_config,
    unknown_generic_attribute_keys,
)
from ..state_machine import StateMachineCore

_REPO_ROOT = Path(__file__).resolve().parents[2]
_PRODUCT_TOKEN_RE = re.compile(
    r"\bnpw\b|\bppa\b|\blds\b|\bpfm\b|\bobserver\b|leak detection",
    re.IGNORECASE,
)
_GUARDED_PATHS = (
    Path("automation/modules/machines/resources/machines.py"),
    Path("hmi/src/pages/MachinesDetailed.tsx"),
    Path("hmi/src/services/machines.ts"),
    Path("automation/pages/components/machines.py"),
    Path("automation/pages/callbacks/machines_detailed.py"),
)


class GenericMotor(StateMachineCore):
    def __init__(self):
        super().__init__(name="GenericMotor", interval=1.0, classification="Custom")


class ConfigurableMotor(StateMachineCore):
    def __init__(self):
        super().__init__(name="ConfigurableMotor", interval=1.0, classification="Custom")
        self._config = {"gain": 1.5}

    def get_ui_schema(self) -> dict:
        return {
            "version": 1,
            "title": "Demo",
            "sections": [
                {
                    "id": "main",
                    "label": "Main",
                    "fields": [
                        {"key": "gain", "type": "number", "label": "Gain", "min": 0, "max": 10}
                    ],
                }
            ],
            "ui_hints": {"threshold_unit": "%"},
        }

    def get_config(self) -> dict:
        return dict(self._config)

    def put_config(self, payload: dict) -> dict:
        if not isinstance(payload, dict):
            raise TypeError("payload must be an object")
        if "gain" in payload and float(payload["gain"]) < 0:
            raise ValueError("gain must be >= 0")
        self._config.update(payload)
        return dict(self._config)


class TestDomainConfigHelpers(unittest.TestCase):
    def test_generic_motor_does_not_support_domain_config(self):
        machine = GenericMotor()
        self.assertFalse(supports_domain_config(machine))
        self.assertFalse(machine.serialize().get("has_domain_config"))

    def test_configurable_motor_exposes_has_domain_config(self):
        machine = ConfigurableMotor()
        self.assertTrue(supports_domain_config(machine))
        self.assertTrue(machine.serialize().get("has_domain_config"))
        self.assertEqual(machine.get_config()["gain"], 1.5)
        updated = machine.put_config({"gain": 2.0})
        self.assertEqual(updated["gain"], 2.0)

    def test_put_config_validation_error(self):
        machine = ConfigurableMotor()
        with self.assertRaises(ValueError):
            machine.put_config({"gain": -1})

    def test_unknown_generic_attribute_keys_reject_domain_fields(self):
        unknown = unknown_generic_attribute_keys(
            {"threshold": 1.0, "detection_threshold_mode": "probability"}
        )
        self.assertEqual(unknown, ["detection_threshold_mode"])
        message = (
            "Unsupported attribute(s) for generic configuration: "
            f"{', '.join(unknown)}. Use /domain-config for domain fields."
        )
        self.assertNotIn("ppa", message.lower())
        self.assertNotIn("npw", message.lower())

    def test_whitelist_accepts_generic_keys_only(self):
        self.assertEqual(
            unknown_generic_attribute_keys(
                {
                    "threshold": 1,
                    "on_delay": 2,
                    "interval": 1,
                    "execution_interval": 1,
                    "sample_interval": None,
                    "sample_overrides": {},
                    "buffer_size": 10,
                }
            ),
            [],
        )

    def test_domain_config_action_and_diff(self):
        self.assertEqual(domain_config_action({"gain": 1}), "save")
        self.assertEqual(domain_config_action({"_reset": True}), "reset")
        self.assertEqual(domain_config_action({"gain": 1, "_set_factory": True}), "set_factory")
        schema = ConfigurableMotor().get_ui_schema()
        changes = diff_domain_config({"gain": 1.5}, {"gain": 3.0, "_warnings": "x"}, schema)
        self.assertEqual(len(changes), 1)
        self.assertEqual(changes[0]["label"], "Gain")
        self.assertEqual(changes[0]["from"], "1.5")
        self.assertEqual(changes[0]["to"], "3.0")

    def test_audit_domain_config_emits_friendly_event(self):
        calls = []

        def fake_persist(**kwargs):
            calls.append(kwargs)
            return True

        schema = ConfigurableMotor().get_ui_schema()
        with patch(
            "automation.utils.system_event_audit.persist_system_event",
            side_effect=fake_persist,
        ):
            audit_domain_config_change(
                machine_name="ConfigurableMotor",
                payload={"gain": 3.0},
                before={"gain": 1.5},
                after={"gain": 3.0},
                schema=schema,
                user=object(),
            )
        self.assertEqual(len(calls), 1)
        self.assertIn("Gain", calls[0]["message"])
        self.assertIn("1.5", calls[0]["description"])
        self.assertIn("3.0", calls[0]["description"])
        self.assertEqual(calls[0]["classification"], "Configuration")


class TestDomainConfigResource(unittest.TestCase):
    def setUp(self):
        self.flask = Flask(__name__)

    def test_resolve_generic_motor_is_404(self):
        from ..modules.machines.resources import machines as machines_mod

        machine = GenericMotor()
        with patch.object(machines_mod, "app") as mock_app, patch.object(
            machines_mod, "_machine_scope_error", return_value=None
        ):
            mock_app.get_machine.return_value = machine
            resolved, error = machines_mod._resolve_domain_machine("GenericMotor")
        self.assertIsNone(resolved)
        self.assertEqual(error[1], 404)
        self.assertIn("no domain configuration", error[0]["message"].lower())

    def test_resolve_configurable_motor(self):
        from ..modules.machines.resources import machines as machines_mod

        machine = ConfigurableMotor()
        with patch.object(machines_mod, "app") as mock_app, patch.object(
            machines_mod, "_machine_scope_error", return_value=None
        ):
            mock_app.get_machine.return_value = machine
            resolved, error = machines_mod._resolve_domain_machine("ConfigurableMotor")
        self.assertIsNone(error)
        self.assertIs(resolved, machine)

    def test_domain_config_get_put_round_trip(self):
        from ..modules.machines.resources import machines as machines_mod

        machine = ConfigurableMotor()
        resource = machines_mod.MachineDomainConfigResource()
        fake_user = object()
        with patch.object(machines_mod, "app") as mock_app, patch.object(
            machines_mod, "_machine_scope_error", return_value=None
        ), patch(
            "automation.extensions.api.Api._resolve_session_user",
            return_value=(fake_user, None, 200),
        ), patch(
            "automation.utils.system_event_audit.persist_system_event",
            return_value=True,
        ):
            mock_app.get_machine.return_value = machine
            with self.flask.test_request_context(
                "/api/machines/ConfigurableMotor/domain-config",
                method="GET",
                headers={"X-API-KEY": "test"},
            ):
                payload, status = resource.get("ConfigurableMotor")
            self.assertEqual(status, 200)
            self.assertEqual(payload["config"]["gain"], 1.5)
            self.assertEqual(payload["schema"]["version"], 1)

            with self.flask.test_request_context(
                "/api/machines/ConfigurableMotor/domain-config",
                method="PUT",
                json={"gain": 3.0},
                headers={"X-API-KEY": "test"},
            ):
                updated, status = resource.put("ConfigurableMotor")
            self.assertEqual(status, 200)
            self.assertEqual(updated["status"], "success")
            self.assertEqual(updated["config"]["gain"], 3.0)

            with self.flask.test_request_context(
                "/api/machines/ConfigurableMotor/domain-config",
                method="PUT",
                json={"gain": -2},
                headers={"X-API-KEY": "test"},
            ):
                err, status = resource.put("ConfigurableMotor")
            self.assertEqual(status, 400)
            self.assertIn("gain", err["message"].lower())

    def test_attributes_reject_domain_field(self):
        from ..modules.machines.resources import machines as machines_mod

        machine = GenericMotor()
        resource = machines_mod.MachineAttributesResource()
        fake_user = object()
        with patch.object(machines_mod, "app") as mock_app, patch.object(
            machines_mod, "_machine_scope_error", return_value=None
        ), patch(
            "automation.extensions.api.Api._resolve_session_user",
            return_value=(fake_user, None, 200),
        ):
            mock_app.get_machine.return_value = machine
            with self.flask.test_request_context(
                "/api/machines/GenericMotor/attributes",
                method="PUT",
                json={"detection_threshold_mode": "probability"},
                headers={"X-API-KEY": "test"},
            ):
                payload, status = resource.put("GenericMotor")
        self.assertEqual(status, 400)
        message = payload["message"].lower()
        self.assertIn("detection_threshold_mode", message)
        self.assertNotIn("ppa", message)
        self.assertNotIn("npw", message)


class TestNoProductEngineNameBranches(unittest.TestCase):
    def test_guarded_sources_have_no_product_tokens(self):
        violations = []
        for rel in _GUARDED_PATHS:
            path = _REPO_ROOT / rel
            self.assertTrue(path.is_file(), f"missing {rel}")
            text = path.read_text(encoding="utf-8")
            for match in _PRODUCT_TOKEN_RE.finditer(text):
                line_no = text[: match.start()].count("\n") + 1
                violations.append(f"{rel}:{line_no}: {match.group(0)!r}")
        self.assertEqual(
            violations,
            [],
            "product tokens leaked into framework machines UI/API:\n" + "\n".join(violations),
        )
