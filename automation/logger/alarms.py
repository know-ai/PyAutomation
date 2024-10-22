# -*- coding: utf-8 -*-
"""pyhades/logger/alarms.py
"""
from datetime import datetime
from ..dbmodels import Alarms, AlarmSummary, AlarmTypes, AlarmStates
from .core import BaseEngine, BaseLogger
from ..alarms.trigger import TriggerType
from ..alarms.states import AlarmState
from ..utils.decorators import db_rollback


class AlarmsLogger(BaseLogger):

    def __init__(self):

        super(AlarmsLogger, self).__init__()

    @db_rollback
    def create_tables(self, tables):
        r"""
        Documentation here
        """
        if not self._db:
            
            return
        
        self._db.create_tables(tables, safe=True)
        self.__init_default_alarms_schema()

    @db_rollback
    def __init_default_alarms_schema(self):
        r"""
        Documentation here
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
        Documentation here
        """
        if not self._db:
            
            return

        query = Alarms.create(
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
        Documentation here
        """
        if not self._db:
            
            return list()
        
        alarms = Alarms.read_all()

        if alarms:

            return alarms
    
    @db_rollback
    def get_alarm_by_name(self, name:str)->Alarms|None:
        r"""
        Documentation here
        """
        if not self._db:
            
            return None
        
        return Alarms.read_by_name(name=name)

    @db_rollback        
    def get_lasts(self, lasts:int=10):
        r"""
        Documentation here
        """
        if not self.is_history_logged:

            return None
        
        if not self._db:
            
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
            timezone:str="UTC"
        ):
        r"""
        Documentation here
        """
        if not self.is_history_logged:

            return None
        
        if not self._db:
            
            return list()
        
        return AlarmSummary.filter_by(
            states=states,
            names=names,
            tags=tags,
            greater_than_timestamp=greater_than_timestamp,
            less_than_timestamp=less_than_timestamp,
            timezone=timezone
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
        if not self._db:
            
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
        Documentation here
        """
        if not self._db:
            
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
        Documentation here
        """
        if not self.is_history_logged:

            return None
        
        if self.get_db():
            
            AlarmSummary.create(name=name, state=state, timestamp=timestamp, ack_timestamp=ack_timestamp)

    @db_rollback
    def put_record_on_alarm_summary(self, name:str, state:str=None, ack_timestamp:datetime=None):
        r"""
        Documentation here
        """
        if not self._db:
            
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
    def get_alarm_summary(self):
        r"""
        Documentation here
        """
        if not self.is_history_logged:

            return None
        
        if not self._db:
            
            return list()
        
        return AlarmSummary.read_all()
    
    
class AlarmsLoggerEngine(BaseEngine):
    r"""
    Alarms logger Engine class for Tag thread-safe database logging.

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

        _query = dict()
        _query["action"] = "get_lasts"
        _query["parameters"] = dict()
        _query["parameters"]["lasts"] = lasts
        
        return self.query(_query)
    
    def get_alarms(self):

        _query = dict()
        _query["action"] = "get_alarms"
        _query["parameters"] = dict()
        
        return self.query(_query)
    
    def get_alarm_by_name(self, name:str):

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
        timezone:str='UTC'
        ):

        _query = dict()
        _query["action"] = "filter_alarm_summary_by"
        _query["parameters"] = dict()
        _query["parameters"]["names"] = names
        _query["parameters"]["states"] = states
        _query["parameters"]["tags"] = tags
        _query["parameters"]["greater_than_timestamp"] = greater_than_timestamp
        _query["parameters"]["less_than_timestamp"] = less_than_timestamp
        _query["parameters"]["timezone"] = timezone
        
        return self.query(_query)
    
    def create_record_on_alarm_summary(self, name:str, state:str, timestamp:datetime, ack_timestamp:datetime=None):

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
        Documentation here
        """
        _query = dict()
        _query["action"] = "delete"
        _query["parameters"] = dict()
        _query["parameters"]["id"] = id
        return self.query(_query)

    def get_alarm_summary(self):
        r"""
        Documentation here
        """
        _query = dict()
        _query["action"] = "get_alarm_summary"
        _query["parameters"] = dict()
        
        return self.query(_query)

    def create_tables(self, tables):
        r"""
        Create default PyHades database tables

        ['TagTrend', 'TagValue']

        **Parameters**

        * **tables** (list) list of database model

        **Returns** `None`
        """
        self.logger.create_tables(tables)