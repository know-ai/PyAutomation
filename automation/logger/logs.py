# -*- coding: utf-8 -*-
"""automation/logger/logs.py

This module implements the Logs Logger, which tracks application-level logs,
often linking them to specific alarm summaries or events for audit trails.
"""
from datetime import datetime
from ..dbmodels.logs import Logs
from ..modules.users.users import User
from .core import BaseEngine, BaseLogger
from ..utils.decorators import db_rollback


class LogsLogger(BaseLogger):
    r"""
    Logger class specialized for Application Logs.

    This differs from EventsLogger in that it may link logs to specific Alarm occurrences (AlarmSummary) or Events.
    """

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
        timestamp:datetime=None,
        shift:str=None,
        area:str=None,
        handover:bool=False,
        ):
        r"""
        Creates a logbook entry. Always journals (DOMAIN.LOG, critical) even
        when the historian is down; remote write runs only if connected.
        """
        from ..persistence.outbox import journal_then_remote
        from ..persistence.records import JournaledEnvelope, PersistableRecord

        username = getattr(user, "username", None) or "system"
        record = PersistableRecord.log(
            message=message,
            username=username,
            user_name=username,
            description=description,
            classification=classification,
            alarm_summary_id=alarm_summary_id,
            event_id=event_id,
            timestamp=timestamp,
            shift=shift,
            area=area,
            handover=bool(handover),
        )

        def _write():
            return Logs.create(
                message=message,
                user=user,
                description=description,
                classification=classification,
                alarm_summary_id=alarm_summary_id,
                event_id=event_id,
                timestamp=timestamp,
                user_name=username,
                shift=shift,
                area=area,
                handover=bool(handover),
            )

        connected = bool(user) and self.check_connectivity()
        result, _ = journal_then_remote(record, _write, connected)
        try:
            from ..utils.audit_metrics import note_log_persisted

            note_log_persisted()
        except Exception:
            pass
        if result is not None and not (isinstance(result, tuple) and result[0] is None):
            return result
        return JournaledEnvelope(record.payload()), "journaled"

    @db_rollback
    def get_lasts(self, lasts:int=1, area:str=None):
        r"""
        Retrieves the last N logs.

        **Parameters:**

        * **lasts** (int): Count to retrieve.
        """
        if not self.is_history_logged:

            return None
        
        if not self.check_connectivity():

            return list()
        
        return Logs.read_lasts(lasts=lasts, area=area)
        
    
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
        timezone:str='UTC',
        page:int=1,
        limit:int=20,
        classifications:list[str]=None,
        search:str="",
        exclude_description:str="",
        area:str=None,
        ):
        r"""
        Filters logs by various criteria with pagination.

        **Parameters:**

        * **usernames** (list[str]): Filter by usernames.
        * **alarm_names** (list[str]): Filter by linked alarm names.
        * **event_ids** (list[int]): Filter by linked event IDs.
        * **classification** (str): Filter by classification.
        * **message** (str): Partial match message.
        * **greater_than_timestamp** (datetime): Start time.
        * **less_than_timestamp** (datetime): End time.
        * **timezone** (str): Timezone.
        * **page**, **limit**: Pagination control.
        """
        if not self.is_history_logged:

            return None
        
        if not self.check_connectivity():

            return {
                "data": [],
                "pagination": {
                    "page": page,
                    "limit": limit,
                    "total_records": 0,
                    "total_pages": 0,
                    "has_next": False,
                    "has_prev": False
                }
            }
        
        return Logs.filter_by(
            usernames=usernames,
            alarm_names=alarm_names,
            event_ids=event_ids,
            message=message,
            description=description,
            classification=classification,
            greater_than_timestamp=greater_than_timestamp,
            less_than_timestamp=less_than_timestamp,
            timezone=timezone,
            page=page,
            limit=limit,
            classifications=classifications,
            search=search,
            exclude_description=exclude_description,
            area=area,
        )

    @db_rollback  
    def get_summary(self)->tuple[list, str]:
        r"""
        Retrieves a summary of all logs.
        """
        if not self.is_history_logged:

            return None
        
        if not self.check_connectivity():
            
            return list()
            
        return Logs.serialize()
    
    
class LogsLoggerEngine(BaseEngine):
    r"""
    Thread-safe Engine for the LogsLogger.
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
        timestamp:datetime=None,
        shift:str=None,
        area:str=None,
        handover:bool=False,
        ):
        r"""
        Thread-safe log creation.
        """
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
        _query["parameters"]["shift"] = shift
        _query["parameters"]["area"] = area
        _query["parameters"]["handover"] = bool(handover)
        
        return self.query(_query)
    
    def get_lasts(self, lasts:int=1, area:str=None):
        r"""
        Thread-safe retrieval of last logs.
        """
        _query = dict()
        _query["action"] = "get_lasts"
        _query["parameters"] = dict()
        _query["parameters"]["lasts"] = lasts
        _query["parameters"]["area"] = area
        
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
        timezone:str='UTC',
        page:int=1,
        limit:int=20,
        classifications:list[str]=None,
        search:str="",
        exclude_description:str="",
        area:str=None,
        ):
        r"""
        Thread-safe log filtering with pagination.
        """
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
        _query["parameters"]["page"] = page
        _query["parameters"]["limit"] = limit
        _query["parameters"]["classifications"] = classifications
        _query["parameters"]["search"] = search
        _query["parameters"]["exclude_description"] = exclude_description
        _query["parameters"]["area"] = area
        
        return self.query(_query)

    def get_summary(self):
        r"""
        Thread-safe retrieval of log summary.
        """
        _query = dict()
        _query["action"] = "get_summary"
        _query["parameters"] = dict()
        
        return self.query(_query)
