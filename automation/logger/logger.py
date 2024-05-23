# -*- coding: utf-8 -*-
"""pyhades/logger/engine.py

This module implements a singleton layer above the DataLogger class,
in a thread-safe mode.
"""

import threading, logging
from .datalogger import DataLogger
from ..singleton import Singleton
from ..dbmodels.core import proxy, SQLITE, POSTGRESQL, MYSQL
from peewee import SqliteDatabase, MySQLDatabase, PostgresqlDatabase


class DataLoggerEngine(Singleton):
    r"""
    Data logger Engine class for Tag thread-safe database logging.

    """

    def __init__(self):

        super(DataLoggerEngine, self).__init__()

        self.logger = DataLogger()
        self._request_lock = threading.Lock()
        self._response_lock = threading.Lock()
        self._response = None
        self._response_lock.acquire()

    def set_db(self, dbtype:str=SQLITE, **kwargs):
        r"""
        Sets the database, it supports SQLite and Postgres,
        in case of SQLite, the filename must be provided.

        if app mode is "Development" you must use SQLite Databse

        **Parameters:**

        * **dbfile** (str): a path to database file.
        * *drop_table** (bool): If you want to drop table.
        * **cascade** (bool): if there are some table dependency, drop it as well
        * **kwargs**: Same attributes to a postgres connection.

        **Returns:** `None`

        Usage:

        ```python
        >>> app.set_db(dbfile="app.db")
        ```
        """

        if dbtype.lower() == SQLITE:

            dbfile = "app.db"
            if 'name' in kwargs:

                dbfile = kwargs['name']
                del kwargs['name']

            self._db = SqliteDatabase(dbfile, pragmas={
                'journal_mode': 'wal',
                'journal_size_limit': 1024,
                'cache_size': -1024 * 64,  # 64MB
                'foreign_keys': 1,
                'ignore_check_constraints': 0,
                'synchronous': 0}
            )

        elif dbtype.lower() == MYSQL:

            db_name = kwargs['name']
            del kwargs['name']
            self._db = MySQLDatabase(db_name, **kwargs)

        elif dbtype.lower() == POSTGRESQL:

            db_name = kwargs['name']
            del kwargs['name']
            self._db = PostgresqlDatabase(db_name, **kwargs)

        proxy.initialize(self._db)
        self.logger.set_db(self._db)

    def get_db(self):
        r"""
        Returns a DB object
        """
        return self.logger.get_db()

    def create_tables(self, tables):
        r"""
        Create default PyHades database tables

        ['TagTrend', 'TagValue']

        **Parameters**

        * **tables** (list) list of database model

        **Returns** `None`
        """
        self.logger.create_tables(tables)

    def drop_tables(self, tables:list):
        r"""
        Drop tables if exist in database

        **Parameters**

        * **tables** (list): List of database model you want yo drop
        """
        self.logger.drop_tables(tables)

    def set_tag(
        self,
        id:str, 
        name:str, 
        unit:str, 
        data_type:str, 
        description:str,
        display_name:str="", 
        opcua_address:str=None, 
        node_namespace:str=None
        ):
        r"""
        Define tag names you want log in database, these tags must be defined in CVTEngine

        **Parameters**

        * **tag** (str): Tag name defined in CVTEngine
        * **period** (float): Sampling time to log tag on database

        **Returns** `None`
        """
        _query = dict()
        _query["action"] = "set_tag"

        _query["parameters"] = dict()
        _query["parameters"]["id"] = id
        _query["parameters"]["name"] = name
        _query["parameters"]["unit"] = unit
        _query["parameters"]["data_type"] = data_type
        _query["parameters"]["description"] = description
        _query["parameters"]["display_name"] = display_name
        _query["parameters"]["opcua_address"] = opcua_address
        _query["parameters"]["node_namespace"] = node_namespace
        
        return self.__query(_query)
    
    def update_tag(self, id:str, **fields):
        r"""
        Documentation here
        """

        _query = dict()
        _query["action"] = "update_tag"

        _query["parameters"] = dict()
        _query["parameters"]["id"] = id
        _query["parameters"].update(fields)
        
        return self.__query(_query)
    
    def delete_tag(self, id:str):
        r"""
        Documentation here
        """

        _query = dict()
        _query["action"] = "delete_tag"

        _query["parameters"] = dict()
        _query["parameters"]["id"] = id
        
        return self.__query(_query)

    def write_tag(self, tag, value):
        r"""
        Writes value to tag into database on a thread-safe mechanism

        **Parameters**

        * **tag** (str): Tag name in database
        * **value** (float): Value to write in tag
        """
        _query = dict()
        _query["action"] = "write_tag"

        _query["parameters"] = dict()
        _query["parameters"]["tag"] = tag
        _query["parameters"]["value"] = value

        return self.__query(_query)

    def write_tags(self, tags:list):
        r"""
        Writes value to tag into database on a thread-safe mechanism

        **Parameters**

        * **tag** (str): Tag name in database
        * **value** (float): Value to write in tag
        """
        _query = dict()
        _query["action"] = "write_tags"

        _query["parameters"] = dict()
        _query["parameters"]["tags"] = tags

        return self.__query(_query)

    def read_tag(self, tag):
        r"""
        Read tag value from database on a thread-safe mechanism

        **Parameters**

        * **tag** (str): Tag name in database

        **Returns**

        * **value** (float): Tag value requested
        """
        _query = dict()
        _query["action"] = "read_tag"

        _query["parameters"] = dict()
        _query["parameters"]["tag"] = tag

        return self.__query(_query)

    def __query(self, query:dict)->dict:

        self.request(query)
        result = self.response()
        if result["result"]:
            return result["response"]

    def request(self, query:dict):
        r"""
        Documentation here
        """
        self._request_lock.acquire()
        action = query["action"]
        error_msg = f"Error in CVTEngine with action: {action}"

        try:

            if hasattr(self.logger, action):

                method = getattr(self.logger, action)
                
                if 'parameters' in query:
                    
                    resp = method(**query["parameters"])
                
                else:

                    resp = method()

            self.__true_response(resp)

        except Exception as e:

            self.__log_error(e, error_msg)

        self._response_lock.release()

    def __log_error(self, e:Exception, msg:str):
        r"""
        Documentation here
        """
        logging.error(f"{e} Message: {msg}")
        self._response = {
            "result": False,
            "response": None
        }

    def response(self):
        r"""
        Documentation here
        """
        self._response_lock.acquire()

        result = self._response

        self._request_lock.release()

        return result
    
    def __true_response(self, resp):
        r"""
        Documentation here
        """
        self._response = {
            "result": True,
            "response": resp
        }

    def __getstate__(self):

        self._response_lock.release()
        state = self.__dict__.copy()
        del state['_request_lock']
        del state['_response_lock']
        return state

    def __setstate__(self, state):
        
        self.__dict__.update(state)
        self._request_lock = threading.Lock()
        self._response_lock = threading.Lock()

        self._response_lock.acquire()
