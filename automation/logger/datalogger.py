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
from peewee import IntegrityError


DATETIME_FORMAT = "%Y-%m-%d %H:%M:%S.%f"


def _tagvalue_bound(dt: datetime) -> datetime:
    """UTC datetime for ``TagValue.timestamp`` comparisons.

    Do **not** pre-scale to integer ticks. Peewee ``TimestampField.db_value``
    treats a raw ``int`` as unix **seconds** and multiplies by ``resolution``
    (1000 for milliseconds). Passing already-scaled ms ticks therefore becomes
    a 16-digit bound that never matches stored 13-digit rows, so trends return
    empty series.
    """
    if dt.tzinfo is None:
        return pytz.UTC.localize(dt)
    return dt.astimezone(pytz.UTC)


def _as_epoch_seconds(value):
    if value is None:
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = pytz.UTC.localize(value)
        return value.timestamp()
    from ..timebase import epoch_seconds_from_db_tick

    return epoch_seconds_from_db_tick(value)


def _as_utc_datetime(value):
    if value is None:
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return pytz.UTC.localize(value)
        return value.astimezone(pytz.UTC)
    return datetime.fromtimestamp(_as_epoch_seconds(value), pytz.UTC)


def _is_unique_violation(exc: BaseException) -> bool:
    name = type(exc).__name__
    if name in ("IntegrityError", "UniqueViolation"):
        return True
    text = str(exc).lower()
    return "duplicate key" in text or "unique constraint" in text


_FK_TAG_FIELDS = ("unit", "display_unit", "data_type")


def _tag_put_fields(**fields) -> dict:
    """Drop None / empty FK values so an update cannot wipe required columns."""
    payload = {}
    for key, value in fields.items():
        if value is None:
            continue
        if key in _FK_TAG_FIELDS and value == "":
            continue
        payload[key] = value
    return payload


def _lookup_tag_row(name: str, identifier: str | None = None, display_name: str | None = None):
    row = Tags.get_or_none(Tags.name == name) if name else None
    if row is None and identifier:
        row = Tags.get_or_none(Tags.identifier == identifier)
    if row is None and display_name:
        row = Tags.get_or_none(Tags.display_name == display_name)
    return row


def _mirror_historian_tag_row(name: str, identifier: str | None = None) -> None:
    try:
        from ..catalog.bootstrap import mirror_historian_row

        row = Tags.get_or_none(Tags.name == name)
        if row is None and identifier:
            row = Tags.get_or_none(Tags.identifier == identifier)
        if row is not None:
            mirror_historian_row(row)
    except Exception:
        logging.getLogger("pyautomation").debug("catalog tag mirror skipped", exc_info=True)


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
        kp:float=None,
        area:str=None,
        owner_node:str=None,
        filter_enabled:bool=False,
        filter_wavelet:str="db4",
        filter_level:int=4,
        filter_threshold_factor:float=3.0,
        filter_persist:bool=False,
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

        existing = _lookup_tag_row(name, id)
        if existing is not None:
            try:
                Tags.put(
                    id=existing.id,
                    **_tag_put_fields(
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
                        kp=kp,
                        area=area,
                        owner_node=owner_node,
                        filter_enabled=filter_enabled,
                        filter_wavelet=filter_wavelet,
                        filter_level=filter_level,
                        filter_threshold_factor=filter_threshold_factor,
                        filter_persist=filter_persist,
                    ),
                )
            except Exception as exc:
                if not _is_unique_violation(exc) and not isinstance(exc, IntegrityError):
                    raise
                logging.getLogger("pyautomation").warning(
                    "Failed to set tag %s: %s. Continuing with next tag.",
                    name,
                    exc,
                )
                return None
            _mirror_historian_tag_row(name, id)
            return existing

        try:
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
                kp=kp,
                area=area,
                owner_node=owner_node,
                filter_enabled=filter_enabled,
                filter_wavelet=filter_wavelet,
                filter_level=filter_level,
                filter_threshold_factor=filter_threshold_factor,
                filter_persist=filter_persist,
            )
        except Exception as exc:
            if not _is_unique_violation(exc) and not isinstance(exc, IntegrityError):
                raise
            try:
                self._db.connection().rollback()
            except Exception:
                pass
            existing = _lookup_tag_row(name, id, display_name)
            if existing is None:
                logging.getLogger("pyautomation").warning(
                    "Failed to set tag %s: %s. Continuing with next tag.",
                    name,
                    exc,
                )
                return None
            logging.getLogger("pyautomation").warning(
                "Tag %s already exists with a unique-constraint conflict; updating",
                name,
            )
            try:
                Tags.put(
                    id=existing.id,
                    **_tag_put_fields(
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
                        kp=kp,
                        area=area,
                        owner_node=owner_node,
                        filter_enabled=filter_enabled,
                        filter_wavelet=filter_wavelet,
                        filter_level=filter_level,
                        filter_threshold_factor=filter_threshold_factor,
                        filter_persist=filter_persist,
                    ),
                )
            except Exception as put_exc:
                if not _is_unique_violation(put_exc) and not isinstance(put_exc, IntegrityError):
                    raise
                logging.getLogger("pyautomation").warning(
                    "Failed to set tag %s: %s. Continuing with next tag.",
                    name,
                    put_exc,
                )
                return None
            _mirror_historian_tag_row(name, id)
            return existing
        _mirror_historian_tag_row(name, id)
        return _lookup_tag_row(name, id)
            
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
        try:
            from ..catalog.mutations import soft_deactivate_tag_local

            soft_deactivate_tag_local(identifier=id, name=getattr(tag, "name", None))
        except Exception:
            logging.getLogger("pyautomation").debug("catalog tag soft-delete mirror skipped", exc_info=True)

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
        * **kwargs**: Fields to update.
        """
        if not self.check_connectivity():

            return None
        
        tag = Tags.get(identifier=id)

        result = Tags.put(id=tag.id, **kwargs)
        try:
            from ..catalog.bootstrap import mirror_historian_row

            refreshed = Tags.get_or_none(Tags.identifier == id) or Tags.get_or_none(Tags.id == tag.id)
            if refreshed is not None:
                mirror_historian_row(refreshed)
        except Exception:
            logging.getLogger("pyautomation").debug("catalog tag update mirror skipped", exc_info=True)
        return result

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
            try:
                if isinstance(tag, dict):
                    self.set_tag(**tag)
                else:
                    self.set_tag(tag)
            except Exception as exc:
                logging.getLogger("pyautomation").warning(
                    "Failed to set tag in batch: %s. Continuing with next tag.",
                    exc,
                )

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
        start_db = _tagvalue_bound(start_dt)
        stop_db = _tagvalue_bound(stop_dt)
              
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

        # TagValue.timestamp is bigint milliseconds (TimestampField resolution=3).
        # to_timestamp() expects seconds, so divide via from_timestamp().
        ts_epoch = TagValue.timestamp
        ts_tz = TagValue.timestamp.from_timestamp()

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
                .where((ts_epoch.between(start_db, stop_db)) & (Tags.name.in_(tags)))
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
                .where((ts_epoch.between(start_db, stop_db)) & (Tags.name.in_(tags)))
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
    def read_backfill(
        self,
        tags: list,
        start_ms: int,
        stop_ms: int,
        *,
        limit_per_tag: int = 1000,
    ) -> dict:
        r"""
        Raw TagValue samples for Socket.IO reconnect backfill (ISO UTC timestamps).

        Returns ``{tag_name: [{"timestamp": ISO-8601, "value": float}, ...]}``
        ordered ascending per tag. Caps each series at ``limit_per_tag``.
        """
        from ..timebase import iso_millis

        if not self.is_history_logged:
            return {}
        if not self.check_connectivity():
            return {}
        if not tags:
            return {}

        try:
            start_ms = int(start_ms)
            stop_ms = int(stop_ms)
            limit_per_tag = max(1, min(int(limit_per_tag), 5000))
        except (TypeError, ValueError):
            return {}

        if stop_ms < start_ms:
            start_ms, stop_ms = stop_ms, start_ms

        # Guardrail: never wider than 5 minutes (max HMI strip-chart span).
        max_span_ms = 5 * 60 * 1000
        if stop_ms - start_ms > max_span_ms:
            start_ms = stop_ms - max_span_ms

        start_dt = datetime.fromtimestamp(start_ms / 1000.0, pytz.UTC)
        stop_dt = datetime.fromtimestamp(stop_ms / 1000.0, pytz.UTC)
        start_db = _tagvalue_bound(start_dt)
        stop_db = _tagvalue_bound(stop_dt)
        ts_epoch = TagValue.timestamp

        query = (
            TagValue.select(
                Tags.name.alias("name"),
                TagValue.value,
                TagValue.timestamp,
            )
            .join(Tags)
            .where((ts_epoch.between(start_db, stop_db)) & (Tags.name.in_(list(tags))))
            .order_by(ts_epoch.asc())
            .dicts()
        )

        out: dict[str, list] = {str(name): [] for name in tags}
        counts: dict[str, int] = {str(name): 0 for name in tags}
        for entry in query:
            name = str(entry.get("name") or "")
            if name not in out:
                continue
            if counts[name] >= limit_per_tag:
                continue
            ts = iso_millis(_as_utc_datetime(entry.get("timestamp")))
            if not ts:
                continue
            try:
                value = float(entry.get("value"))
            except (TypeError, ValueError):
                continue
            if value != value:  # NaN
                continue
            out[name].append({"timestamp": ts, "value": value})
            counts[name] += 1
        return out

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
            start_dt = _timezone.localize(datetime.strptime(start, DATETIME_FORMAT)).astimezone(pytz.UTC)
            stop_dt = _timezone.localize(datetime.strptime(stop, DATETIME_FORMAT)).astimezone(pytz.UTC)
        except ValueError:
            return dict()

        # Base query — compare against stored millisecond ticks, not unix seconds.
        query = (TagValue
                .select(Tags.name, TagValue.value, TagValue.timestamp,
                        Units.unit.alias('tag_value_unit'))
                .join(Tags)
                .join(Units, on=(Tags.unit == Units.id))
                .where((TagValue.timestamp.between(_tagvalue_bound(start_dt), _tagvalue_bound(stop_dt))) & (Tags.name.in_(tags)))
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
        
        for entry in paginated_query:
            ts_val = entry['timestamp']
            dt_object = _as_utc_datetime(ts_val)
            if dt_object is None:
                continue
                
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
            max_dt = _as_utc_datetime(max_ts)
            if max_dt is not None and stop_dt > max_dt:
                stop_dt = max_dt
                stop_ts = stop_dt.timestamp()

        # Check for data presence to adjust start time if necessary
        # 1. Check if there is any data BEFORE or AT start_dt (history)
        has_history = (TagValue
            .select()
            .join(Tags)
            .where(
                (Tags.name.in_(tags)) & 
                (TagValue.timestamp <= _tagvalue_bound(start_dt))
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
                    (TagValue.timestamp >= _tagvalue_bound(start_dt)) & 
                    (TagValue.timestamp <= _tagvalue_bound(stop_dt)) &
                    (TagValue.value.is_null(False))
                )
                .scalar())
            
            if min_ts is None:
                # No data in range and no history
                return empty_result
            
            start_dt = _as_utc_datetime(min_ts)
            if start_dt is None:
                return empty_result
            start_ts = start_dt.timestamp()

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
                (TagValue.timestamp >= _tagvalue_bound(page_start_dt)) & 
                (TagValue.timestamp <= _tagvalue_bound(page_end_dt)) &
                (TagValue.value.is_null(False))
            )
            .order_by(TagValue.timestamp.asc())
            .dicts())
            
        # Organize changes by timestamp
        changes_by_ts = defaultdict(dict)
        for change in changes_query:
            ts = _as_epoch_seconds(change['timestamp'])
            if ts is None:
                continue
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
                    .where((Tags.name == tag_name) & (TagValue.timestamp <= _tagvalue_bound(step_dt)))
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
        _query["parameters"]["area"] = tag.area
        _query["parameters"]["owner_node"] = tag.owner_node
        _query["parameters"]["filter_enabled"] = getattr(tag, "filter_enabled", False)
        _query["parameters"]["filter_wavelet"] = getattr(tag, "filter_wavelet", "db4")
        _query["parameters"]["filter_level"] = getattr(tag, "filter_level", 4)
        _query["parameters"]["filter_threshold_factor"] = getattr(tag, "filter_threshold_factor", 3.0)
        _query["parameters"]["filter_persist"] = getattr(tag, "filter_persist", False)
        
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
