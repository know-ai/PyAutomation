# -*- coding: utf-8 -*-
"""automation/logger/alarms.py

This module implements the Alarms Logger, responsible for persisting alarm definitions,
alarm status history, and summaries to the database.
"""
from datetime import datetime
import logging
from ..dbmodels import Alarms, AlarmSummary, AlarmTypes, AlarmStates
from .core import BaseEngine, BaseLogger
from ..alarms.trigger import TriggerType
from ..alarms.states import AlarmState
from ..utils.decorators import db_rollback


class AlarmsLogger(BaseLogger):
    r"""
    Logger class specialized for Alarm Management.

    It handles CRUD operations for Alarm definitions and logging of Alarm events (activations, acknowledgments, etc.).
    """

    def __init__(self):

        super(AlarmsLogger, self).__init__()

    @db_rollback
    def create_tables(self, tables):
        r"""
        Creates alarm-related tables and initializes default alarm types and states.

        **Parameters:**

        * **tables** (list): List of database models.
        """
        if not self.check_connectivity():
            
            return
        
        self._db.create_tables(tables, safe=True)
        try:
            AlarmSummary.ensure_schema()
        except Exception:
            logging.getLogger("pyautomation").warning(
                "AlarmSummary timestamp scale ensure skipped",
                exc_info=True,
            )
        self.__init_default_alarms_schema()

    @db_rollback
    def __init_default_alarms_schema(self):
        r"""
        Initializes default Alarm Types (High, Low, etc.) and Alarm States (Active, Ack, etc.) in the DB.
        """
        ## Alarm Types
        for alarm_type in TriggerType:

            AlarmTypes.create(name=alarm_type.value)

        ## Alarm States
        for alarm_state in AlarmState._states:
            name = alarm_state.state
            mnemonic = alarm_state.mnemonic
            condition = alarm_state.process_condition
            status = alarm_state.alarm_status
            AlarmStates.create(name=name, mnemonic=mnemonic, condition=condition, status=status)

    @db_rollback
    def create(
            self,
            id:str,
            name:str,
            tag:str,
            trigger_type:str,
            trigger_value:float,
            description:str,
            area:str=None):
        r"""
        Creates a new Alarm definition in the database.

        **Parameters:**

        * **id** (str): Alarm unique identifier.
        * **name** (str): Alarm name.
        * **tag** (str): Associated tag name.
        * **trigger_type** (str): Type of trigger (e.g., "HIGH", "LOW").
        * **trigger_value** (float): The threshold value.
        * **description** (str): Description of the alarm.
        """
        if not self.check_connectivity():
            
            return 

        Alarms.create(
            identifier=id,
            name=name,
            tag=tag,
            trigger_type=trigger_type,
            trigger_value=trigger_value,
            description=description,
            area=area,
        )

    @db_rollback
    def get_alarms(self):
        r"""
        Retrieves all configured alarms.

        **Returns:**

        * **list**: List of Alarm model instances.
        """
        if not self.check_connectivity():
            
            return list()
        
        alarms = Alarms.read_all()

        if alarms:

            return alarms
    
    @db_rollback
    def get_alarm_by_name(self, name:str)->Alarms|None:
        r"""
        Retrieves a specific alarm by name.

        **Parameters:**

        * **name** (str): Alarm name.

        **Returns:**

        * **Alarms**: The alarm model instance or None.
        """
        if not self.check_connectivity():
            
            return None
        
        return Alarms.read_by_name(name=name)

    @db_rollback        
    def get_lasts(self, lasts:int=10, area:str=None):
        r"""
        Retrieves the last N entries from the Alarm Summary (history).

        **Parameters:**

        * **lasts** (int): Number of entries to retrieve.

        **Returns:**

        * **list**: List of AlarmSummary entries.
        """
        if not self.is_history_logged:

            return list()
        
        if not self.check_connectivity():
            
            return list()
        
        return AlarmSummary.read_lasts(lasts=lasts, area=area)
    
    @db_rollback
    def filter_alarm_summary_by(
            self,
            states:list[str]=None,
            names:list[str]=None,
            tags:list[str]=None,
            greater_than_timestamp:datetime=None,
            less_than_timestamp:datetime=None,
            timezone:str=None,
            page:int=1,
            limit:int=20,
            area:str=None,
        ):
        r"""
        Filters alarm history based on various criteria.

        **Parameters:**

        * **states** (list[str]): Filter by alarm states.
        * **names** (list[str]): Filter by alarm names.
        * **tags** (list[str]): Filter by tag names.
        * **greater_than_timestamp** (datetime): Start time in UTC.
        * **less_than_timestamp** (datetime): End time in UTC.
        * **timezone** (str): IANA zone for serialize presentation.
        * **page** (int): Pagination page.
        * **limit** (int): Entries per page.

        **Returns:**

        * **list**: Filtered list of alarm summaries.
        
        **Note:**
        All timestamps are expected to be in UTC. Timezone conversions should be handled
        at the API endpoint level before calling this method.
        """
        if not self.is_history_logged:

            return None
        
        if not self.check_connectivity():
            
            return list()
        
        return AlarmSummary.filter_by(
            states=states,
            names=names,
            tags=tags,
            greater_than_timestamp=greater_than_timestamp,
            less_than_timestamp=less_than_timestamp,
            timezone=timezone,
            page=page,
            limit=limit,
            area=area,
        )
    
    @db_rollback
    def put(
        self,
        id:str,
        name:str=None,
        tag:str=None,
        description:str=None,
        alarm_type:str=None,
        trigger_value:str=None,
        state:str=None
        ):
        r"""
        Updates an existing alarm definition.

        **Parameters:**

        * **id** (str): Alarm ID.
        * **name** (str, optional): New name.
        * **tag** (str, optional): New tag.
        * **description** (str, optional): New description.
        * **alarm_type** (str, optional): New alarm type.
        * **trigger_value** (str, optional): New trigger value.
        * **state** (str, optional): New state.
        """
        if not self.check_connectivity():
            
            return None
        
        fields = dict()
        alarm = Alarms.read_by_identifier(identifier=id)
        if alarm:
            if name:
                fields["name"] = name
            if tag:
                fields["tag"] = tag
            if description:
                fields["description"] = description
            if alarm_type:
                alarm_type = AlarmTypes.read_by_name(name=alarm_type)
                fields["trigger_type"] = alarm_type
            if trigger_value:
                fields["trigger_value"] = trigger_value
            if state:
                alarm_state = AlarmStates.get_or_none(name=state)
                fields["state"] = alarm_state
            query = Alarms.put(
                id=alarm.id,
                **fields
            )

            return query

    @db_rollback
    def delete(self, id:str):
        r"""
        Logically deletes an alarm (sets it to "Out Of Service").

        **Parameters:**

        * **id** (str): Alarm ID.
        """
        if not self.check_connectivity():
            
            return None
        
        alarm_state = AlarmStates.get_or_none(name="Out Of Service")
        alarm = Alarms.read_by_identifier(identifier=id)
        Alarms.put(
            id=alarm.id,
            state=alarm_state
        )

    @db_rollback
    def create_record_on_alarm_summary(
            self,
            name:str,
            state:str,
            timestamp:datetime,
            ack_timestamp:datetime=None,
            identifier:str=None,
            tag:str=None,
            trigger_type:str=None,
            trigger_value=None,
            description:str=None,
            area:str=None,
        ):
        r"""
        Creates a new entry in the Alarm Summary (history log).

        **Parameters:**

        * **name** (str): Alarm name.
        * **state** (str): Alarm state.
        * **timestamp** (datetime): Timestamp of the event.
        * **ack_timestamp** (datetime, optional): Acknowledgment timestamp.
        """
        if not self.is_history_logged:

            return None
        
        from ..persistence.outbox import journal_then_remote
        from ..persistence.records import PersistableRecord

        record = PersistableRecord.alarm_create(
            name=name,
            state=state,
            timestamp=timestamp,
            ack_timestamp=ack_timestamp,
            area=area,
            identifier=identifier,
            tag=tag,
            trigger_type=trigger_type,
            trigger_value=trigger_value,
            description=description,
        )

        def _write():
            from ..persistence.remote import _ensure_alarm_catalog

            _ensure_alarm_catalog(record.payload())
            return AlarmSummary.create(
                name=name,
                state=state,
                timestamp=timestamp,
                ack_timestamp=ack_timestamp,
                area=record.payload().get("area") or area,
                sample_uuid=record.payload().get("sample_uuid") or record.idempotency_key(),
            )

        result, _ = journal_then_remote(record, _write, self.check_connectivity())
        return result

    @db_rollback
    def put_record_on_alarm_summary(
            self,
            name:str,
            state:str=None,
            ack_timestamp:datetime=None,
            identifier:str=None,
            tag:str=None,
            area:str=None,
        ):
        r"""
        Updates the latest record in the Alarm Summary for a given alarm.

        **Parameters:**

        * **name** (str): Alarm name.
        * **state** (str, optional): New state.
        * **ack_timestamp** (datetime, optional): Acknowledgment timestamp.
        """
        if not self.is_history_logged:

            return None

        from ..persistence.outbox import journal_then_remote
        from ..persistence.records import PersistableRecord

        record = PersistableRecord.alarm_update(
            name=name,
            state=state,
            ack_timestamp=ack_timestamp,
            area=area,
            identifier=identifier,
            tag=tag,
        )

        def _write():
            fields = dict()
            alarm = AlarmSummary.read_by_name(name=name, area=record.payload().get("area") or area)
            if not alarm:
                return None
            if ack_timestamp:
                from ..timebase import quantize_datetime_ms
                stamp = ack_timestamp
                if isinstance(stamp, datetime):
                    stamp = quantize_datetime_ms(stamp)
                fields["ack_time"] = stamp
            if state:
                alarm_state = AlarmStates.get_or_none(name=state)
                fields["state"] = alarm_state
            if not fields:
                return None
            return AlarmSummary.put(id=alarm.id, **fields)

        result, _ = journal_then_remote(record, _write, self.check_connectivity())
        return result

    def acknowledge_many(self, updates:list[dict]|None=None):
        r"""
        Persist a bulk acknowledge with one journal COMMIT and one remote transaction.

        Each item is ``{id, name, state, ack_timestamp}``. Catalog state and the
        latest AlarmSummary row are grouped by target state so round-trips stay
        O(1) in the number of ISA states (ACKED / Normal), not in N alarms.
        """
        items = list(updates or [])
        if not items:
            return 0

        from ..persistence.outbox import journal_then_remote_batch
        from ..persistence.records import PersistableRecord

        connected = self.check_connectivity()
        records = []
        if self.is_history_logged:
            records = [
                PersistableRecord.alarm_update(
                    name=item.get("name"),
                    state=item.get("state"),
                    ack_timestamp=item.get("ack_timestamp"),
                    area=item.get("area"),
                    identifier=item.get("id"),
                    tag=item.get("tag"),
                )
                for item in items
                if item.get("name")
            ]

        def _write():
            return self._apply_ack_batch(items)

        if records:
            result, _ = journal_then_remote_batch(records, _write, connected)
            return result if result is not None else 0
        if not connected:
            return 0
        return self._apply_ack_batch(items)

    @db_rollback
    def _apply_ack_batch(self, updates:list[dict])->int:
        if not updates:
            return 0
        db = self.get_db()
        if db is None:
            return 0

        from contextlib import nullcontext
        from peewee import fn
        from ..timebase import quantize_datetime_ms

        names = [item.get("name") for item in updates if item.get("name")]
        identifiers = [item.get("id") for item in updates if item.get("id")]
        by_name = {item["name"]: item for item in updates if item.get("name")}
        by_identifier = {item["id"]: item for item in updates if item.get("id")}

        clauses = []
        if identifiers:
            clauses.append(Alarms.identifier.in_(identifiers))
        if names:
            clauses.append(Alarms.name.in_(names))
        if not clauses:
            return 0

        query = Alarms.select()
        catalog = list(query.where(clauses[0] if len(clauses) == 1 else (clauses[0] | clauses[1])))
        if not catalog:
            return 0

        state_cache = {}

        def _state(name:str):
            if not name:
                return None
            if name not in state_cache:
                state_cache[name] = AlarmStates.get_or_none(name=name)
            return state_cache[name]

        def _update_for(row):
            return by_name.get(row.name) or by_identifier.get(row.identifier)

        ack_time = None
        for item in updates:
            stamp = item.get("ack_timestamp")
            if isinstance(stamp, datetime):
                ack_time = quantize_datetime_ms(stamp)
                break

        catalog_by_state: dict[int, list[int]] = {}
        alarm_pks = []
        for row in catalog:
            item = _update_for(row)
            if not item:
                continue
            alarm_pks.append(row.id)
            state_row = _state(item.get("state"))
            if state_row is None:
                continue
            catalog_by_state.setdefault(state_row.id, []).append(row.id)

        ctx = db.atomic() if hasattr(db, "atomic") else nullcontext()
        with ctx:
            written = 0
            for state_id, ids in catalog_by_state.items():
                if not ids:
                    continue
                Alarms.update(state=state_id).where(Alarms.id.in_(ids)).execute()
                written += len(ids)

            if self.is_history_logged and alarm_pks and ack_time is not None:
                latest = list(
                    AlarmSummary
                    .select(AlarmSummary.alarm, fn.MAX(AlarmSummary.id).alias("max_id"))
                    .where(AlarmSummary.alarm.in_(alarm_pks))
                    .group_by(AlarmSummary.alarm)
                )
                max_ids = [row.max_id for row in latest if getattr(row, "max_id", None)]
                if max_ids:
                    summaries = list(
                        AlarmSummary
                        .select(AlarmSummary, Alarms)
                        .join(Alarms)
                        .where(AlarmSummary.id.in_(max_ids))
                    )
                    summary_by_state: dict[int, list[int]] = {}
                    for summary in summaries:
                        item = by_name.get(summary.alarm.name)
                        if not item:
                            continue
                        state_row = _state(item.get("state"))
                        if state_row is None:
                            continue
                        summary_by_state.setdefault(state_row.id, []).append(summary.id)
                    for state_id, ids in summary_by_state.items():
                        if not ids:
                            continue
                        AlarmSummary.update(
                            ack_time=ack_time,
                            state=state_id,
                        ).where(AlarmSummary.id.in_(ids)).execute()
            return written

    @db_rollback
    def get_alarm_summary(self, page:int=1, limit:int=20):
        r"""
        Retrieves the alarm summary with pagination.

        **Parameters:**

        * **page** (int): Page number (default: 1).
        * **limit** (int): Records per page (default: 20).

        **Returns:**

        * **dict**: Dictionary with 'data' (list of AlarmSummary records) and 'pagination' metadata.
        """
        if not self.is_history_logged:

            return None
        
        if not self.check_connectivity():
            
            return {
                "data": list(),
                "pagination": {
                    "page": page,
                    "limit": limit,
                    "total_records": 0,
                    "total_pages": 1,
                    "has_next": False,
                    "has_prev": False
                }
            }
        
        return AlarmSummary.read_all(page=page, limit=limit)
    
    
class AlarmsLoggerEngine(BaseEngine):
    r"""
    Thread-safe Engine for the AlarmsLogger.
    """

    def __init__(self):

        super(AlarmsLoggerEngine, self).__init__()
        self.logger = AlarmsLogger()

    def create(
        self,
        id:str,
        name:str,
        tag:str,
        trigger_type:str,
        trigger_value:float,
        description:str,
        area:str=None,
        ):
        r"""
        Thread-safe alarm creation.
        """
        _query = dict()
        _query["action"] = "create"
        _query["parameters"] = dict()
        _query["parameters"]["id"] = id
        _query["parameters"]["name"] = name
        _query["parameters"]["tag"] = tag
        _query["parameters"]["trigger_type"] = trigger_type
        _query["parameters"]["trigger_value"] = trigger_value
        _query["parameters"]["description"] = description
        _query["parameters"]["area"] = area
        
        return self.query(_query)
    
    def get_lasts(
        self,
        lasts:int=1,
        area:str=None,
        ):
        r"""
        Thread-safe retrieval of last alarm events.
        """
        _query = dict()
        _query["action"] = "get_lasts"
        _query["parameters"] = dict()
        _query["parameters"]["lasts"] = lasts
        _query["parameters"]["area"] = area
        
        return self.query(_query)
    
    def get_alarms(self):
        r"""
        Thread-safe retrieval of all alarms.
        """
        _query = dict()
        _query["action"] = "get_alarms"
        _query["parameters"] = dict()
        
        return self.query(_query)
    
    def get_alarm_by_name(self, name:str):
        r"""
        Thread-safe retrieval of an alarm by name.
        """
        _query = dict()
        _query["action"] = "get_alarm_by_name"
        _query["parameters"] = dict()
        _query["parameters"]["name"] = name
        
        return self.query(_query)
    
    def filter_alarm_summary_by(
        self,
        names:list[str]=None,
        states:list[int]=None,
        tags:list[int]=None,
        greater_than_timestamp:datetime=None,
        less_than_timestamp:datetime=None,
        timezone:str=None,
        page:int=1,
        limit:int=20,
        area:str=None,
        ):
        r"""
        Thread-safe filtering of alarm summary.
        
        **Note:**
        All timestamps are expected to be in UTC. Timezone conversions should be handled
        at the API endpoint level before calling this method. ``timezone`` is only
        used when serializing presentation timestamps.
        """
        _query = dict()
        _query["action"] = "filter_alarm_summary_by"
        _query["parameters"] = dict()
        _query["parameters"]["names"] = names
        _query["parameters"]["states"] = states
        _query["parameters"]["tags"] = tags
        _query["parameters"]["greater_than_timestamp"] = greater_than_timestamp
        _query["parameters"]["less_than_timestamp"] = less_than_timestamp
        _query["parameters"]["timezone"] = timezone
        _query["parameters"]["page"] = page
        _query["parameters"]["limit"] = limit
        _query["parameters"]["area"] = area
        
        return self.query(_query)
    
    def create_record_on_alarm_summary(
        self,
        name:str,
        state:str,
        timestamp:datetime,
        ack_timestamp:datetime=None,
        identifier:str=None,
        tag:str=None,
        trigger_type:str=None,
        trigger_value=None,
        description:str=None,
        area:str=None,
        ):
        r"""
        Thread-safe creation of alarm history record.
        """
        _query = dict()
        _query["action"] = "create_record_on_alarm_summary"
        _query["parameters"] = dict()
        _query["parameters"]["name"] = name
        _query["parameters"]["state"] = state
        _query["parameters"]["timestamp"] = timestamp
        _query["parameters"]["ack_timestamp"] = ack_timestamp
        _query["parameters"]["identifier"] = identifier
        _query["parameters"]["tag"] = tag
        _query["parameters"]["trigger_type"] = trigger_type
        _query["parameters"]["trigger_value"] = trigger_value
        _query["parameters"]["description"] = description
        _query["parameters"]["area"] = area
        
        return self.query(_query)
    
    def put_record_on_alarm_summary(
        self,
        name:str,
        state:str=None,
        ack_timestamp:datetime=None,
        identifier:str=None,
        tag:str=None,
        area:str=None,
        ):
        r"""
        Thread-safe update of alarm history record.
        """
        _query = dict()
        _query["action"] = "put_record_on_alarm_summary"
        _query["parameters"] = dict()
        _query["parameters"]["name"] = name
        _query["parameters"]["state"] = state
        _query["parameters"]["ack_timestamp"] = ack_timestamp
        _query["parameters"]["identifier"] = identifier
        _query["parameters"]["tag"] = tag
        _query["parameters"]["area"] = area

        return self.query(_query)

    def acknowledge_many(self, updates:list[dict]|None=None):
        r"""
        Thread-safe bulk acknowledge (one engine round-trip).
        """
        _query = dict()
        _query["action"] = "acknowledge_many"
        _query["parameters"] = dict()
        _query["parameters"]["updates"] = updates or []
        return self.query(_query)

    def put(
        self,
        id:str,
        name:str=None,
        tag:str=None,
        description:str=None,
        alarm_type:str=None,
        trigger_value:str=None,
        state:str=None
        ):
        r"""
        Thread-safe alarm update.
        """
        _query = dict()
        _query["action"] = "put"
        _query["parameters"] = dict()
        _query["parameters"]["id"] = id
        _query["parameters"]["name"] = name
        _query["parameters"]["tag"] = tag
        _query["parameters"]["description"] = description
        _query["parameters"]["alarm_type"] = alarm_type
        _query["parameters"]["trigger_value"] = trigger_value
        _query["parameters"]["state"] = state

        return self.query(_query)

    def delete(self, id:str):
        r"""
        Thread-safe alarm deletion.
        """
        _query = dict()
        _query["action"] = "delete"
        _query["parameters"] = dict()
        _query["parameters"]["id"] = id
        return self.query(_query)

    def get_alarm_summary(self, page:int=1, limit:int=20):
        r"""
        Thread-safe retrieval of alarm summary with pagination.
        """
        _query = dict()
        _query["action"] = "get_alarm_summary"
        _query["parameters"] = dict()
        _query["parameters"]["page"] = page
        _query["parameters"]["limit"] = limit
        
        return self.query(_query)

    def create_tables(self, tables):
        r"""
        Thread-safe table creation.
        """
        self.logger.create_tables(tables)
