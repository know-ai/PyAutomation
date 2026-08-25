# -*- coding: utf-8 -*-
"""automation/workers/logger.py

This module implements the Logger Worker, responsible for persisting data to the database.
"""
import logging, time, datetime, os
from threading import Event as ThreadEvent
from .worker import BaseWorker
from ..managers import DBManager
from ..opcua.models import Client
from ..logger.datalogger import DataLoggerEngine
from ..tags.cvt import CVTEngine
import sqlite3
from peewee import SqliteDatabase

# An unconfigured edge must stay idle. Do not hit PG every logger period
# looking for a PLC that the operator has not created yet.
_EMPTY_OPC_RETRY_S = (60.0, 180.0, 300.0)


def _scope_owns_node(owner_node) -> bool:
    try:
        from ..node_scope import get_node_scope

        scope = get_node_scope()
    except (ImportError, AttributeError):
        return True
    if not getattr(scope, "enabled", False):
        return True
    if not getattr(scope, "is_valid", False):
        return False
    try:
        return bool(scope.owns_node(owner_node))
    except Exception:
        return False


def _scope_owns_tag(tag) -> bool:
    try:
        from ..node_scope import get_node_scope

        scope = get_node_scope()
    except (ImportError, AttributeError):
        return True
    if not getattr(scope, "enabled", False):
        return True
    if not getattr(scope, "is_valid", False) or tag is None:
        return False
    try:
        return bool(scope.owns_tag(tag))
    except Exception:
        return False


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
        self.name = "LoggerWorker"
        self._wake = ThreadEvent()
        self.last_cycle_utc = None
        
        self._manager = manager
        self._period = period
        self.logger = DataLoggerEngine()
        self.cvt = CVTEngine()
        self.sqlite_db = None
        self.sqlite_db_name = None
        self._opcua_empty_until = 0.0
        self._opcua_empty_step = 0

    def stop(self):
        super(LoggerWorker, self).stop()
        self._wake.set()

    def request_cycle(self) -> None:
        """Wake the loop so SAF retry does not wait for logger_period."""
        self._wake.set()

    def sqlite_db_backup(self):
        r"""
        Archives a SQLite historian with VACUUM INTO.

        Never deletes TagValue / AlarmSummary / Events / Logs in-place.
        Checksum of the archive is verified before considering the backup successful.
        """
        import hashlib

        if self.sqlite_db:
            file_size_mb = os.path.getsize(self.sqlite_db_name) / 1024 / 1024
            if file_size_mb > 1 * 1024:
                timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
                name = self.sqlite_db_name.split(".db")[0]
                name = name.split(os.path.sep)[-1]
                backup_dir = os.path.join(".", "db", "backups")
                os.makedirs(backup_dir, exist_ok=True)
                backup_file = os.path.join(backup_dir, f"{name}_{timestamp}.db")
                logger = logging.getLogger("pyautomation")
                escaped = backup_file.replace("'", "''")
                conn = sqlite3.connect(self.sqlite_db_name)
                try:
                    conn.execute(f"VACUUM INTO '{escaped}'")
                    conn.commit()
                finally:
                    conn.close()
                digest = hashlib.sha256()
                with open(backup_file, "rb") as handle:
                    for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                        digest.update(chunk)
                checksum_path = f"{backup_file}.sha256"
                with open(checksum_path, "w", encoding="utf-8") as handle:
                    handle.write(digest.hexdigest())
                if os.path.getsize(backup_file) <= 0:
                    raise RuntimeError(f"SQLite VACUUM INTO produced empty archive: {backup_file}")
                logger.info(f"Backup verificado: {backup_file} sha256={digest.hexdigest()}")
        else:
            db = self.logger.logger.get_db()
            if db:
                if isinstance(db, SqliteDatabase):
                    self.sqlite_db = db
                    self.sqlite_db_name = db.database


    def check_opcua_connection(self):
        r"""
        Checks the status of OPC UA clients and attempts reconnection if necessary.

        With zero clients this is a no-op for the logger period: the edge is
        unconfigured, not degraded. Reload from catalog uses a long backoff so
        a later HMI/API create still appears without a 10 s PG poll.
        """
        from automation import PyAutomation
        app = PyAutomation()
        if app.opcua_client_manager._clients:
            self._opcua_empty_until = 0.0
            self._opcua_empty_step = 0
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
                    if not _scope_owns_node(getattr(opcua_client, "owner_node", None)):
                        logging.getLogger("pyautomation").error(
                            "Skipping foreign OPC UA reconnect client=%s owner_node=%s",
                            client_name,
                            getattr(opcua_client, "owner_node", None),
                        )
                        continue
                    try:
                        opcua_client.reconnect()
                    except Exception as e:
                        # Si hay un error durante la reconexión, registrar pero continuar con otros clientes
                        logging.error(f"Error reconnecting OPC UA client '{client_name}': {e}")
            return
        now = time.monotonic()
        if now < self._opcua_empty_until:
            return
        if not app.is_db_connected():
            return
        app.load_opcua_clients_from_db()
        if app.opcua_client_manager._clients:
            self._opcua_empty_until = 0.0
            self._opcua_empty_step = 0
            return
        delay = _EMPTY_OPC_RETRY_S[min(self._opcua_empty_step, len(_EMPTY_OPC_RETRY_S) - 1)]
        self._opcua_empty_step += 1
        self._opcua_empty_until = now + delay

    def get_tags_from_queue(self, _queue):
        r"""
        Retrieves tag data from the queue and filters it based on configuration.

        **Parameters:**

        * **_queue** (Queue): The queue containing tag updates.

        **Returns:**

        * **list**: A list of tag data dictionaries ready for insertion.
        """
        tags = list()
        while not _queue.empty():

            item = _queue.get(block=False)
            tag_name = item["tag"]
            tag = self.cvt.get_tag_by_name(name=tag_name)
            if tag and _scope_owns_tag(tag):
                value = item['value']
                timestamp = item["timestamp"]
                tags.append({
                    "tag": tag_name,
                    "value": value,
                    "timestamp": timestamp,
                    "area": getattr(tag, "area", None),
                    "owner_node": getattr(tag, "owner_node", None),
                })

        return tags

    def reconnect_to_db(self):
        r"""
        Attempts to reconnect to the database if the connection is lost.
        """
        from automation import PyAutomation
        from ..utils.db_audit import database_connection_auditor
        from ..utils.connection_alarms import set_db_disconnected

        app = PyAutomation()
        
        if self.db_reconnection:
            logging.critical("Trying reconnect to DB...")
            database_connection_auditor.notify_link_lost(source="watchdog")
            # Arm alarm only when we believed the link was previously up.
            set_db_disconnected(True)

        self.db_reconnection = False
        db_connected = app.reconnect_to_db(source="watchdog")
                
        if db_connected:
            
            logging.critical("Reconnection successfully")
            self.db_reconnection = True
            set_db_disconnected(False)
            try:
                from ..catalog.replicator import get_catalog_replicator

                worker = get_catalog_replicator()
                if worker is not None:
                    worker._sync_full()
            except Exception:
                logging.getLogger("pyautomation").debug(
                    "catalog sync after reconnect skipped",
                    exc_info=True,
                )
            logging.getLogger("pyautomation").info(
                "Historian link restored: catalog hydrate + SAF drain in progress. "
                "Any prior 'socket replaced' INFO lines during this window are expected and harmless."
            )
        else:
            set_db_disconnected(True)

    def run(self):
        r"""
        Replication worker loop (Phoenix Directive).

        The local SQLite journal is the source of truth. This loop:
        1. Replicates PENDING journal records with ACK-after-commit.
        2. Reconnects the remote historian if needed (fail-fast TCP timeout).
        3. Archives oversized local SQLite historians without deleting live rows.
        4. Maintains OPC UA client sessions.

        Historian TCP I/O must not run on the gevent hub: a ``No route to host``
        connect would otherwise freeze Socket.IO ``on.tag`` for the OS timeout.
        """
        self.db_reconnection = True
        log = logging.getLogger("pyautomation")

        while True:
            self._wake.clear()
            cycle_started = time.monotonic()
            watchdog_started = time.monotonic()
            from automation import PyAutomation
            from ..utils.connection_alarms import set_db_disconnected

            app = PyAutomation()
            reachable = self.logger.logger.check_connectivity()
            if reachable:
                if not app.is_db_connected():
                    self.reconnect_to_db()
                else:
                    self.db_reconnection = True
                    # Probe OK and bound handle live: always clear sticky disconnect
                    # alarm (stale sockets / cooldown must not leave ALM.DB.Connection Active).
                    set_db_disconnected(False)
            else:
                set_db_disconnected(True)
                self.db_reconnection = False
                app._db_live = False
                from ..utils.db_connections import close_current_greenlet_connection

                close_current_greenlet_connection(self.logger.logger.get_db())
            watchdog_s = time.monotonic() - watchdog_started
            if watchdog_s >= 8.0:
                log.warning(
                    "Historian watchdog blocked %.1fs (probe/reconnect); "
                    "HMI on.tag is independent of this wait",
                    watchdog_s,
                )

            if app.is_db_connected():
                try:
                    from ..persistence import get_persistence_gateway

                    get_persistence_gateway().replicate_once()
                    self.last_cycle_utc = datetime.datetime.now(datetime.timezone.utc).isoformat()
                except Exception as exc:
                    text = str(exc).lower()
                    if "tag not in remote" in text or (
                        "tag" in text and "not found" in text
                    ):
                        log.warning(
                            "Tag not found in remote; forcing full catalog sync"
                        )
                        try:
                            from ..catalog.replicator import get_catalog_replicator

                            worker = get_catalog_replicator()
                            if worker is not None:
                                worker.request_full_sync(
                                    reason="tag not in remote Tags"
                                )
                        except Exception:
                            log.debug(
                                "catalog full-sync request skipped", exc_info=True
                            )
                    else:
                        log.error(
                            "SAF replication cycle failed; journal preserved",
                            exc_info=True,
                        )
                self.sqlite_db_backup()

            self.check_opcua_connection()

            elapsed = time.monotonic() - cycle_started
            remaining = self._period - elapsed
            if remaining > 0:
                self._wake.wait(timeout=remaining)
            if self.stop_event.is_set():
                from ..utils.db_connections import close_current_greenlet_connection

                close_current_greenlet_connection(self.logger.logger.get_db())
                logging.critical("Alarm worker shutdown successfully!")
                break
