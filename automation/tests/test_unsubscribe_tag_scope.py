# -*- coding: utf-8 -*-
"""Tag edits must not drop leak-detection subscriptions (only DAQ is recycled)."""
from __future__ import annotations

import unittest
from unittest.mock import MagicMock

from ..managers.state_machine import StateMachineManager


def _machine(name: str, classification: str) -> MagicMock:
    machine = MagicMock()
    machine.name.value = name
    machine.classification.value = classification
    machine.unsubscribe_to = MagicMock()
    machine.get_subscribed_tags.return_value = {"PI_01": object()}
    return machine


class TestUnsubscribeTagScope(unittest.TestCase):
    def test_tag_edit_unsubscribes_daq_only(self):
        leak = _machine("LDS", "Leak Detection")
        daq = _machine("DAQ-1000", "Data Acquisition System")
        mgr = StateMachineManager()
        mgr._machines = [(leak, 1.0, "async"), (daq, 1.0, "async")]
        tag = MagicMock()
        mgr.unsubscribe_tag(tag, acquisition_only=True)
        leak.unsubscribe_to.assert_not_called()
        daq.unsubscribe_to.assert_called_once_with(tag=tag)

    def test_tag_delete_unsubscribes_all_machines(self):
        leak = _machine("LDS", "Leak Detection")
        daq = _machine("DAQ-1000", "Data Acquisition System")
        mgr = StateMachineManager()
        mgr._machines = [(leak, 1.0, "async"), (daq, 1.0, "async")]
        tag = MagicMock()
        mgr.unsubscribe_tag(tag, acquisition_only=False)
        leak.unsubscribe_to.assert_called_once_with(tag=tag)
        daq.unsubscribe_to.assert_called_once_with(tag=tag)
