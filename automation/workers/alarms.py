# -*- coding: utf-8 -*-
"""rackio/workers/alarms.py

This module implements Alarm Worker.
"""
import logging, time
from .worker import BaseWorker
from ..managers import AlarmManager


class AlarmWorker(BaseWorker):

    def __init__(self, manager:AlarmManager, period=1.0):

        super(AlarmWorker, self).__init__()
        
        self._manager = manager
        self._period = period
        self._manager.attach_all()

    def run(self):
        r"""
        Documentation here
        """
        _queue = self._manager.get_queue()

        while True:

            time.sleep(self._period)

            while not _queue.empty():

                item = _queue.get()
                _tag = item["tag"]
                self._manager.execute(_tag)

            if self.stop_event.is_set():
                
                logging.info("Alarm worker shutdown successfully!")
                break