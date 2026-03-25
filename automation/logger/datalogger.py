# -*- coding: utf-8 -*-
"""automation/logger/datalogger.py

This module implements the Data Logger, responsible for persisting tag values (time-series data)
and managing tag configurations in the database.
"""
import pytz, logging, math
from peewee import fn, SQL
from collections import defaultdict
from datetime import datetime, timedelta
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
        opcua_client_name:str=None,
        node_namespace:str=None,
        scan_time:int=None,
        dead_band:float=None,
        manufacturer:str="",
        segment:str="",
        kp:float=None
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
        * **opcua_client_name** (str, optional): OPC UA client name.
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
            opcua_client_name=opcua_client_name,
            node_namespace=node_namespace,
            scan_time=scan_time,
            dead_band=dead_band,
            manufacturer=manufacturer,
            segment=segment,
            kp=kp
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
            gaussian_filter_value = kwargs["gaussian_filter"]
            if isinstance(gaussian_filter_value, str):
                kwargs["gaussian_filter"] = gaussian_filter_value.strip().lower() in ("1", "true", "yes", "on")
            else:
                kwargs["gaussian_filter"] = bool(gaussian_filter_value)
        
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
        start_dt = _timezone.localize(datetime.strptime(start, DATETIME_FORMAT)).astimezone(pytz.UTC)
        stop_dt = _timezone.localize(datetime.strptime(stop, DATETIME_FORMAT)).astimezone(pytz.UTC)

        # Guardrail: limitar el rango máximo a 3 meses (≈ 90 días).
        # Si se solicita más, devolvemos SOLO el tramo más reciente de 3 meses.
        max_span = timedelta(days=90)
        if stop_dt - start_dt > max_span:
            start_dt = stop_dt - max_span

        start_ts = float(start_dt.timestamp())
        stop_ts = float(stop_dt.timestamp())
              
        # Base query: para trending, preferimos agregación en SQL (mucho más eficiente)
        # y solo caemos a "raw" para spans pequeños.
         
        # Structure the data
        # Guardrail: limitar cantidad de puntos devueltos (por tag) para no saturar el front.
        # Nota: el gráfico suele verse bien con 1k–3k puntos.
        max_points = 2000

        span_seconds = max(0.0, stop_ts - start_ts)
        time_span_minutes = span_seconds / 60.0
        result = defaultdict(lambda: {"values": []})

        # Elegir bucket dinámico para devolver <= max_points por tag.
        # Para buckets exactos de minuto/hora/día usamos date_trunc (más eficiente).
        bucket_seconds = 0
        if span_seconds > 0 and max_points > 0:
            bucket_seconds = int(math.ceil(span_seconds / float(max_points)))

        # Nunca bajar de 1s cuando hay span.
        if span_seconds > 0:
            bucket_seconds = max(1, bucket_seconds)

        # Para spans muy cortos, devolvemos raw (sin agregación).
        # Umbral conservador: si el bucket calculado es <= 1s, raw.
        use_raw = (span_seconds <= 0) or (bucket_seconds <= 1 and time_span_minutes <= 120)

        # En esta implementación, TagValue.timestamp en DB puede estar como epoch (bigint/float).
        # Para bucketing y formateo convertimos a timestamptz con to_timestamp().
        ts_epoch = TagValue.timestamp
        ts_tz = fn.to_timestamp(ts_epoch)

        if not use_raw:
            # Postgres 17 (vanilla) soporta date_bin(interval, ts, origin) para bucketing arbitrario.
            # Esto evita armar SQL manual con format() (no soportado por peewee.SQL).
            if bucket_seconds >= 86400 and bucket_seconds % 86400 == 0:
                bucket_base = fn.date_trunc("day", ts_tz)
            elif bucket_seconds >= 3600 and bucket_seconds % 3600 == 0:
                bucket_base = fn.date_trunc("hour", ts_tz)
            elif bucket_seconds >= 60 and bucket_seconds % 60 == 0:
                bucket_base = fn.date_trunc("minute", ts_tz)
            else:
                origin = fn.to_timestamp(0)
                bucket_base = fn.date_bin(
                    SQL(f"make_interval(secs => {int(bucket_seconds)})"),
                    ts_tz,
                    origin,
                )
            bucket_expr = bucket_base.alias("bucket")

            query = (
                TagValue.select(
                    Tags.name.alias("name"),
                    bucket_expr,
                    fn.AVG(TagValue.value).alias("value"),
                    Units.unit.alias("tag_value_unit"),
                    Variables.name.alias("variable_name"),
                )
                .join(Tags)
                .join(Units, on=(Tags.unit == Units.id))
                .join(Variables, on=(Units.variable_id == Variables.id))
                # Filtrar en epoch (mucho más eficiente si la columna es bigint/numérica).
                .where((ts_epoch.between(start_ts, stop_ts)) & (Tags.name.in_(tags)))
                .group_by(Tags.name, bucket_expr, Units.unit, Variables.name)
                .order_by(bucket_expr)
                .dicts()
            )

            # Optimización: formatear timestamp en SQL (menos overhead en Python).
            # Postgres: timezone(tz, timestamptz) -> timestamp en esa zona.
            # to_char(..., 'MM/DD/YYYY, HH24:MI:SS.US') alinea con el parser de Trends.tsx.
            ts_fmt = "MM/DD/YYYY, HH24:MI:SS.US"
            query = query.select_extend(
                fn.to_char(fn.timezone(timezone, bucket_base), ts_fmt).alias("x")
            )
            for entry in query:
                tag_name = entry["name"]
                result[tag_name]["values"].append({"x": entry["x"], "y": entry["value"]})
                # Guardar unit/variable si están disponibles (evita consultas extra por tag)
                if "unit" not in result[tag_name]:
                    result[tag_name]["unit"] = entry.get("tag_value_unit")
                if "variable" not in result[tag_name]:
                    result[tag_name]["variable"] = entry.get("variable_name")
        else:
            # Use original data (sin agregación)
            query = (
                TagValue.select(
                    Tags.name.alias("name"),
                    TagValue.value,
                    TagValue.timestamp,
                    Units.unit.alias("tag_value_unit"),
                    Variables.name.alias("variable_name"),
                )
                .join(Tags)
                .join(Units, on=(Tags.unit == Units.id))
                .join(Variables, on=(Units.variable_id == Variables.id))
                .where((ts_epoch.between(start_ts, stop_ts)) & (Tags.name.in_(tags)))
                .order_by(ts_epoch)
                .dicts()
            )
            ts_fmt = "MM/DD/YYYY, HH24:MI:SS.US"
            query = query.select_extend(
                fn.to_char(fn.timezone(timezone, ts_tz), ts_fmt).alias("x")
            )
            for entry in query:
                tag_name = entry["name"]
                result[tag_name]["values"].append({"x": entry["x"], "y": entry["value"]})
                if "unit" not in result[tag_name]:
                    result[tag_name]["unit"] = entry.get("tag_value_unit")
                if "variable" not in result[tag_name]:
                    result[tag_name]["variable"] = entry.get("variable_name")
        
        # Asegurar que todos los tags solicitados existan en el resultado (aunque no haya data).
        for tag in tags:
            _ = result[tag]  # materializa entry
        
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

        # Validate stop date: if it's in the future, adjust to the most recent timestamp in database
        max_ts = (TagValue
            .select(fn.Max(TagValue.timestamp))
            .join(Tags)
            .where(
                (Tags.name.in_(tags)) & 
                (TagValue.value.is_null(False))
            )
            .scalar())
        
        if max_ts is not None:
            if isinstance(max_ts, datetime):
                if max_ts.tzinfo is None:
                    max_ts = utc_timezone.localize(max_ts)
                max_dt = max_ts
            else:
                max_dt = datetime.fromtimestamp(float(max_ts), pytz.UTC)
            
            # If stop_dt is in the future compared to the most recent data, adjust it
            if stop_dt > max_dt:
                stop_dt = max_dt
                stop_ts = stop_dt.timestamp()

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
        
        # Calculate start and end for current page (in DESC order, page 1 = most recent)
        start_index = (page - 1) * limit
        end_index = min(start_index + limit, total_records)
        
        # For DESC order: calculate timestamps from stop backwards
        # Page 1 starts at stop_ts and goes backwards
        page_end_ts = stop_ts - (start_index * sample_time)  # Most recent timestamp for this page
        page_start_ts = stop_ts - ((end_index - 1) * sample_time)  # Oldest timestamp for this page
        
        # Query data needed for this page plus context for forward fill
        
        data_points = []
        
        # 2. Get all changes within the page window (for forward fill calculation)
        page_start_dt = datetime.fromtimestamp(page_start_ts, pytz.UTC)
        page_end_dt = datetime.fromtimestamp(page_end_ts, pytz.UTC)

        changes_query = (TagValue
            .select(Tags.name, TagValue.value, TagValue.timestamp)
            .join(Tags)
            .where(
                (Tags.name.in_(tags)) & 
                (TagValue.timestamp >= page_start_dt) & 
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
            
        # 3. Generate tabular data in DESC order (most recent first)
        # Generate all timestamps for this page in DESC order
        num_rows = end_index - start_index
        timestamps_desc = []
        for i in range(num_rows):
            step_ts = page_end_ts - (i * sample_time)
            timestamps_desc.append(step_ts)
        
        # For each timestamp in DESC order, get the value using forward fill
        # Forward fill: use the most recent value <= timestamp
        for step_ts in timestamps_desc:
            step_dt = datetime.fromtimestamp(step_ts, pytz.UTC)
            
            # Get values for each tag at this timestamp (forward fill)
            row_values = []
            has_data = False
            
            # Timestamp column
            formatted_ts = step_dt.astimezone(_timezone).strftime(DATETIME_FORMAT)
            row_values.append(formatted_ts)
            
            # Get value for each tag (most recent value <= step_ts)
            for tag_name in tags:
                last_val_query = (TagValue
                    .select(TagValue.value)
                    .join(Tags)
                    .where((Tags.name == tag_name) & (TagValue.timestamp <= step_dt))
                    .order_by(TagValue.timestamp.desc())
                    .limit(1)
                    .dicts())
                
                entry = list(last_val_query)
                if entry:
                    val = entry[0]['value']
                    row_values.append(val)
                    if val is not None:
                        has_data = True
                else:
                    row_values.append(None)
            
            if has_data:
                data_points.append(row_values)
        
        # Data points are already in DESC order (most recent first)

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
        _query["parameters"]["opcua_client_name"] = tag.get_opcua_client_name() if hasattr(tag, 'get_opcua_client_name') else None
        _query["parameters"]["node_namespace"] = tag.node_namespace
        _query["parameters"]["scan_time"] = tag.scan_time
        _query["parameters"]["dead_band"] = tag.dead_band
        _query["parameters"]["manufacturer"] = tag.manufacturer
        _query["parameters"]["segment"] = tag.segment
        _query["parameters"]["kp"] = tag.kp
        
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
