# -*- coding: utf-8 -*-
"""Reconnect integrity: Events/outbox must not raise InterfaceError."""
from __future__ import annotations

import unittest
from unittest.mock import patch

from automation.modules.users.roles import Role
from automation.modules.users.users import User


def _system_user() -> User:
    return User(
        username="system",
        role=Role(name="sudo", level=0),
        email="system@local",
        password="x",
        name="System",
        lastname="Intelcon",
    )


class TestEventsCreateStaleLink(unittest.TestCase):
    def test_stale_user_lookup_returns_none_not_raise(self):
        from automation.dbmodels import events as events_mod

        with patch(
            "automation.catalog.ensure_historian.resolve_historian_user_row",
            side_effect=RuntimeError("connection already closed"),
        ):
            row, msg = events_mod.Events.create(
                message="Catalog sync completed",
                user=_system_user(),
            )
        self.assertIsNone(row)
        self.assertTrue("stale" in msg.lower() or "failed" in msg.lower())

    def test_missing_user_soft_fails(self):
        from automation.dbmodels import events as events_mod

        with patch(
            "automation.catalog.ensure_historian.resolve_historian_user_row",
            return_value=None,
        ):
            row, msg = events_mod.Events.create(message="test", user=_system_user())
        self.assertIsNone(row)
        self.assertIn("journal will retry", msg)


class TestResolveHistorianUser(unittest.TestCase):
    def test_stale_read_returns_none(self):
        from automation.catalog.ensure_historian import resolve_historian_user_row

        with patch(
            "automation.dbmodels.users.Users.read_by_username",
            side_effect=RuntimeError("InterfaceError: connection already closed"),
        ):
            self.assertIsNone(resolve_historian_user_row(_system_user()))
