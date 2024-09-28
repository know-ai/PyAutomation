# -*- coding: utf-8 -*-
"""pyhades/logger/datalogger.py

This module implements a database logger for the CVT instance, 
will create a time-serie for each tag in a short memory data base.
"""
import logging, sys, os
from datetime import datetime
from ..dbmodels import Tags, TagValue
from .core import BaseLogger, BaseEngine


class DataLogger(BaseLogger):

    """Data Logger class.

    This class is intended to be an API for tags 
    settings and tags logged access.

    # Example
    
    ```python
    >>> from pyhades import DataLogger
    >>> _logger = DataLogger()
    ```
    """
    def __init__(self):

        super(DataLogger, self).__init__()

    def set_tag(
        self, 
        id:str,
        name:str, 
        unit:str, 
        data_type:str, 
        description:str, 
        display_name:str="",
        display_unit:str=None,
        opcua_address:str=None, 
        node_namespace:str=None,
        scan_time:int=None,
        dead_band:float=None
        ):
        r"""
        Documentation here
        """
        Tags.create(
            id=id,
            name=name, 
            unit=unit,
            data_type=data_type,
            description=description,
            display_name=display_name,
            display_unit=display_unit,
            opcua_address=opcua_address,
            node_namespace=node_namespace,
            scan_time=scan_time,
            dead_band=dead_band
            )
        
    def delete_tag(self, id:str):
        r"""
        Documentation here
        """
        tag = Tags.get(identifier=id)
        Tags.delete(id=tag.id)

    def update_tag(self, id:str, **kwargs):
        r"""
        Documentation here
        """
        tag = Tags.get(identifier=id)
        Tags.put(id=tag.id, **kwargs)

    def set_tags(self, tags):
        r"""
        Documentation here
        """
        for tag in tags:

            self.set_tag(tag)

    def get_tags(self):
        r"""
        Documentation here
        """
        return Tags.read_all()
    
    def write_tag(self, tag, value, timestamp):
        r"""
        Documentation here
        """
        try:
            trend = Tags.read_by_name(tag)
            TagValue.create(tag=trend, value=value, timestamp=timestamp)
        except Exception as e:
            _, _, e_traceback = sys.exc_info()
            e_filename = os.path.split(e_traceback.tb_frame.f_code.co_filename)[1]
            e_message = str(e)
            e_line_number = e_traceback.tb_lineno
            logging.warning(f"Rollback done in database due to conflicts writing tag: {e_line_number} - {e_filename} - {e_message}")
            conn = self._db.connection()
            conn.rollback()

    def write_tags(self, tags:list):
        r"""
        Documentation here
        """
        _tags = tags.copy()
        try:
            for counter, tag in enumerate(tags):

                _tags[counter].update({
                    'tag': Tags.read_by_name(tag['tag'])
                })

            TagValue.insert_many(tags).execute()

        except Exception as e:
            _, _, e_traceback = sys.exc_info()
            e_filename = os.path.split(e_traceback.tb_frame.f_code.co_filename)[1]
            e_message = str(e)
            e_line_number = e_traceback.tb_lineno
            logging.warning(f"Rollback done in database due to conflicts writing tags: {e_line_number} - {e_filename} - {e_message}")
            conn = self._db.connection()
            conn.rollback()

    def read_tag(self, tag):
        r"""
        Documentation here
        """
        try:
            query = Tags.select().order_by(Tags.start)
            trend = query.where(Tags.name == tag).get()
            
            period = trend.period
            values = trend.values.select()
            
            result = dict()

            t0 = values[0].timestamp.strftime('%Y-%m-%d %H:%M:%S')
            values = [value.value for value in values]

            result["t0"] = t0
            result["dt"] = period
            result["values"] = values
            
            return result
        except Exception as e:
            _, _, e_traceback = sys.exc_info()
            e_filename = os.path.split(e_traceback.tb_frame.f_code.co_filename)[1]
            e_message = str(e)
            e_line_number = e_traceback.tb_lineno
            logging.warning(f"Rollback done in database due to conflicts reading tag: {e_line_number} - {e_filename} - {e_message}")
            conn = self._db.connection()
            conn.rollback()

    def read_trends(self, start:str, stop:str, tags):
        r"""
        Documentation here
        """    
        start = datetime.strptime(start, self.tag_engine.DATETIME_FORMAT)
        stop = datetime.strptime(stop, self.tag_engine.DATETIME_FORMAT)
        result = {tag: {
            'values': list(),
            'unit': self.tag_engine.get_display_unit_by_tag(tag)
        } for tag in tags}
        

        for tag in tags:

            trend = Tags.select().where(Tags.name==tag).get()
            
            values = trend.values.select().where((TagValue.timestamp > start) & (TagValue.timestamp < stop)).order_by(TagValue.timestamp.asc())

            for value in values:
                
                result[tag]['values'].append({"x": value.timestamp.strftime(self.tag_engine.DATETIME_FORMAT), "y": value.value})

        return result

class DataLoggerEngine(BaseEngine):
    r"""
    Data logger Engine class for Tag thread-safe database logging.

    """
    def __init__(self):

        super(DataLoggerEngine, self).__init__()
        self.logger = DataLogger()

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
        display_unit:str=None,
        opcua_address:str=None, 
        node_namespace:str=None,
        scan_time:int=None,
        dead_band:float=None
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
        _query["parameters"]["display_unit"] = display_unit
        _query["parameters"]["opcua_address"] = opcua_address
        _query["parameters"]["node_namespace"] = node_namespace
        _query["parameters"]["scan_time"] = scan_time
        _query["parameters"]["dead_band"] = dead_band
        
        return self.query(_query)

    def get_tags(self):
        r"""

        """
        _query = dict()
        _query["action"] = "get_tags"
        _query["parameters"] = dict()
        
        return self.query(_query)
    
    def update_tag(self, id:str, **fields):
        r"""Documentation here

        # Parameters

        - 

        # Returns

        - 
        """

        _query = dict()
        _query["action"] = "update_tag"
        _query["parameters"] = dict()
        _query["parameters"]["id"] = id
        _query["parameters"].update(fields)
        
        return self.query(_query)
    
    def delete_tag(self, id:str):
        r"""Documentation here

        # Parameters

        - 

        # Returns

        - 
        """
        _query = dict()
        _query["action"] = "delete_tag"
        _query["parameters"] = dict()
        _query["parameters"]["id"] = id
        
        return self.query(_query)

    def write_tag(self, tag:str, value:float, timestamp:datetime):
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
        _query["parameters"]["timestamp"] = timestamp

        return self.query(_query)

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

        return self.query(_query)

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

        return self.query(_query)
    
    def read_trends(self, start:str, stop:str, *tags):
        r"""
        Read tag value from database on a thread-safe mechanism

        **Parameters**

        * **tag** (str): Tag name in database

        **Returns**

        * **value** (float): Tag value requested
        """
        _query = dict()
        _query["action"] = "read_trends"
        _query["parameters"] = dict()
        _query["parameters"]["start"] = start
        _query["parameters"]["stop"] = stop
        _query["parameters"]["tags"] = tags
        return self.query(_query)

