# -*- coding: utf-8 -*-
"""automation/logger/opcua_server.py

This module implements the OPC UA Server Logger, responsible for persisting
OPC UA Server node configurations and access rights.
"""
from ..dbmodels import OPCUAServer
from .core import BaseEngine, BaseLogger
from ..utils.decorators import db_rollback


class OPCUAServerLogger(BaseLogger):
    r"""
    Logger class specialized for OPC UA Server persistence.
    """

    def __init__(self):

        super(OPCUAServerLogger, self).__init__()

    @db_rollback
    def create(
            self,
            name:str,
            namespace:str,
            access_level=1
            ):
        r"""
        Creates a new OPC UA Node configuration in the database.

        **Parameters:**

        * **name** (str): Node name.
        * **namespace** (str): Node ID/Namespace.
        * **access_level**: Bitmask or label.
        """
        if not self.check_connectivity():
            try:
                from ..catalog.mutations import persist_opcua_server_local

                persist_opcua_server_local(
                    name=name, namespace=namespace, access_level=access_level
                )
            except Exception:
                import logging

                logging.getLogger("pyautomation").debug(
                    "local catalog opcuaserver create skipped", exc_info=True
                )
            return None
       
        OPCUAServer.create(
            name=name,
            namespace=namespace,
            access_level=access_level
        )
        try:
            from ..catalog.bootstrap import mirror_historian_row
            from ..catalog.mutations import persist_opcua_server_local

            row = OPCUAServer.read_by_namespace(namespace=namespace)
            if row is not None:
                mirror_historian_row(row)
            else:
                persist_opcua_server_local(
                    name=name, namespace=namespace, access_level=access_level
                )
        except Exception:
            import logging

            logging.getLogger("pyautomation").debug(
                "catalog opcuaserver create mirror skipped", exc_info=True
            )

    @db_rollback
    def put(
        self,
        namespace:str,
        access_level=1
        ):
        r"""
        Updates the access bitmask for a specific OPC UA Node.

        **Parameters:**

        * **namespace** (str): Node ID/Namespace.
        * **access_level**: New bitmask or label.

        **Returns:**

        * **OPCUAServer**: The updated model instance.
        """
        if not self.check_connectivity():
            try:
                from ..catalog.mutations import update_opcua_server_access_local

                update_opcua_server_access_local(
                    namespace=namespace, access_level=access_level
                )
            except Exception:
                import logging

                logging.getLogger("pyautomation").debug(
                    "local catalog opcuaserver put skipped", exc_info=True
                )
            return None    
        
        if access_level is not None:
            
            OPCUAServer.update_access_level(namespace=namespace, access_level=access_level)

            obj = OPCUAServer.read_by_namespace(namespace=namespace)
            try:
                from ..catalog.bootstrap import mirror_historian_row

                if obj is not None:
                    mirror_historian_row(obj)
            except Exception:
                import logging

                logging.getLogger("pyautomation").debug(
                    "catalog opcuaserver put mirror skipped", exc_info=True
                )

            return obj
    
    @db_rollback
    def read_all(self):
        r"""
        Retrieves all OPC UA Server nodes.
        """
        if not self.check_connectivity():
            try:
                from ..catalog.local_provider import LocalCatalogProvider
                from ..catalog.mutations import _LocalOpcuaServerView

                rows = LocalCatalogProvider().read_all("opcuaserver")
                return [_LocalOpcuaServerView(row) for row in rows]
            except Exception:
                import logging

                logging.getLogger("pyautomation").debug(
                    "local catalog opcuaserver read_all skipped", exc_info=True
                )
                return []

        return OPCUAServer.read_all()
    
    @db_rollback
    def read_by_namespace(self, namespace:str):
        r"""
        Retrieves an OPC UA Server node by its namespace.
        """
        if not self.check_connectivity():
            try:
                from ..catalog.mutations import get_opcua_server_local

                return get_opcua_server_local(namespace=namespace)
            except Exception:
                import logging

                logging.getLogger("pyautomation").debug(
                    "local catalog opcuaserver read_by_namespace skipped", exc_info=True
                )
                return None

        return OPCUAServer.read_by_namespace(namespace=namespace)

    @db_rollback
    def read_by_namespaces(self, namespaces: list):
        """Batch access lookup. One query when the caller passes <= 5000 ids."""
        if not namespaces:
            return []
        if not self.check_connectivity():
            return []
        return OPCUAServer.read_by_namespaces(namespaces)

class OPCUAServerLoggerEngine(BaseEngine):
    r"""
    Thread-safe Engine for the OPCUAServerLogger.
    """

    def __init__(self):

        super(OPCUAServerLoggerEngine, self).__init__()
        self.logger = OPCUAServerLogger()

    def create(
        self,
        name:str,
        namespace:str,
        access_level=1
        ):
        r"""
        Thread-safe node creation.
        """
        _query = dict()
        _query["action"] = "create"
        _query["parameters"] = dict()
        _query["parameters"]["name"] = name
        _query["parameters"]["namespace"] = namespace
        _query["parameters"]["access_level"] = access_level
        
        return self.query(_query)
    
    def put(
        self,
        namespace:str,
        access_level=1
        ):
        r"""
        Thread-safe node update.
        """
        _query = dict()
        _query["action"] = "put"
        _query["parameters"] = dict()
        _query["parameters"]["namespace"] = namespace
        _query["parameters"]["access_level"] = access_level

        return self.query(_query)
    
    def read_by_namespace(
        self,
        namespace:str
        ):
        r"""
        Thread-safe read by namespace.
        """
        _query = dict()
        _query["action"] = "read_by_namespace"
        _query["parameters"] = dict()
        _query["parameters"]["namespace"] = namespace

        return self.query(_query)

    def read_by_namespaces(self, namespaces: list):
        _query = dict()
        _query["action"] = "read_by_namespaces"
        _query["parameters"] = dict()
        _query["parameters"]["namespaces"] = namespaces
        return self.query(_query)

    def read_all(self):
        r"""
        Thread-safe read all.
        """
        _query = dict()
        _query["action"] = "read_all"
        _query["parameters"] = dict()
        return self.query(_query)
