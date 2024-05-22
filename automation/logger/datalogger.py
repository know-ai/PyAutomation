# -*- coding: utf-8 -*-
"""pyautomation/logger/datalogger.py

This module implements a database logger for the CVT instance, 
will create a time-serie for each tag in a short memory data base.
"""
from ..dbmodels import (
    Tags
    )


class DataLogger:

    """Data Logger class.

    This class is intended to be an API for tags 
    settings and tags logged access.

    # Example
    
    ```python
    >>> from pyautomation import DataLogger
    >>> _logger = DataLogger()
    ```
    """

    def __init__(self):

        self._db = None

    def set_db(self, db):

        self._db = db

    def get_db(self):
        
        return self._db

    def set_tag(
        self, 
        name:str, 
        unit:str, 
        data_type:str, 
        description:str, 
        display_name:str="",
        opcua_address:str=None, 
        node_namespace:str=None):

        tag = Tags.create(
            name=name, 
            unit=unit,
            data_type=data_type,
            description=description,
            display_name=display_name,
            opcua_address=opcua_address,
            node_namespace=node_namespace
            )
        
        return tag.serialize()

    def set_tags(self, tags):
        
        for tag in tags:

            self.set_tag(tag)

    def update_tag(self, id:str, **fields):
        r"""
        Documentation here
        """
        tag = Tags.put(id=id, **fields)

        return tag.serialize()
    
    def delete_tag(self, id:str):
        r"""
        Documentation here
        """
        Tags.delete(id=id)
    
    def create_tables(self, tables):
        if not self._db:
            
            return
        self._db.create_tables(tables, safe=True)

    def drop_tables(self, tables):

        if not self._db:
            
            return

        self._db.drop_tables(tables, safe=True)

    # def write_tag(self, tag, value):
    #     try:
    #         trend = Tags.read_by_name(tag)
    #         tag_value = TagValue.create(tag=trend, value=value)
    #         tag_value.save()
    #     except Exception as e:
    #         logging.warning(f"Rollback done in database due to conflicts writing tag")
    #         conn = self._db.connection()
    #         conn.rollback()

    # def write_tags(self, tags:list):

    #     try:
    #         TagValue.insert_many(tags).execute()
    #     except Exception as e:
    #         logging.warning(f"Rollback done in database due to conflicts writing tags")
    #         conn = self._db.connection()
    #         conn.rollback()

    # def read_tag(self, tag):
    #     try:
    #         query = Tags.select().order_by(Tags.start)
    #         trend = query.where(Tags.name == tag).get()
            
    #         period = trend.period
    #         values = trend.values.select()
            
    #         result = dict()

    #         t0 = values[0].timestamp.strftime('%Y-%m-%d %H:%M:%S')
    #         values = [value.value for value in values]

    #         result["t0"] = t0
    #         result["dt"] = period
    #         result["values"] = values
            
    #         return result
    #     except Exception as e:
    #         logging.warning(f"Rollback done in database due to conflicts reading tag")
    #         conn = self._db.connection()
    #         conn.rollback()
