# -*- coding: utf-8 -*-
"""pyhades/logger/events.py
"""
import threading, logging
from datetime import datetime
from ..dbmodels import Events
from ..singleton import Singleton
from ..modules.users.users import User
from .logger import DataLoggerEngine
logger_engine = DataLoggerEngine()


class EventsLogger:

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
        
        if logger_engine.get_db():
            
            Events.create(
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

        return Events.read_lasts(lasts=lasts)
    
    def filter_by(
        self,
        usernames:list[str]=None,
        priorities:list[int]=None,
        criticities:list[int]=None,
        greater_than_timestamp:datetime=None,
        less_than_timestamp:datetime=None
        ):
        r"""
        Documentation here
        """

        return Events.filter_by(
            usernames=usernames,
            priorities=priorities,
            criticities=criticities,
            greater_than_timestamp=greater_than_timestamp,
            less_than_timestamp=less_than_timestamp
        )
        
    def get_summary(self)->list:
        r"""
        Documentation here
        """
        if logger_engine.get_db():
            
            return Events.serialize()
        
        return []
    
class EventsLoggerEngine(Singleton):
    r"""
    Data logger Engine class for Tag thread-safe database logging.

    """

    def __init__(self):

        super(EventsLoggerEngine, self).__init__()

        self.logger = EventsLogger()
        self._request_lock = threading.Lock()
        self._response_lock = threading.Lock()
        self._response = None
        self._response_lock.acquire()

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
        
        return self.__query(_query)
    
    def get_lasts(
        self,
        lasts:int=1
        ):

        _query = dict()
        _query["action"] = "get_lasts"
        _query["parameters"] = dict()
        _query["parameters"]["lasts"] = lasts
        
        return self.__query(_query)
    
    def filter_by(
        self,
        usernames:list[str]=None,
        priorities:list[int]=None,
        criticities:list[int]=None,
        greater_than_timestamp:datetime=None,
        less_than_timestamp:datetime=None
        ):

        _query = dict()
        _query["action"] = "filter_by"
        _query["parameters"] = dict()
        _query["parameters"]["usernames"] = usernames
        _query["parameters"]["priorities"] = priorities
        _query["parameters"]["criticities"] = criticities
        _query["parameters"]["greater_than_timestamp"] = greater_than_timestamp
        _query["parameters"]["less_than_timestamp"] = less_than_timestamp
        
        return self.__query(_query)

    def get_summary(self):
        r"""
        Documentation here
        """
        _query = dict()
        _query["action"] = "get_summary"
        _query["parameters"] = dict()
        
        return self.__query(_query)

    def __query(self, query:dict)->dict:
        r"""
        Documentation here
        """
        self.request(query)
        result = self.response()
        if result["result"]:
            return result["response"]

    def request(self, query:dict):
        r"""Documentation here

        # Parameters

        - 

        # Returns

        - 
        """
        self._request_lock.acquire()
        action = query["action"]
        error_msg = f"Error in EventLoggerEngine: {action}"

        try:

            if hasattr(self.logger, action):

                method = getattr(self.logger, action)
                
                if 'parameters' in query:
                    
                    resp = method(**query["parameters"])
                
                else:

                    resp = method()

            self.__true_response(resp)

        except Exception as e:

            self.__log_error(e, error_msg)

        self._response_lock.release()

    def __log_error(self, e:Exception, msg:str):
        r"""
        Documentation here
        """
        logging.error(f"{e} Message: {msg}")
        self._response = {
            "result": False,
            "response": None
        }

    def response(self):
        r"""Documentation here

        # Parameters

        - 

        # Returns

        - 
        """
        self._response_lock.acquire()

        result = self._response

        self._request_lock.release()

        return result
    
    def __true_response(self, resp):
        r"""
        Documentation here
        """
        self._response = {
            "result": True,
            "response": resp
        }

    def __getstate__(self):

        self._response_lock.release()
        state = self.__dict__.copy()
        del state['_request_lock']
        del state['_response_lock']
        return state

    def __setstate__(self, state):
        
        self.__dict__.update(state)
        self._request_lock = threading.Lock()
        self._response_lock = threading.Lock()

        self._response_lock.acquire()
