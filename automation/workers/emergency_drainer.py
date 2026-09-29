# -*- coding: utf-8 -*-
"""Drain the SAF ring off the acquisition thread once it crosses 80% full.

Shares the journal writer lock with SafJournalFlusher. It never runs on the
producer and never opens a second SQLite writer.
"""
from __future__ import annotations

import threading


class EmergencyDrainer(threading.Thread):
    def __init__(self, journal):
        super().__init__(name="SafEmergencyDrainer", daemon=True)
        self.journal = journal

    def run(self) -> None:
        self.journal._emergency_loop()
