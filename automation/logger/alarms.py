# -*- coding: utf-8 -*-
"""pyhades/logger/alarms.py
"""
from datetime import datetime
from ..dbmodels import Alarms, AlarmSummary, AlarmTypes, AlarmStates
from .core import BaseEngine, BaseLogger
from ..alarms.trigger import TriggerType
from ..alarms.states import AlarmState


class AlarmsLogger(BaseLogger):

    def __init__(self):

        super(AlarmsLogger, self).__init__()

    def create_tables(self, tables):
        r"""
        Documentation here
        """
        if not self._db:
            
            return
        
        self._db.create_tables(tables, safe=True)
        self.__init_default_alarms_schema()

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

    def create(
            self,
            id:str,
            name:str,
            tag:str,
            trigger_type:str,
            trigger_value:float,
            description:str,
            tag_alarm:str):
        r"""
        Documentation here
        """
        if self.get_db():

            query = Alarms.create(
                identifier=id,
                name=name,
                tag=tag,
                trigger_type=trigger_type,
                trigger_value=trigger_value,
                description=description,
                tag_alarm=tag_alarm
            )

    def get_alarms(self):
        r"""
        Documentation here
        """
        if self.get_db():
        
            alarms = Alarms.read_all()

            if alarms:

                return alarms
            
        return list()
    
    def get_alarm_by_name(self, name:str)->Alarms|None:
        r"""
        Documentation here
        """
        if self.get_db():
        
            return Alarms.read_by_name(name=name)
            
    def get_lasts(self, lasts:int=10):
        r"""
        Documentation here
        """
        if self.get_db():
        
            return AlarmSummary.read_lasts(lasts=lasts)
        
        return list()
    
    def filter_alarm_summary_by(
            self,
            states:list[str]=None,
            names:list[str]=None,
            tags:list[str]=None,
            greater_than_timestamp:datetime=None,
            less_than_timestamp:datetime=None
        ):
        r"""
        Documentation here
        """
        if self.get_db():
        
            return AlarmSummary.filter_by(
                states=states,
                names=names,
                tags=tags,
                greater_than_timestamp=greater_than_timestamp,
                less_than_timestamp=less_than_timestamp
            )
        
        return list()
    
    def put(
        self,
        id:str,
        name:str=None,
        tag:str=None,
        description:str=None,
        alarm_type:str=None,
        trigger_value:str=None
        ):
        fields = dict()
        alarm = Alarms.read_by_identifier(identifier=id)
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
        query = Alarms.put(
            id=alarm.id,
            **fields
        )

        return query

    def delete(self, id:str):
        r"""
        Documentation here
        """
        alarm =Alarms.read_by_identifier(identifier=id)
        Alarms.delete(id=alarm.id)

    def create_record_on_alarm_summary(self, name:str, state:str):
        r"""
        Documentation here
        """
        if self.get_db():
        
            AlarmSummary.create(name=name, state=state)

    def get_alarm_summary(self):
        r"""
        Documentation here
        """
        if self.get_db():
        
            return AlarmSummary.read_all()
        
        return list()
    
    
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
        description:str,
        tag_alarm:str
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
        _query["parameters"]["tag_alarm"] = tag_alarm
        
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
        usernames:list[str]=None,
        priorities:list[int]=None,
        criticities:list[int]=None,
        greater_than_timestamp:datetime=None,
        less_than_timestamp:datetime=None
        ):

        _query = dict()
        _query["action"] = "filter_alarm_summary_by"
        _query["parameters"] = dict()
        _query["parameters"]["usernames"] = usernames
        _query["parameters"]["priorities"] = priorities
        _query["parameters"]["criticities"] = criticities
        _query["parameters"]["greater_than_timestamp"] = greater_than_timestamp
        _query["parameters"]["less_than_timestamp"] = less_than_timestamp
        
        return self.query(_query)
    
    def create_record_on_alarm_summary(self, name:str, state:str):

        _query = dict()
        _query["action"] = "create_record_on_alarm_summary"
        _query["parameters"] = dict()
        _query["parameters"]["name"] = name
        _query["parameters"]["state"] = state
        
        return self.query(_query)

    def put(
        self,
        id:str,
        name:str=None,
        tag:str=None,
        description:str=None,
        alarm_type:str=None,
        trigger_value:str=None
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