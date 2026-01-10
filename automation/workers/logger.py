# -*- coding: utf-8 -*-
"""automation/workers/logger.py

This module implements the Logger Worker, responsible for persisting data to the database.
"""
import logging, time, datetime, os, shutil
from .worker import BaseWorker
from ..managers import DBManager
from ..opcua.models import Client
from ..logger.datalogger import DataLoggerEngine
from ..tags.cvt import CVTEngine
import sqlite3
from peewee import SqliteDatabase
from ..dbmodels.tags import TagValue
from ..dbmodels.alarms import AlarmSummary
from ..dbmodels.events import Events
from ..dbmodels.logs import Logs


class LoggerWorker(BaseWorker):
    r"""
    A background worker thread that handles database operations.

    It performs the following tasks:
    1. Periodically writes buffered tag data to the database.
    2. Manages SQLite database backups and maintenance (vacuuming).
    3. Handles database reconnection logic.
    4. Checks and maintains OPC UA client connections.
    """

    def __init__(self, manager:DBManager, period:float=10.0):
        r"""
        Initializes the LoggerWorker.

        **Parameters:**

        * **manager** (DBManager): The database manager instance.
        * **period** (float): The execution interval in seconds.
        """

        super(LoggerWorker, self).__init__()
        
        self._manager = manager
        self._period = period
        self.logger = DataLoggerEngine()
        self.cvt = CVTEngine()
        self.sqlite_db = None
        self.sqlite_db_name = None

    def sqlite_db_backup(self):
        r"""
        Performs a backup of the SQLite database if it exceeds 1GB.

        It copies the database file to the `db/backups` directory, clears the
        historical tables (TagValue, AlarmSummary, Events, Logs), and performs a VACUUM
        command to reclaim disk space.
        """
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


    def check_opcua_connection(self):
        r"""
        Checks the status of OPC UA clients and attempts reconnection if necessary.
        """
        from automation import PyAutomation
        app = PyAutomation()
        if app.opcua_client_manager._clients:
            # Crear una copia de los items para evitar RuntimeError si el diccionario cambia durante la iteración
            # Esto puede ocurrir si reconnect() o alguna otra operación modifica _clients
            clients_snapshot = list(app.opcua_client_manager._clients.items())
            for client_name, opcua_client in clients_snapshot:
                # Verificar que el cliente aún existe en el diccionario (puede haber sido removido)
                if client_name not in app.opcua_client_manager._clients:
                    continue
                    
                # Verificar que el cliente en el diccionario es el mismo que tenemos en la snapshot
                if app.opcua_client_manager._clients[client_name] is not opcua_client:
                    continue

                if isinstance(opcua_client, Client):
                    try:
                        opcua_client.reconnect()
                    except Exception as e:
                        # Si hay un error durante la reconexión, registrar pero continuar con otros clientes
                        logging.error(f"Error reconnecting OPC UA client '{client_name}': {e}")
        else:
            
            app.load_opcua_clients_from_db()

    def get_tags_from_queue(self, _queue):
        r"""
        Retrieves tag data from the queue and filters it based on configuration.

        **Parameters:**

        * **_queue** (Queue): The queue containing tag updates.

        **Returns:**

        * **list**: A list of tag data dictionaries ready for insertion.
        """
        from .. import SEGMENT, MANUFACTURER
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

        return tags

    def reconnect_to_db(self):
        r"""
        Attempts to reconnect to the database if the connection is lost.
        """
        from automation import PyAutomation
        app = PyAutomation()
        
        if self.db_reconnection:
            
            logging.critical("Trying reconnect to DB...")
        
        self.db_reconnection = False
        db_connected = app.reconnect_to_db()
                
        if db_connected:
            
            logging.critical("Reconnection successfully")
            self.db_reconnection = True

    def run(self):
        r"""
        Main worker loop.

        Continuously:
        1. Checks database connectivity.
        2. Backs up SQLite DB if needed.
        3. Writes queued tags to the database.
        4. Reconnects to DB if connection lost.
        5. Checks OPC UA connections.
        6. Sleeps for the configured period.
        """       
        _queue = self._manager.get_queue()
        self.db_reconnection = True

        while True:

            if self.db_reconnection:

                db_connection = self.logger.logger.check_connectivity()
            
                if db_connection:
                    self.sqlite_db_backup()
                    tags = self.get_tags_from_queue(_queue=_queue)
            
                    if tags:
                        
                        self.logger.write_tags(tags=tags)
                    
                else:

                    self.reconnect_to_db()
            
            else:

                self.reconnect_to_db()

            self.check_opcua_connection()

            if self.stop_event.is_set():
                logging.critical("Alarm worker shutdown successfully!")
                break

            time.sleep(self._period)
