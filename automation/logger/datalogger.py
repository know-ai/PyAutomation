# -*- coding: utf-8 -*-
"""automation/logger/datalogger.py

This module implements the Data Logger, responsible for persisting tag values (time-series data)
and managing tag configurations in the database.
"""
import pytz, logging, math
from peewee import fn
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

    This class serves as an API for managing tag settings and accessing logged historical data.
    It interacts directly with the database models.
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
        Creates a new tag definition in the database.

        **Parameters:**

        * **id** (str): Unique identifier for the tag.
        * **name** (str): Tag name.
        * **unit** (str): Measurement unit.
        * **data_type** (str): Data type (float, int, bool, etc.).
        * **description** (str, optional): Tag description.
        * **display_name** (str, optional): Friendly name for display.
        * **display_unit** (str, optional): Unit for display purposes.
        * **opcua_address** (str, optional): Source OPC UA server address.
        * **node_namespace** (str, optional): Source OPC UA node ID.
        * **scan_time** (int, optional): Scan interval in ms.
        * **dead_band** (float, optional): Deadband for logging.
        * **manufacturer** (str, optional): Associated manufacturer.
        * **segment** (str, optional): Associated segment.
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
        Deactivates a tag in the database (logical delete).

        **Parameters:**

        * **id** (str): Tag ID.
        """
        if not self.check_connectivity():

            return None
        
        tag, _ = Tags.get_or_create(identifier=id)
        Tags.put(id=tag.id, active=False)

    @db_rollback
    def get_tag_by_name(self, name:str):
        r"""
        Retrieves a tag configuration by its name.

        **Parameters:**

        * **name** (str): Tag name.

        **Returns:**

        * **Tags**: The tag model instance.
        """
        if not self.check_connectivity():

            return None
        
        return Tags.read_by_name(name=name)

    @db_rollback
    def update_tag(self, id:str, **kwargs):
        r"""
        Updates tag configuration properties.

        **Parameters:**

        * **id** (str): Tag ID.
        * **kwargs**: Fields to update (e.g., gaussian_filter=True).
        """
        if not self.check_connectivity():

            return None
        
        tag = Tags.get(identifier=id)

        if "gaussian_filter" in kwargs:
            
            if kwargs['gaussian_filter'].lower() in ('1', 'true'):

                kwargs['gaussian_filter'] = True

            else:

                kwargs['gaussian_filter'] = False
        
        return Tags.put(id=tag.id, **kwargs)

    @db_rollback
    def set_tags(self, tags):
        r"""
        Batch creates multiple tags.

        **Parameters:**

        * **tags** (list): List of tag dictionaries.
        """
        if not self.check_connectivity():

            return None
        
        for tag in tags:

            self.set_tag(tag)

    @db_rollback
    def get_tags(self):
        r"""
        Retrieves all tags configured in the database.

        **Returns:**

        * **list**: List of all Tags.
        """
        if not self.check_connectivity():

            return list()
            
        return Tags.read_all()
    
    @db_rollback
    def write_tag(self, tag, value, timestamp):
        r"""
        Writes a single value for a tag to the historical log.

        **Parameters:**

        * **tag** (str): Tag name.
        * **value** (float): Value to log.
        * **timestamp** (datetime): Timestamp of the value.
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
        Batch writes multiple tag values to the historical log.

        **Parameters:**

        * **tags** (list): List of dictionaries containing {'tag': name, 'value': val, 'timestamp': ts}.
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
        Reads historical data for charting/trending.
        
        Supports automatic downsampling based on the requested time span:
        - > 1 week: Daily averages
        - > 2 days: Hourly averages
        - > 2 hours: Minute averages
        - Otherwise: Raw data

        **Parameters:**

        * **start** (str): Start datetime string.
        * **stop** (str): End datetime string.
        * **timezone** (str): Timezone for the query.
        * **tags** (list): List of tag names to query.

        **Returns:**

        * **dict**: Dictionary of time-series data per tag.
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

    @db_rollback
    def read_table(self, start:str, stop:str, timezone:str, tags:list, page:int=1, limit:int=20):
        r"""
        Retrieves historical data in a paginated table format.

        **Parameters:**

        * **start** (str): Start datetime string.
        * **stop** (str): Stop datetime string.
        * **timezone** (str): Timezone.
        * **tags** (list): List of tag names.
        * **page** (int): Page number.
        * **limit** (int): Records per page.

        **Returns:**

        * **dict**: {data: list, pagination: dict}
        """
        if not self.is_history_logged:
            return None
        
        if not self.check_connectivity():
            return dict()

        _timezone = pytz.timezone(timezone)
        try:
            start_dt = _timezone.localize(datetime.strptime(start, DATETIME_FORMAT)).astimezone(pytz.UTC).timestamp()
            stop_dt = _timezone.localize(datetime.strptime(stop, DATETIME_FORMAT)).astimezone(pytz.UTC).timestamp()
        except ValueError:
            return dict()

        # Base query
        query = (TagValue
                .select(Tags.name, TagValue.value, TagValue.timestamp,
                        Units.unit.alias('tag_value_unit'))
                .join(Tags)
                .join(Units, on=(Tags.unit == Units.id))
                .where((TagValue.timestamp.between(start_dt, stop_dt)) & (Tags.name.in_(tags)))
                .order_by(TagValue.timestamp.desc()))

        total_records = query.count()
        
        # Safe pagination
        if limit <= 0: limit = 20
        if page <= 0: page = 1
        
        total_pages = math.ceil(total_records / limit)
        if total_pages == 0: total_pages = 1
        
        has_next = page < total_pages
        has_prev = page > 1

        paginated_query = query.paginate(page, limit).dicts()
        
        data = []
        utc_timezone = pytz.timezone('UTC')
        
        for entry in paginated_query:
            ts_val = entry['timestamp']
            if isinstance(ts_val, (int, float)):
                dt_object = datetime.fromtimestamp(ts_val, pytz.UTC)
            else:
                # Assuming naive datetime in UTC (based on read_trends using 'UTC' timezone to localize)
                dt_object = utc_timezone.localize(ts_val) if ts_val.tzinfo is None else ts_val
                
            formatted_ts = dt_object.astimezone(_timezone).strftime(DATETIME_FORMAT)
            
            data.append({
                "timestamp": formatted_ts,
                "tag_name": entry['name'],
                "value": f"{entry['value']} {entry['tag_value_unit']}"
            })

        return {
            "data": data,
            "pagination": {
                "page": page,
                "limit": limit,
                "total_records": total_records,
                "total_pages": total_pages,
                "has_next": has_next,
                "has_prev": has_prev
            }
        }
        
    @db_rollback
    def read_tabular_data(self, start:str, stop:str, timezone:str, tags:list, sample_time:int, page:int=1, limit:int=20):
        r"""
        Retrieves historical data in a tabular format with forward-fill resampling.
        
        Useful for exporting data where all tags need to share the same timestamps.

        **Parameters:**

        * **start** (str): Start datetime string.
        * **stop** (str): Stop datetime string.
        * **timezone** (str): Timezone.
        * **tags** (list): List of tag names.
        * **sample_time** (int): Resampling interval in seconds.
        * **page** (int): Page number.
        * **limit** (int): Rows per page.
            
        **Returns:**

        * **dict**: {tag_names, display_names, values, pagination}
        """
        if not self.is_history_logged:
            return None
        
        if not self.check_connectivity():
            return dict()

        _timezone = pytz.timezone(timezone)
        utc_timezone = pytz.UTC
        
        try:
            start_dt = _timezone.localize(datetime.strptime(start, DATETIME_FORMAT)).astimezone(utc_timezone)
            stop_dt = _timezone.localize(datetime.strptime(stop, DATETIME_FORMAT)).astimezone(utc_timezone)
            start_ts = start_dt.timestamp()
            stop_ts = stop_dt.timestamp()
        except ValueError:
            return dict()

        if sample_time <= 0:
            return dict()

        # Get display names mapping early
        try:
            tags_info = Tags.select(Tags.name, Tags.display_name).where(Tags.name.in_(tags)).dicts()
            display_map = {t['name']: t['display_name'] for t in tags_info}
        except Exception:
            display_map = {}

        tag_names = ["timestamp"] + tags
        display_names = ["timestamp"] + [display_map.get(tag, tag) for tag in tags]

        empty_result = {
            "tag_names": tag_names,
            "display_names": display_names,
            "values": [],
            "pagination": {}
        }

        # Check for data presence to adjust start time if necessary
        # 1. Check if there is any data BEFORE or AT start_dt (history)
        has_history = (TagValue
            .select()
            .join(Tags)
            .where(
                (Tags.name.in_(tags)) & 
                (TagValue.timestamp <= start_dt)
            )
            .limit(1)
            .count() > 0)
        
        if not has_history:
            # 2. If no history, find the first actual data point within the requested range
            min_ts = (TagValue
                .select(fn.Min(TagValue.timestamp))
                .join(Tags)
                .where(
                    (Tags.name.in_(tags)) & 
                    (TagValue.timestamp >= start_dt) & 
                    (TagValue.timestamp <= stop_dt) &
                    (TagValue.value.is_null(False))
                )
                .scalar())
            
            if min_ts is None:
                # No data in range and no history
                return empty_result
            
            # Adjust start to the first actual data point
            if isinstance(min_ts, datetime):
                 if min_ts.tzinfo is None:
                     min_ts = utc_timezone.localize(min_ts)
                 start_dt = min_ts
                 start_ts = start_dt.timestamp()
            elif isinstance(min_ts, (int, float)):
                 start_ts = float(min_ts)
                 start_dt = datetime.fromtimestamp(start_ts, pytz.UTC)

        # Calculate total records based on time range and sample time
        total_duration = stop_ts - start_ts
        if total_duration < 0:
            return empty_result
            
        total_records = math.floor(total_duration / sample_time) + 1
        
        # Pagination calculations
        if limit <= 0: limit = 20
        if page <= 0: page = 1
        
        total_pages = math.ceil(total_records / limit)
        if total_pages == 0: total_pages = 1
        
        has_next = page < total_pages
        has_prev = page > 1
        
        # Calculate start and end for current page
        start_index = (page - 1) * limit
        end_index = min(start_index + limit, total_records)
        
        page_start_ts = start_ts + (start_index * sample_time)
        page_end_ts = start_ts + ((end_index - 1) * sample_time)
        
        # Query data needed for this page plus context for forward fill
        
        data_points = []
        current_ts = page_start_ts
        
        # 1. Get initial values (state at page_start_ts)
        current_values = {}
        current_dt = datetime.fromtimestamp(current_ts, pytz.UTC)
        
        for tag_name in tags:
            # Get the latest value <= current_dt
            last_val_query = (TagValue
                .select(TagValue.value)
                .join(Tags)
                .where((Tags.name == tag_name) & (TagValue.timestamp <= current_dt))
                .order_by(TagValue.timestamp.desc())
                .limit(1)
                .dicts())
            
            entry = list(last_val_query)
            if entry:
                current_values[tag_name] = entry[0]['value']
            else:
                current_values[tag_name] = None

        # 2. Get changes within the page window
        page_start_dt = datetime.fromtimestamp(page_start_ts, pytz.UTC)
        page_end_dt = datetime.fromtimestamp(page_end_ts, pytz.UTC)

        changes_query = (TagValue
            .select(Tags.name, TagValue.value, TagValue.timestamp)
            .join(Tags)
            .where(
                (Tags.name.in_(tags)) & 
                (TagValue.timestamp > page_start_dt) & 
                (TagValue.timestamp <= page_end_dt) &
                (TagValue.value.is_null(False))
            )
            .order_by(TagValue.timestamp.asc())
            .dicts())
            
        # Organize changes by timestamp
        changes_by_ts = defaultdict(dict)
        for change in changes_query:
            ts_val = change['timestamp']
            if isinstance(ts_val, datetime):
                if ts_val.tzinfo is None:
                    ts_val = utc_timezone.localize(ts_val)
                ts = ts_val.timestamp()
            else:
                ts = float(ts_val)
            
            changes_by_ts[ts][change['name']] = change['value']
            
        # 3. Generate tabular data
        changes_iter = sorted(changes_by_ts.keys())
        change_idx = 0
        
        for i in range(end_index - start_index):
            step_ts = page_start_ts + (i * sample_time)
            
            # Update current_values with any changes that happened between last step and now (inclusive)
            while change_idx < len(changes_iter) and changes_iter[change_idx] <= step_ts:
                ts = changes_iter[change_idx]
                for tag, val in changes_by_ts[ts].items():
                    current_values[tag] = val
                change_idx += 1
                
            # Build row
            dt_object = datetime.fromtimestamp(step_ts, pytz.UTC)
            formatted_ts = dt_object.astimezone(_timezone).strftime(DATETIME_FORMAT)
            
            row_values = [formatted_ts]
            has_data = False
            for tag in tags:
                val = current_values.get(tag)
                row_values.append(val)
                if val is not None:
                    has_data = True
                
            if has_data:
                data_points.append(row_values)

        return {
            "tag_names": tag_names,
            "display_names": display_names,
            "values": data_points,
            "pagination": {
                "page": page,
                "limit": limit,
                "total_records": total_records,
                "total_pages": total_pages,
                "has_next": has_next,
                "has_prev": has_prev
            }
        }

    def _agregate_data_every_seconds(self, query, result, seconds:int, timezone:str="UTC"):
        r"""
        Downsamples data by averaging values within specific time buckets.
        
        **Parameters:**

        * **query**: The query object containing raw data.
        * **result**: The result dictionary to append to.
        * **seconds**: Bucket size in seconds.
        * **timezone**: Target timezone for result formatting.
        """
        # Aggregate data
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
                "y": avg_value
            })
        
        return result
        
    @db_rollback
    def read_segments(self):
        r"""
        Retrieves all configured segments.

        **Returns:**

        * **list**: List of Segment objects.
        """
        if not self.check_connectivity():

            return list()

        return Segment.read_all()


class DataLoggerEngine(BaseEngine):
    r"""
    Thread-safe Engine for the DataLogger.

    This class provides a thread-safe wrapper around the `DataLogger` class,
    ensuring that database operations from multiple threads do not conflict.
    """
    def __init__(self):

        super(DataLoggerEngine, self).__init__()
        self.logger = DataLogger()

    def create_tables(self, tables):
        r"""
        Creates default database tables.

        **Parameters:**

        * **tables** (list): List of database models.
        """
        self.logger.create_tables(tables)

    def drop_tables(self, tables:list):
        r"""
        Drops specified tables from the database.

        **Parameters:**

        * **tables** (list): List of database models.
        """
        self.logger.drop_tables(tables)

    def set_tag(
        self,
        tag:Tag
        ):
        r"""
        Registers a tag for logging in the database, using a thread-safe call.

        **Parameters:**

        * **tag** (Tag): The tag object to register.
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
        Retrieves all tags from the database (thread-safe).
        """
        _query = dict()
        _query["action"] = "get_tags"
        _query["parameters"] = dict()
        
        return self.query(_query)
    
    def get_tag_by_name(self, name:str):
        r"""
        Retrieves a tag by name (thread-safe).
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
        r"""
        Updates tag configuration (thread-safe).

        **Parameters:**

        * **id** (str): Tag ID.
        * **kwargs**: Properties to update.
        """

        _query = dict()
        _query["action"] = "update_tag"
        _query["parameters"] = dict()
        _query["parameters"]["id"] = id
        for key, value in kwargs.items():

            _query["parameters"][key] = value
    
        return self.query(_query)
    
    def delete_tag(self, id:str):
        r"""
        Deletes a tag (thread-safe).

        **Parameters:**

        * **id** (str): Tag ID.
        """
        _query = dict()
        _query["action"] = "delete_tag"
        _query["parameters"] = dict()
        _query["parameters"]["id"] = id
        
        return self.query(_query)

    def write_tag(self, tag:str, value:float, timestamp:datetime):
        r"""
        Writes a single tag value (thread-safe).

        **Parameters:**

        * **tag** (str): Tag name.
        * **value** (float): Value.
        * **timestamp** (datetime): Timestamp.
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
        Batch writes tag values (thread-safe).

        **Parameters:**

        * **tags** (list): List of tag value dictionaries.
        """
        _query = dict()
        _query["action"] = "write_tags"

        _query["parameters"] = dict()
        _query["parameters"]["tags"] = tags

        return self.query(_query)
    
    def read_trends(self, start:str, stop:str, timezone:str, *tags):
        r"""
        Reads trend data (thread-safe).

        **Parameters:**

        * **start** (str): Start time.
        * **stop** (str): End time.
        * **timezone** (str): Timezone.
        * **tags**: Variable length argument of tag names.
        """
        _query = dict()
        _query["action"] = "read_trends"
        _query["parameters"] = dict()
        _query["parameters"]["start"] = start
        _query["parameters"]["stop"] = stop
        _query["parameters"]["timezone"] = timezone
        _query["parameters"]["tags"] = tags
        return self.query(_query)

    def read_tabular_data(self, start:str, stop:str, timezone:str, tags:list, sample_time:int, page:int=1, limit:int=20):
        r"""
        Reads tabular data (thread-safe).
        """
        _query = dict()
        _query["action"] = "read_tabular_data"
        _query["parameters"] = dict()
        _query["parameters"]["start"] = start
        _query["parameters"]["stop"] = stop
        _query["parameters"]["timezone"] = timezone
        _query["parameters"]["tags"] = tags
        _query["parameters"]["sample_time"] = sample_time
        _query["parameters"]["page"] = page
        _query["parameters"]["limit"] = limit
        return self.query(_query)

    def read_segments(self):
        r"""
        Reads segments (thread-safe).
        """
        _query = dict()
        _query["action"] = "read_segments"
        _query["parameters"] = dict()
        return self.query(_query)
