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
            access_type:str="Read"
            ):
        r"""
        Creates a new OPC UA Node configuration in the database.

        **Parameters:**

        * **name** (str): Node name.
        * **namespace** (str): Node ID/Namespace.
        * **access_type** (str): Access rights ("Read", "Write", "ReadWrite").
        """
        if not self.check_connectivity():

            return None
       
        OPCUAServer.create(
            name=name,
            namespace=namespace,
            access_type=access_type
        )

    @db_rollback
    def put(
        self,
        namespace:str,
        access_type:str
        ):
        r"""
        Updates the access type for a specific OPC UA Node.

        **Parameters:**

        * **namespace** (str): Node ID/Namespace.
        * **access_type** (str): New access type.

        **Returns:**

        * **OPCUAServer**: The updated model instance.
        """
        if not self.check_connectivity():
            
            return None    
        
        if access_type:
            
            OPCUAServer.update_access_type(namespace=namespace, access_type=access_type)

            obj = OPCUAServer.read_by_namespace(namespace=namespace)

            return obj
    
    @db_rollback
    def read_all(self):
        r"""
        Retrieves all OPC UA Server nodes.
        """
        if not self.check_connectivity():

            return list()
        
        return OPCUAServer.read_all()
    
    @db_rollback
    def read_by_namespace(self, namespace:str):
        r"""
        Retrieves an OPC UA Server node by its namespace.
        """
        if not self.check_connectivity():

            return list()
        
        return OPCUAServer.read_by_namespace(namespace=namespace)
     

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
        access_type:str="Read"
        ):
        r"""
        Thread-safe node creation.
        """
        _query = dict()
        _query["action"] = "create"
        _query["parameters"] = dict()
        _query["parameters"]["name"] = name
        _query["parameters"]["namespace"] = namespace
        _query["parameters"]["access_type"] = access_type
        
        return self.query(_query)
    
    def put(
        self,
        namespace:str,
        access_type:str
        ):
        r"""
        Thread-safe node update.
        """
        _query = dict()
        _query["action"] = "put"
        _query["parameters"] = dict()
        _query["parameters"]["namespace"] = namespace
        _query["parameters"]["access_type"] = access_type

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

    def read_all(self):
        r"""
        Thread-safe read all.
        """
        _query = dict()
        _query["action"] = "read_all"
        _query["parameters"] = dict()
        return self.query(_query)
