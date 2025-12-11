# -*- coding: utf-8 -*-
"""automation/logger/alarms.py

This module implements the Alarms Logger, responsible for persisting alarm definitions,
alarm status history, and summaries to the database.
"""
from datetime import datetime
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
            description:str):
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
            description=description
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
    def get_lasts(self, lasts:int=10):
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
        
        return AlarmSummary.read_lasts(lasts=lasts)
    
    @db_rollback
    def filter_alarm_summary_by(
            self,
            states:list[str]=None,
            names:list[str]=None,
            tags:list[str]=None,
            greater_than_timestamp:datetime=None,
            less_than_timestamp:datetime=None,
            timezone:str="UTC",
            page:int=1,
            limit:int=20
        ):
        r"""
        Filters alarm history based on various criteria.

        **Parameters:**

        * **states** (list[str]): Filter by alarm states.
        * **names** (list[str]): Filter by alarm names.
        * **tags** (list[str]): Filter by tag names.
        * **greater_than_timestamp** (datetime): Start time.
        * **less_than_timestamp** (datetime): End time.
        * **timezone** (str): Timezone.
        * **page** (int): Pagination page.
        * **limit** (int): Entries per page.

        **Returns:**

        * **list**: Filtered list of alarm summaries.
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
            limit=limit
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
    def create_record_on_alarm_summary(self, name:str, state:str, timestamp:datetime, ack_timestamp:datetime=None):
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
        
        if self.check_connectivity():
            
            AlarmSummary.create(name=name, state=state, timestamp=timestamp, ack_timestamp=ack_timestamp)

    @db_rollback
    def put_record_on_alarm_summary(self, name:str, state:str=None, ack_timestamp:datetime=None):
        r"""
        Updates the latest record in the Alarm Summary for a given alarm.

        **Parameters:**

        * **name** (str): Alarm name.
        * **state** (str, optional): New state.
        * **ack_timestamp** (datetime, optional): Acknowledgment timestamp.
        """
        if not self.check_connectivity():
            
            return None
        
        if not self.is_history_logged:

            return None
        
        fields = dict()
        alarm = AlarmSummary.read_by_name(name=name)

        if alarm:

            if ack_timestamp:
                fields["ack_time"] = ack_timestamp
            if state:
                alarm_state = AlarmStates.get_or_none(name=state)
                fields["state"] = alarm_state

            if fields:
                query = AlarmSummary.put(
                    id=alarm.id,
                    **fields
                )

                return query

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
        description:str
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
        
        return self.query(_query)
    
    def get_lasts(
        self,
        lasts:int=1
        ):
        r"""
        Thread-safe retrieval of last alarm events.
        """
        _query = dict()
        _query["action"] = "get_lasts"
        _query["parameters"] = dict()
        _query["parameters"]["lasts"] = lasts
        
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
        timezone:str='UTC',
        page:int=1,
        limit:int=20
        ):
        r"""
        Thread-safe filtering of alarm summary.
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
        
        return self.query(_query)
    
    def create_record_on_alarm_summary(self, name:str, state:str, timestamp:datetime, ack_timestamp:datetime=None):
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
        
        return self.query(_query)
    
    def put_record_on_alarm_summary(
        self,
        name:str,
        state:str=None,
        ack_timestamp:datetime=None
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
