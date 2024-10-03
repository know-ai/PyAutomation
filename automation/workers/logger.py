# -*- coding: utf-8 -*-
"""rackio/workers/logger.py

This module implements Logger Worker.
"""
import logging, time
from .worker import BaseWorker
from ..managers import DBManager
from ..logger.datalogger import DataLoggerEngine
from ..tags.cvt import CVTEngine


class LoggerWorker(BaseWorker):

    def __init__(self, manager:DBManager, period:int=10.0):

        super(LoggerWorker, self).__init__()
        
        self._manager = manager
        self._period = period
        self.logger = DataLoggerEngine()
        self.cvt = CVTEngine()

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
                tag_name = item["tag"]
                tag = self.cvt.get_tag_by_name(name=tag_name)
                if tag:
                    to_unit = tag.get_display_unit()
                    value = item['value'].convert(to_unit=to_unit)
                    timestamp = item["timestamp"]
                    tags.append({"tag":tag_name, "value":value, "timestamp":timestamp})

            self.logger.write_tags(tags=tags)

            if self.stop_event.is_set():
                
                logging.info("Alarm worker shutdown successfully!")
                break