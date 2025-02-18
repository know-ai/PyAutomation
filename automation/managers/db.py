# -*- coding: utf-8 -*-
"""pyhades/managers/logger.py

This module implements Logger Manager.
"""
import logging, queue
from ..singleton import Singleton
from ..logger.datalogger import DataLoggerEngine
from ..logger.logdict import  LogTable
from ..logger.alarms import AlarmsLoggerEngine
from ..logger.events import EventsLoggerEngine
from ..logger.users import UsersLoggerEngine
from ..logger.logs import LogsLoggerEngine
from ..logger.machines import MachinesLoggerEngine
from ..logger.opcua_server import OPCUAServerLoggerEngine
from ..tags import CVTEngine, TagObserver
from ..modules.users.users import User
from ..utils.decorators import logging_error_handler
from ..dbmodels import (
    Manufacturer,
    Segment,
    Tags, 
    TagValue, 
    AlarmTypes,
    AlarmStates, 
    Alarms,  
    AlarmSummary, 
    Variables, 
    Units, 
    DataTypes,
    OPCUA,
    Users,
    Roles,
    Events,
    Logs,
    Machines,
    TagsMachines,
    AccessType,
    OPCUAServer,
    BaseModel
)


class DBManager(Singleton):
    r"""
    Database Manager class for database logging settings.
    """

    def __init__(self, period:float=1.0, delay:float=1.0, drop_tables:bool=False):

        self._period = period
        self._delay = delay
        self._drop_tables = drop_tables
        self._tag_queue = queue.Queue()
        self.engine = CVTEngine()
        self._logging_tags = LogTable()
        self._logger = DataLoggerEngine()
        self.alarms_logger = AlarmsLoggerEngine()
        self.events_logger = EventsLoggerEngine()
        self.users_logger = UsersLoggerEngine()
        self.logs_logger = LogsLoggerEngine()
        self.machines_logger = MachinesLoggerEngine()
        self.opcuaserver_logger = OPCUAServerLoggerEngine()
        self._tables = [
            Manufacturer,
            Segment,
            Variables, 
            Units, 
            DataTypes, 
            Tags, 
            TagValue, 
            AlarmTypes,
            AlarmStates,
            Alarms,
            AlarmSummary,
            OPCUA,
            Roles,
            Users,
            Events,
            Logs,
            Machines,
            TagsMachines,
            AccessType,
            OPCUAServer
        ]

        self._extra_tables = []
        
    def get_queue(self)->queue.Queue:
        r"""
        Documentation here
        """
        return self._tag_queue

    def set_db(self, db, is_history_logged:bool=False):
        r"""
        Initialize a new DB Object SQLite - Postgres - MySQL

        **Parameters**

        * **db** (db object): Sqlite - Postgres or MySql db object

        **Returns** `None`
        """
        self._logger.set_db(db)
        self._logger.logger.set_is_history_logged(value=is_history_logged)
        self.alarms_logger.set_db(db)
        self.alarms_logger.logger.set_is_history_logged(value=is_history_logged)
        self.events_logger.set_db(db)
        self.events_logger.logger.set_is_history_logged(value=is_history_logged)
        self.users_logger.set_db(db)
        self.logs_logger.set_db(db)
        self.logs_logger.logger.set_is_history_logged(value=is_history_logged)
        self.machines_logger.set_db(db)
        self.opcuaserver_logger.logger.set_db(db)
        
    def get_db(self):
        r"""
        Returns a DB object
        """
        return self._logger.get_db()

    def set_dropped(self, drop_tables:bool):
        r"""
        Allows to you set a flag variable to drop database tables when run app.

        **Parameters**

        * **drop_tables** (bool) If True, drop all tables define in the app an initialized it in blank.

        **Returns**

        * **None**
        """
        self._drop_tables = drop_tables

    def get_dropped(self)->bool:
        r"""
        Gets flag variables to drop tables when initialize the app

        **Return**

        * **drop_tables** (bool) Flag variables to drop table
        """
        return self._drop_tables

    def register_table(self, cls:BaseModel):
        r"""
        Allows to you register a new database model

        **Parameters**

        * **cls* (BaseModel): A class that inherit from BaseModel

        """
        self._tables.append(cls)

    def get_db_table(self, tablename:str):
        r"""
        Documentation here
        """
        for table in self._tables:

            if table._meta.table_name.lower()==tablename.lower():

                return table
            
        return None

    def create_tables(self):
        r"""
        Creates default tables and tables registered with method *register_table*
        """
        self._tables.extend(self._extra_tables)
        self._logger.create_tables(self._tables)
        self.alarms_logger.create_tables(self._tables)

    def drop_tables(self):
        r"""
        Drop all tables defined
        """
        tables = self._tables
        
        self._logger.drop_tables(tables)

    def clear_default_tables(self):
        r"""
        If you want initialize any PyHades app without default tables, you can use this method
        """
        self._tables = []

    def get_tags(self)->dict:
        r"""
        Gets all tag defined in tag's repository
        """
        return self._logger.get_tags()
    
    def get_alarms(self)->dict:
        r"""
        Gets all tag defined in tag's repository
        """

        return self.alarms_logger.get_alarms()

    @logging_error_handler
    def set_tag(
        self, 
        tag:str, 
        unit:str, 
        data_type:str, 
        description:str,
        display_name:str="", 
        min_value:float=None, 
        max_value:float=None, 
        tcp_source_address:str=None, 
        node_namespace:str=None):
        r"""
        Sets tag to Database

        **Parameters**

        * **tag** (str):
        * **unit** (str):
        * **data_type** (str):
        * **description** (str):
        * **min_value** (float)[Optional]:
        * **max_value** (float)[Optional]:
        * **tcp_source_address** (str)[Optional]:
        * **node_namespace** (str)[Optional]:
        """
        self._logger.set_tag(
            tag=tag,  
            unit=unit,
            data_type=data_type,
            description=description,
            display_name=display_name,
            min_value=min_value,
            max_value=max_value,
            tcp_source_address=tcp_source_address,
            node_namespace=node_namespace
        )

    def set_tags(self):
        r"""
        Allows to you define all tags added with *add_tag* method
        """
        for period in self._logging_tags.get_groups():
            
            tags = self._logging_tags.get_tags(period)
        
            for tag, unit, data_type, description, display_name, min_value, max_value, tcp_source_address, node_namespace in tags:

                self.set_tag(
                    tag=tag,
                    unit=unit, 
                    data_type=data_type, 
                    description=description, 
                    display_name=display_name,
                    min_value=min_value, 
                    max_value=max_value, 
                    tcp_source_address=tcp_source_address, 
                    node_namespace=node_namespace)

    def init_database(self):
        r"""
        Initializes all databases.
        """
        if self.get_dropped():
            try:
                self.drop_tables()
            except Exception as e:
                error = str(e)
                logger = logging.getLogger("pyautomation")
                logger.error("Database:{}".format(error))
        
        self.create_tables()

    def stop_database(self):
        r"""
        Documentation here
        """
        self._logger.stop_db()

    def get_opcua_clients(self):
        r"""
        Documentation here
        """
        return OPCUA.read_all()

    # USERS METHODS
    def set_role(self, name:str, level:int, identifier:str):
        r"""
        Documentation here
        """
        return self.users_logger.set_role(name=name, level=level, identifier=identifier)

    def set_user(self, user:User):
        r"""
        Documentation here
        """
        return self.users_logger.set_user(user=user)
    
    def login(self, password:str, username:str="", email:str=""):
        r"""
        Documentation here
        """
        return self.users_logger.login(password=password, username=username, email=email)

    def summary(self)->dict:
        r"""
        Get database manager summary

        **Returns**

        * **summary** (dict): Database summary
        """
        result = dict()

        result["period"] = self.get_period()
        result["tags"] = self.get_tags()
        result["delay"] = self.get_delay()

        return result
    
    def attach(self, tag_name:str):

        observer = TagObserver(self._tag_queue)
        self.engine.attach(name=tag_name, observer=observer)
