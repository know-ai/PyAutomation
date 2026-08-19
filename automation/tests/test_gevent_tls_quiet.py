# -*- coding: utf-8 -*-
"""Tests for gevent TLS quiet hooks."""
from __future__ import annotations

import unittest

from automation.utils.gevent_tls_quiet import install_gevent_tls_quiet_hooks


class TestGeventTlsQuiet(unittest.TestCase):
    def test_install_is_idempotent(self):
        install_gevent_tls_quiet_hooks()
        install_gevent_tls_quiet_hooks()


if __name__ == "__main__":
    unittest.main()
