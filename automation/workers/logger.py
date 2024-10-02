# -*- coding: utf-8 -*-
"""rackio/workers/logger.py

This module implements Logger Worker.
"""
import logging, time
from .worker import BaseWorker
from ..managers import DBManager
from ..logger.datalogger import DataLoggerEngine


class LoggerWorker(BaseWorker):

    def __init__(self, manager:DBManager, period:int=10.0):

        super(LoggerWorker, self).__init__()
        
        self._manager = manager
        self._period = period
        self.logger = DataLoggerEngine()

    def run(self):
        r"""
        Documentation here
        """
        _queue = self._manager.get_queue()

        while True:

            time.sleep(self._period)
            tags = list()
            while not _queue.empty():

                item = _queue.get()
                tag = item["tag"]
                value = item["value"]
                timestamp = item["timestamp"]
                tags.append({"tag":tag, "value":value, "timestamp":timestamp})

            self.logger.write_tags(tags=tags)

            if self.stop_event.is_set():
                
                logging.info("Alarm worker shutdown successfully!")
                break