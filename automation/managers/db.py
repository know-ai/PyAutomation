# -*- coding: utf-8 -*-
"""pyautomation/managers/db.py

This module implements Logger Manager.
"""
from ..singleton import Singleton
from ..tags import CVTEngine
from ..logger import DataLoggerEngine
import queue, secrets
from ..dbmodels import (
    Tags
    )


class DBManager(Singleton):
    r"""
    Database Manager class for database logging settings.
    """

    def __init__(self):

        self.tag_engine = CVTEngine()
        self.logger = DataLoggerEngine()
        self.queue = queue.Queue()
        self.workers = list()
        self._tables = [
            Tags
        ]

    def get_queue(self)->queue.Queue:
        r"""
        Documentation here
        """
        return self.queue

    def put_queue(self, method:str, **kwargs):
        r"""
        Documentation here
        """
        self.queue.put((method, kwargs))

    def set_db(self, db):
        r"""
        Initialize a new DB Object SQLite - Postgres - MySQL

        **Parameters**

        * **db** (db object): Sqlite - Postgres or MySql db object

        **Returns** `None`
        """
        self.logger.set_db(db)
        self.create_tables()

    def get_db(self):
        r"""
        Returns a DB object
        """
        return self.logger.get_db()

    def set_dropped(self, drop_tables:bool):
        r"""
        Allows to you set a flag variable to drop database tables when run app.

        **Parameters**

        * **drop_tables** (bool) If True, drop all tables define in the app an initialized it in blank.

        **Returns**

        * **None**
        """
        self._drop_tables = drop_tables

    def get_dropped(self)->bool:
        r"""
        Gets flag variables to drop tables when initialize the app

        **Return**

        * **drop_tables** (bool) Flag variables to drop table
        """
        return self._drop_tables

    def create_tables(self):
        r"""
        Creates default tables and tables registered with method *register_table*
        """
        self.logger.create_tables(self._tables)

    def drop_tables(self):
        r"""
        Drop all tables defined
        """
        tables = self._tables
        self.logger.drop_tables(tables)

    def get_tags(self)->dict:
        r"""
        Gets all tag defined in tag's repository
        """
        return self.tag_engine.get_tags()

    def set_tag(
        self, 
        name:str, 
        unit:str, 
        data_type:str, 
        description:str,
        display_name:str="",
        opcua_address:str=None, 
        node_namespace:str=None):
        r"""
        Sets tag to Database

        **Parameters**

        * **tag** (str):
        * **unit** (str):
        * **data_type** (str):
        * **description** (str):
        * **min_value** (float)[Optional]:
        * **max_value** (float)[Optional]:
        * **tcp_source_address** (str)[Optional]:
        * **node_namespace** (str)[Optional]:
        """
        payload = {
            "id": secrets.token_hex(4),
            "name": name,
            "unit": unit,
            "data_type": data_type,
            "description": description,
            "display_name": display_name,
            "opcua_address": opcua_address,
            "node_namespace": node_namespace
        }
        # CREATE TAG ON CVT (HOLD IN MEMORY)
        self.tag_engine.set_tag(**payload)
        # CREATE TAG ON DATABASE (PERSISTENT DATA) 
        # NOT BLOCKING EXECUTION AND THREAD SAFE MECHANISM
        self.put_queue("set_tag", **payload)

    def update_tag(self, id:str, **fields):
        r"""
        Documentation here
        """
        if self.tag_engine.get_tag(id=id):
            
            # UPDATE TAG ON CVT (HOLDING MEMORY)
            self.tag_engine.update_tag(id=id, **fields)
            # UPDATE TAG ON DATABASE (PERSISTENT DATA)
            # NOT BLOCKING EXECUTION AND THREAD SAFE MECHANISM
            fields.update({
                "id": id
            })
            self.put_queue("update_tag", **fields)

    def delete_tag(self, id:str):
        r"""
        Documentation here
        """
        if self.tag_engine.get_tag(id=id):
            # DELETE TAG ON CVT (HOLDING MEMORY)
            self.tag_engine.delete_tag(id=id)
            # DELETE TAG ON DATABASE (PERSISTENT DATA)
            # NOT BLOCKING EXECUTION AND THREAD SAFE MECHANISM
            fields = {
                "id": id
            }
            self.put_queue("delete_tag", **fields) 

    def init_database(self, **kwargs):
        r"""
        Initializes all databases.
        """
        
        self.logger.set_db(**kwargs)
        self.create_tables()
        tags = Tags.read_all()

        for tag in tags:

            self.tag_engine.set_tag(**tag)

    def summary(self)->dict:
        r"""
        Get database manager summary

        **Returns**

        * **summary** (dict): Database summary
        """
        result = dict()

        result["tags"] = self.get_tags()

        return result
    