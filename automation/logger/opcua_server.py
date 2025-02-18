# -*- coding: utf-8 -*-
"""pyhades/logger/machines.py
"""
from ..dbmodels import OPCUAServer
from .core import BaseEngine, BaseLogger
from ..utils.decorators import db_rollback


class OPCUAServerLogger(BaseLogger):

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
        Documentation here
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

        if not self.check_connectivity():
            
            return None    
        
        if access_type:
            
            OPCUAServer.update_access_type(namespace=namespace, access_type=access_type)

            obj = OPCUAServer.read_by_namespace(namespace=namespace)

            return obj
    
    @db_rollback
    def read_all(self):
        if not self.check_connectivity():

            return list()
        
        return OPCUAServer.read_all()
    
    @db_rollback
    def read_by_namespace(self, namespace:str):
        if not self.check_connectivity():

            return list()
        
        return OPCUAServer.read_by_namespace(namespace=namespace)
     

class OPCUAServerLoggerEngine(BaseEngine):
    r"""
    OPCUA Server logger Engine class for Tag thread-safe database logging.

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

        _query = dict()
        _query["action"] = "read_by_namespace"
        _query["parameters"] = dict()
        _query["parameters"]["namespace"] = namespace

        return self.query(_query)

    def read_all(self):

        _query = dict()
        _query["action"] = "read_all"
        _query["parameters"] = dict()
        return self.query(_query)

