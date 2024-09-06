# -*- coding: utf-8 -*-
"""automation/workers/logger.py

This module implements Logger Worker.
"""
from .worker import BaseWorker
from threading import Thread
from time import sleep


class LoggerScheduler():

    def __init__(self, manager, period:float):

        self.manager = manager
        self._stop = False

        if period > 0:
            
            self._period = period

    def stop(self):

        self._stop = True
    
    def run(self):
        
        while True:

            queue = self.manager.get_queue()

            while not queue.empty():

                fn, attrs = queue.get()
                # NOTIFY TO DBMANAGER IN A SAFE THREAD MECHANISM TO OPERATE INTO DATABASE
                method = getattr(self.manager.logger, fn)
                method(**attrs)
            
            sleep(self._period)


class LoggerWorker(BaseWorker):

    def __init__(self, manager, period:float):

        super(LoggerWorker, self).__init__()
        
        self._manager = manager
        self.scheduler = LoggerScheduler(manager=self._manager, period=period)

    def run(self):
        print(f"automation/workers/logger.py LoggerWorker run executed")
        thread = Thread(target=self.scheduler.run)
        thread.start()
        
    def stop(self):

        self.scheduler.stop()