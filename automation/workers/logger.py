# -*- coding: utf-8 -*-
"""rackio/workers/logger.py

This module implements Logger Worker.
"""
import logging, time, datetime, os, shutil
from .worker import BaseWorker
from ..managers import DBManager
from ..managers import OPCUAClientManager
from ..logger.datalogger import DataLoggerEngine
from ..tags.cvt import CVTEngine
import sqlite3
from peewee import SqliteDatabase
from ..dbmodels.tags import TagValue
from ..dbmodels.alarms import AlarmSummary
from ..dbmodels.events import Events
from ..dbmodels.logs import Logs


class LoggerWorker(BaseWorker):

    def __init__(self, manager:DBManager, period:int=10.0):

        super(LoggerWorker, self).__init__()
        
        self._manager = manager
        self._period = period
        self.logger = DataLoggerEngine()
        self.opcua_client_manager = OPCUAClientManager()
        self.cvt = CVTEngine()
        self.sqlite_db = None
        self.sqlite_db_name = None

    def sqlite_db_backup(self):
        if self.sqlite_db:
            file_size_mb = os.path.getsize(self.sqlite_db_name) / 1024 / 1024 
            if file_size_mb > 1 * 1024: # 1 Gb: 
                timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
                name = self.sqlite_db_name.split(".db")[0]
                name = name.split(os.path.sep)[-1]
                backup_file = os.path.join(".", "db", "backups", f"{name}_{timestamp}.db")
                shutil.copy2(os.path.join(".", "db", "app.db"), backup_file)
                logger = logging.getLogger("pyautomation")
                logger.info(f"Backup creado: {backup_file}")
                # Empty TagValue 
                query = TagValue.delete()
                query.execute()
                # Empty Alarm Summary
                query = AlarmSummary.delete()
                query.execute()
                # Empty Events
                query = Events.delete()
                query.execute()
                # Empty Logs
                query = Logs.delete()
                query.execute()
                # Execute Vacuum to compact DB
                self.sqlite_db.close()
                conn = sqlite3.connect(self.sqlite_db_name)
                cur = conn.cursor()
                cur.execute("VACUUM;")
                conn.commit()
                conn.close()
                # Reopen DB connection
                from ..dbmodels import proxy
                self._db = self._manager.get_db()
                proxy.initialize(self._db)

        else:
            db = self.logger.logger.get_db()
            if db:
                if isinstance(db, SqliteDatabase):
                    self.sqlite_db = db
                    self.sqlite_db_name = db.database

    def run(self):
        r"""
        Documentation here
        """
        from .. import SEGMENT, MANUFACTURER
        _queue = self._manager.get_queue()

        while True:
            self.sqlite_db_backup()
            time.sleep(self._period)
            tags = list()

            while not _queue.empty():

                item = _queue.get(block=False)
                tag_name = item["tag"]
                tag = self.cvt.get_tag_by_name(name=tag_name)
                if tag:

                    if tag.manufacturer==MANUFACTURER and tag.segment==SEGMENT:

                        value = item['value']
                        timestamp = item["timestamp"]
                        tags.append({"tag":tag_name, "value":value, "timestamp":timestamp})

                    elif not MANUFACTURER and not SEGMENT:

                        value = item['value']
                        timestamp = item["timestamp"]
                        tags.append({"tag":tag_name, "value":value, "timestamp":timestamp})
    
            if tags:
                
                self.logger.write_tags(tags=tags)

            if self.stop_event.is_set():
                logger = logging.getLogger("pyautomation")
                logger.info("Alarm worker shutdown successfully!")
                break

            # Check if OPCUA Client are disconnected and reconnect them
            for opcua_client in self.opcua_client_manager._clients.values():

                opcua_client.reconnect()