# -*- coding: utf-8 -*-
"""AlarmTransitionWorker returns non-resident historian sockets after a batch."""
from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from automation.alarms.runtime import TransitionWorker


class TestAlarmTransitionWorkerSockets(unittest.TestCase):
    def test_process_batch_releases_historian_socket(self):
        runtime = MagicMock()
        worker = TransitionWorker(runtime, interval_ms=50)
        event = SimpleNamespace(enqueued_at=0.0)
        with patch(
            "automation.utils.db_connections.historian_role_scope",
        ) as scope, patch(
            "automation.utils.db_connections.keep_historian_socket",
            return_value=False,
        ), patch(
            "automation.utils.db_connections.close_current_greenlet_connection",
        ) as close, patch(
            "automation.PyAutomation",
            return_value=SimpleNamespace(_db="db"),
        ):
            scope.return_value.__enter__ = MagicMock(return_value=None)
            scope.return_value.__exit__ = MagicMock(return_value=False)
            worker._process_batch([event])

        runtime.process_event.assert_called_once_with(event)
        close.assert_called_once_with("db")
