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
        r"""Documentation here

        # Parameters

        - 

        # Returns

        - 
        """
        self._db = db

    def get_db(self):
        r"""Documentation here

        # Parameters

        - 

        # Returns

        - 
        """
        return self._db

    def set_tag(
        self, 
        id:str,
        name:str, 
        unit:str, 
        data_type:str, 
        description:str, 
        display_name:str="",
        opcua_address:str=None, 
        node_namespace:str=None):
        r"""Documentation here

        # Parameters

        - 

        # Returns

        - 
        """

        tag = Tags.create(
            id=id,
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
        r"""Documentation here

        # Parameters

        - 

        # Returns

        - 
        """
        
        for tag in tags:

            self.set_tag(tag)

    def update_tag(self, id:str, **fields):
        r"""Documentation here

        # Parameters

        - 

        # Returns

        - 
        """
        Tags.put(id=id, **fields)
    
    def delete_tag(self, id:str):
        r"""Documentation here

        # Parameters

        - 

        # Returns

        - 
        """
        Tags.delete(id=id)
    
    def create_tables(self, tables):
        r"""Documentation here

        # Parameters

        - 

        # Returns

        - 
        """
        if not self._db:
            
            return
        self._db.create_tables(tables, safe=True)

    def drop_tables(self, tables):
        r"""Documentation here

        # Parameters

        - 

        # Returns

        - 
        """
        if not self._db:
            
            return

        self._db.drop_tables(tables, safe=True)
