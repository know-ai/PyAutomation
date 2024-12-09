# -*- coding: utf-8 -*-
"""pyhades/logger/datalogger.py

This module implements a database logger for the CVT instance, 
will create a time-serie for each tag in a short memory data base.
"""
import pytz, logging
from collections import defaultdict
from datetime import datetime
from ..tags.tag import Tag
from ..dbmodels import Tags, TagValue, Units, Segment, Variables
from ..modules.users.users import User
from ..tags.cvt import CVTEngine
from .core import BaseLogger, BaseEngine
from ..variables import *
from ..utils.decorators import db_rollback


DATETIME_FORMAT = "%Y-%m-%d %H:%M:%S.%f"

class DataLogger(BaseLogger):
    """
    Data Logger class.

    This class serves as an API for managing tag settings and accessing logged tags.

    **Usage Example**:

    .. code-block:: python

        >>> from pyhades import DataLogger
        >>> _logger = DataLogger()

    """

    def __init__(self):

        super(DataLogger, self).__init__()
        self.tag_engine = CVTEngine()

    @db_rollback
    def set_tag(
        self, 
        id:str,
        name:str, 
        unit:str, 
        data_type:str, 
        description:str="", 
        display_name:str="",
        display_unit:str=None,
        opcua_address:str=None, 
        node_namespace:str=None,
        scan_time:int=None,
        dead_band:float=None,
        manufacturer:str="",
        segment:str=""
        ):
        r"""
        Documentation here
        """
        if not self.check_connectivity():

            return None
            
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
            dead_band=dead_band,
            manufacturer=manufacturer,
            segment=segment
            )
            
    @db_rollback
    def delete_tag(self, id:str):
        r"""
        Documentation here
        """
        if not self.check_connectivity():

            return None
        
        tag, _ = Tags.get_or_create(identifier=id)
        Tags.put(id=tag.id, active=False)

    @db_rollback
    def get_tag_by_name(self, name:str):
        r"""
        Documentation here
        """
        if not self.check_connectivity():

            return None
        
        return Tags.read_by_name(name=name)

    @db_rollback
    def update_tag(self, id:str, **kwargs):
        r"""
        Documentation here
        """
        if not self.check_connectivity():

            return None
        
        tag = Tags.get(identifier=id)
        return Tags.put(id=tag.id, **kwargs)

    @db_rollback
    def set_tags(self, tags):
        r"""
        Documentation here
        """
        if not self.check_connectivity():

            return None
        
        for tag in tags:

            self.set_tag(tag)

    @db_rollback
    def get_tags(self):
        r"""
        Documentation here
        """
        if not self.check_connectivity():

            return list()
            
        return Tags.read_all()
    
    @db_rollback
    def write_tag(self, tag, value, timestamp):
        r"""
        Documentation here
        """
        if not self.is_history_logged:

            return None
        
        if not self.check_connectivity():

            return None
        
        trend = Tags.read_by_name(tag)
        unit = Units.read_by_unit(unit=trend.display_unit.unit)
        TagValue.create(tag=trend, value=value, timestamp=timestamp, unit=unit)

    @db_rollback
    def write_tags(self, tags:list):
        r"""
        Documentation here
        """
        if not self.is_history_logged:

            return None
        
        if not self.check_connectivity():

            return None
            
        _tags = tags.copy()
        
        for counter, tag in enumerate(tags):
            
            _tag = Tags.read_by_name(tag['tag'])
            
            if _tag:

                unit = Units.get_or_none(id=_tag.display_unit.id)
                _tags[counter].update({
                    'tag': _tag,
                    'unit': unit
                })
        
        TagValue.insert_many(_tags).execute()

    @db_rollback
    def read_trends(self, start:str, stop:str, timezone:str, tags):
        r"""
        Documentation here
        """  
        if not self.is_history_logged:

            return None
        
        if not self.check_connectivity():

            return dict()

        _timezone = pytz.timezone(timezone)
        start = _timezone.localize(datetime.strptime(start, DATETIME_FORMAT)).astimezone(pytz.UTC).timestamp()
        stop = _timezone.localize(datetime.strptime(stop, DATETIME_FORMAT)).astimezone(pytz.UTC).timestamp()           
        query = (TagValue
                .select(Tags.name, TagValue.value, TagValue.timestamp,
                        Units.unit.alias('tag_value_unit'), Variables.name.alias('variable_name'))
                .join(Tags)
                .join(Units, on=(Tags.unit == Units.id))
                .join(Variables, on=(Units.variable_id == Variables.id))
                .where((TagValue.timestamp.between(start, stop)) & (Tags.name.in_(tags)))
                .order_by(TagValue.timestamp)
                .dicts()) 
        
        # Structure the data
        time_span = (stop - start ) / 60 # span in minutes
        result = defaultdict(lambda: {"values": []})
        if time_span > 60 * 24 * 7:  # 1 week
            # Aggregate data every 1 day
            result = self._agregate_data_every_seconds(query=query, result=result, seconds=3600 * 24, timezone=timezone)

        elif time_span > 60 * 24 * 2:  # 2 days
            # Aggregate data every 1 hora
            result = self._agregate_data_every_seconds(query=query, result=result, seconds=3600, timezone=timezone)

        elif time_span > 60 * 2:  # 2 horas
            # Aggregate data every 1 minute
            result = self._agregate_data_every_seconds(query=query, result=result, seconds=60, timezone=timezone)

        else:
            # Use original data
            for entry in query:

                from_timezone = pytz.timezone('UTC')
                timestamp = entry['timestamp']
                timestamp = from_timezone.localize(timestamp)
                result[entry['name']]["values"].append({
                    "x": timestamp.astimezone(_timezone).strftime(self.tag_engine.DATETIME_FORMAT),
                    "y": entry['value']
                })

        for tag in tags:

            result[tag]['unit'] = self.tag_engine.get_display_unit_by_tag(tag)
        
        return result
        
    def _agregate_data_every_seconds(self, query, result, seconds:int, timezone:str="UTC"):
        r"""Documentation here
        """
        # Aggregate data every 5 seconds
        target_timezone = pytz.timezone(timezone)
        buffer = defaultdict(lambda: {"sum": 0, "count": 0, "last_timestamp": None})

        for entry in query:
            bucket = entry['timestamp'].replace(second=(entry['timestamp'].second // seconds) * seconds, microsecond=0)
            buffer_key = (entry['name'], bucket)
            buffer[buffer_key]["sum"] += entry['value']
            buffer[buffer_key]["count"] += 1
            buffer[buffer_key]["last_timestamp"] = entry['timestamp']
            buffer[buffer_key]['unit'] = entry["tag_value_unit"]
            buffer[buffer_key]['variable'] = entry['variable_name']

        for (tag_name, bucket), data in buffer.items():

            avg_value = data["sum"] / data["count"]
            last_timestamp = data["last_timestamp"]
            from_timezone = pytz.timezone('UTC')
            last_timestamp = from_timezone.localize(last_timestamp)
            result[tag_name]["values"].append({
                "x": last_timestamp.astimezone(target_timezone).strftime(self.tag_engine.DATETIME_FORMAT),
                # "y": eval(f"{variable}.convert_value({avg_value}, from_unit={'unit'}, to_unit={'_tag.get_display_unit()'})")
                "y": avg_value
            })
        
        return result
        
    @db_rollback
    def read_segments(self):
        r"""
        Documentation here
        """
        if not self.check_connectivity():

            return list()

        return Segment.read_all()


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
        tag:Tag
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
        _query["parameters"]["id"] = tag.id
        _query["parameters"]["name"] = tag.name
        _query["parameters"]["unit"] = tag.unit
        _query["parameters"]["data_type"] = tag.data_type
        _query["parameters"]["description"] = tag.description
        _query["parameters"]["display_name"] = tag.display_name
        _query["parameters"]["display_unit"] = tag.display_unit
        _query["parameters"]["opcua_address"] = tag.opcua_address
        _query["parameters"]["node_namespace"] = tag.node_namespace
        _query["parameters"]["scan_time"] = tag.scan_time
        _query["parameters"]["dead_band"] = tag.dead_band
        _query["parameters"]["manufacturer"] = tag.manufacturer
        _query["parameters"]["segment"] = tag.segment
        
        return self.query(_query)

    def get_tags(self):
        r"""

        """
        _query = dict()
        _query["action"] = "get_tags"
        _query["parameters"] = dict()
        
        return self.query(_query)
    
    def get_tag_by_name(self, name:str):
        r"""

        """
        _query = dict()
        _query["action"] = "get_tag_by_name"
        _query["parameters"] = dict()
        _query["parameters"]["name"] = name
        
        return self.query(_query)
    
    def update_tag(
            self, 
            id:str, 
            user:User|None=None,
            **kwargs
            ):
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
        for key, value in kwargs.items():

            _query["parameters"][key] = value
    
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
    
    def read_trends(self, start:str, stop:str, timezone:str, *tags):
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
        _query["parameters"]["timezone"] = timezone
        _query["parameters"]["tags"] = tags
        return self.query(_query)

    def read_segments(self):
        r"""
        Documentation here
        """
        _query = dict()
        _query["action"] = "read_segments"
        _query["parameters"] = dict()
        return self.query(_query)
    