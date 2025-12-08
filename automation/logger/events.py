# -*- coding: utf-8 -*-
"""pyhades/logger/events.py
"""
from datetime import datetime
from ..dbmodels.events import Events
from ..modules.users.users import User
from .core import BaseEngine, BaseLogger


class EventsLogger(BaseLogger):

    def __init__(self):

        super(EventsLogger, self).__init__()

    def create(
        self, 
        message:str, 
        user:User, 
        description:str=None, 
        classification:str=None,
        priority:int=None,
        criticity:int=None,
        timestamp:datetime=None
        ):
        r"""
        Documentation here
        """
        if not self.is_history_logged:

            return None
        
        if not self.check_connectivity():
            
            return None
            
        return Events.create(
            message=message, 
            user=user, 
            description=description, 
            classification=classification,
            priority=priority,
            criticity=criticity,
            timestamp=timestamp
        )

    def get_lasts(self, lasts:int=1):
        r"""
        Documentation here
        """
        if not self.is_history_logged:

            return list()
        
        if not self.check_connectivity():
            
            return list()
        
        return Events.read_lasts(lasts=lasts)
    
    def filter_by(
        self,
        usernames:list[str]=None,
        priorities:list[int]=None,
        criticities:list[int]=None,
        message:str="",
        description:str="",
        classification:str="",
        greater_than_timestamp:datetime=None,
        less_than_timestamp:datetime=None,
        timezone:str="UTC",
        page:int=1,
        limit:int=20
        ):
        r"""
        Documentation here
        """
        if not self.is_history_logged:

            return None
        
        if not self.check_connectivity():
            
            return list()
        
        return Events.filter_by(
            usernames=usernames,
            priorities=priorities,
            criticities=criticities,
            message=message,
            classification=classification,
            description=description,
            greater_than_timestamp=greater_than_timestamp,
            less_than_timestamp=less_than_timestamp,
            timezone=timezone,
            page=page,
            limit=limit
            )

    def get_summary(self)->tuple[list, str]:
        r"""
        Documentation here
        """
        if not self.is_history_logged:

            return None
        
        if not self.check_connectivity():
            
            return list()
            
        return Events.serialize()
    
class EventsLoggerEngine(BaseEngine):
    r"""
    Data logger Engine class for Tag thread-safe database logging.

    """

    def __init__(self):

        super(EventsLoggerEngine, self).__init__()
        self.logger = EventsLogger()

    def create(
        self,
        message:str, 
        user:User, 
        description:str=None, 
        classification:str=None,
        priority:int=None,
        criticity:int=None,
        timestamp:datetime=None
        ):

        _query = dict()
        _query["action"] = "create"
        _query["parameters"] = dict()
        _query["parameters"]["message"] = message
        _query["parameters"]["user"] = user
        _query["parameters"]["description"] = description
        _query["parameters"]["classification"] = classification
        _query["parameters"]["priority"] = priority
        _query["parameters"]["criticity"] = criticity
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
        priorities:list[int]=None,
        criticities:list[int]=None,
        message:str="",
        classification:str="",
        description:str="",
        greater_than_timestamp:datetime=None,
        less_than_timestamp:datetime=None,
        timezone:str='UTC',
        page:int=1,
        limit:int=20
        ):

        _query = dict()
        _query["action"] = "filter_by"
        _query["parameters"] = dict()
        _query["parameters"]["usernames"] = usernames
        _query["parameters"]["priorities"] = priorities
        _query["parameters"]["criticities"] = criticities
        _query["parameters"]["message"] = message
        _query["parameters"]["classification"] = classification
        _query["parameters"]["description"] = description
        _query["parameters"]["greater_than_timestamp"] = greater_than_timestamp
        _query["parameters"]["less_than_timestamp"] = less_than_timestamp
        _query["parameters"]["timezone"] = timezone
        _query["parameters"]["page"] = page
        _query["parameters"]["limit"] = limit
        
        return self.query(_query)

    def get_summary(self):
        r"""
        Documentation here
        """
        _query = dict()
        _query["action"] = "get_summary"
        _query["parameters"] = dict()
        
        return self.query(_query)
    