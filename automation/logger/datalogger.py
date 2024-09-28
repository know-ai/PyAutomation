# -*- coding: utf-8 -*-
"""pyhades/logger/datalogger.py

This module implements a database logger for the CVT instance, 
will create a time-serie for each tag in a short memory data base.
"""
from ..dbmodels import (
    Tags, 
    TagValue, 
    AlarmTypes, 
    AlarmStates, 
    Variables, 
    Units,
    DataTypes,
    Alarms,
    AlarmSummary,
    Users,
    Roles,
    Events,
    OPCUA)
from datetime import datetime
from ..alarms.trigger import TriggerType
from ..alarms.states import AlarmState
import logging, sys, os
from automation.tags import CVTEngine
from ..variables import VARIABLES, DATATYPES
from automation.modules.users.users import User


class DataLogger:

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
        from ..managers.alarms import AlarmManager
        self._db = None
        self.tag_engine = CVTEngine()
        self.alarm_manager = AlarmManager()

    def set_db(self, db):
        r"""Documentation here
        """
        self._db = db

    def get_db(self):
        r"""
        Documentation here
        """
        return self._db
    
    def stop_db(self):
        r""""
        Documentation here
        """
        self._db = None

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
    
    def create_tables(self, tables):
        r"""
        Documentation here
        """
        if not self._db:
            
            return
        
        self._db.create_tables(tables, safe=True)
        self.__init_default_variables_schema()
        self.__init_default_datatypes_schema()
        self.__init_default_alarms_schema()

    def __init_default_variables_schema(self):
        r"""
        Documentation here
        """
        for variable, units in VARIABLES.items():
    
            if not Variables.name_exist(variable):
                
                Variables.create(name=variable)

            for name, unit in units.items():

                if not Units.name_exist(unit):

                    Units.create(name=name, unit=unit, variable=variable)

    def __init_default_datatypes_schema(self):
        r"""
        Documentation here
        """
        for datatype in DATATYPES:

            DataTypes.create(name=datatype["value"])

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

    def drop_tables(self, tables):
        r"""
        Documentation here
        """
        if not self._db:
            
            return

        self._db.drop_tables(tables, safe=True)

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

    # ALARMS METHODS
    def set_alarm(
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
        Alarms.create(
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
        return Alarms.read_all()
    
    def get_lasts_alarms(self, lasts:int=10):
        r"""
        Documentation here
        """
        return self.alarm_manager.get_lasts(lasts=lasts)
    
    def filter_alarms_by(self, **fields):
        r"""
        Documentation here
        """
        return self.alarm_manager.filter_by(**fields)
    
    def create_record_on_summary(self, name:str, state:str):
        r"""
        Documentation here
        """
        AlarmSummary.create(name=name, state=state)

    def get_alarm_summary(self):
        r"""
        Documentation here
        """
        return AlarmSummary.read_all()
    
    # EVENTS METHODS
    def create_event(
            self,
            message:str,
            user:User,
            description:str=None,
            classification:str=None,
            priority:int=None,
            criticity:int=None,
            timestamp:datetime=None):
        r"""
        Documentation here
        """
        Events.create(
            message=message,
            user=user,
            description=description,
            classification=classification,
            priority=priority,
            criticity=criticity,
            timestamp=timestamp
        )
    
    def get_lasts_events(self, lasts:int=10):
        r"""
        Documentation here
        """
        return self.event_manager.get_lasts(lasts=lasts)
    
    def filter_events_by(self, **fields):
        r"""
        Documentation here
        """
        return self.event_manager.filter_by(**fields)

    # ROLES METHODS
    def set_role(self, name:str, level:int, identifier:str):
        r"""
        Documentation here
        """
        return Roles.create(
            name=name,
            level=level,
            identifier=identifier
        )

    def put_role(self):
        r"""
        Documentation here
        """
        pass

    def delete_role(self):
        r"""
        Documentation here
        """
        pass

    # USERS METHODS
    def set_user(
            self, 
            user:User
        ):
        r"""
        Documentation here
        """
        return Users.create(
            user=user
        )

    def put_user(self):
        r"""
        Documentation here
        """
        pass

    def delete_user(self):
        r"""
        Documentation here
        """
        pass