# -*- coding: utf-8 -*-
"""pyhades/logger/events.py
"""
from datetime import datetime
from ..dbmodels.logs import Logs
from ..modules.users.users import User
from .core import BaseEngine, BaseLogger
from ..utils.decorators import db_rollback


class LogsLogger(BaseLogger):

    def __init__(self):

        super(LogsLogger, self).__init__()

    @db_rollback
    def create(
        self, 
        message:str, 
        user:User, 
        description:str=None, 
        classification:str=None,
        alarm_summary_id:int=None,
        event_id:int=None,
        timestamp:datetime=None
        ):
        r"""
        Documentation here
        """
        if not self.is_history_logged:

            return None
        
        if not self.check_connectivity():

            return list()
            
        query, message = Logs.create(
            message=message, 
            user=user, 
            description=description, 
            classification=classification,
            alarm_summary_id=alarm_summary_id,
            event_id=event_id,
            timestamp=timestamp
        )

        return query, message

    @db_rollback
    def get_lasts(self, lasts:int=1):
        r"""
        Documentation here
        """
        if not self.is_history_logged:

            return None
        
        if not self.check_connectivity():

            return list()
        
        return Logs.read_lasts(lasts=lasts)
        
    
    @db_rollback
    def filter_by(
        self,
        usernames:list[str]=None,
        alarm_names:list[str]=None,
        event_ids:list[int]=None,
        classification:str="",
        message:str="",
        description:str="",
        greater_than_timestamp:datetime=None,
        less_than_timestamp:datetime=None,
        timezone:str='UTC'
        ):
        r"""
        Documentation here
        """
        if not self.is_history_logged:

            return None
        
        if not self.check_connectivity():

            return list()
        
        return Logs.filter_by(
            usernames=usernames,
            alarm_names=alarm_names,
            event_ids=event_ids,
            message=message,
            description=description,
            classification=classification,
            greater_than_timestamp=greater_than_timestamp,
            less_than_timestamp=less_than_timestamp,
            timezone=timezone
        )

    @db_rollback  
    def get_summary(self)->tuple[list, str]:
        r"""
        Documentation here
        """
        if not self.is_history_logged:

            return None
        
        if not self.check_connectivity():
            
            return list()
            
        return Logs.serialize()
    
    
class LogsLoggerEngine(BaseEngine):
    r"""
    Operation Logs logger Engine class for Tag thread-safe database logging.

    """

    def __init__(self):

        super(LogsLoggerEngine, self).__init__()
        self.logger = LogsLogger()

    def create(
        self,
        message:str, 
        user:User, 
        description:str=None, 
        classification:str=None,
        alarm_summary_id:int=None,
        event_id:int=None,
        timestamp:datetime=None
        ):

        _query = dict()
        _query["action"] = "create"
        _query["parameters"] = dict()
        _query["parameters"]["message"] = message
        _query["parameters"]["user"] = user
        _query["parameters"]["description"] = description
        _query["parameters"]["classification"] = classification
        _query["parameters"]["alarm_summary_id"] = alarm_summary_id
        _query["parameters"]["event_id"] = event_id
        _query["parameters"]["timestamp"] = timestamp
        
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
    
    def filter_by(
        self,
        usernames:list[str]=None,
        alarm_names:list[str]=None,
        event_ids:list[int]=None,
        classification:str="",
        message:str="",
        description:str="",
        greater_than_timestamp:datetime=None,
        less_than_timestamp:datetime=None,
        timezone:str='UTC'
        ):

        _query = dict()
        _query["action"] = "filter_by"
        _query["parameters"] = dict()
        _query["parameters"]["usernames"] = usernames
        _query["parameters"]["alarm_names"] = alarm_names
        _query["parameters"]["event_ids"] = event_ids
        _query["parameters"]["classification"] = classification
        _query["parameters"]["message"] = message
        _query["parameters"]["description"] = description
        _query["parameters"]["greater_than_timestamp"] = greater_than_timestamp
        _query["parameters"]["less_than_timestamp"] = less_than_timestamp
        _query["parameters"]["timezone"] = timezone
        
        return self.query(_query)

    def get_summary(self):
        r"""
        Documentation here
        """
        _query = dict()
        _query["action"] = "get_summary"
        _query["parameters"] = dict()
        
        return self.query(_query)
    