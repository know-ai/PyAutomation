# -*- coding: utf-8 -*-
"""automation/managers/logger.py

This module implements the Database Manager (DBManager), which orchestrates database interactions,
table registration, and logging engines for various system components.
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
    Central manager for database operations and historical data logging.

    It manages the connection to the database (SQLite, PostgreSQL, MySQL), registers database models,
    and initializes specific logging engines for Alarms, Events, Users, etc.
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
        
    @logging_error_handler
    def get_queue(self)->queue.Queue:
        r"""
        Retrieves the internal queue used for tag updates.
        """
        return self._tag_queue

    @logging_error_handler
    def set_db(self, db, is_history_logged:bool=False):
        r"""
        Configures the database connection for all logging engines.

        **Parameters:**

        * **db** (Database): The Peewee database instance (SqliteDatabase, PostgresqlDatabase, MySQLDatabase).
        * **is_history_logged** (bool, optional): Enables or disables historical data logging.
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
        
    @logging_error_handler
    def get_db(self):
        r"""
        Retrieves the current database connection object.
        """
        return self._logger.get_db()

    @logging_error_handler
    def set_dropped(self, drop_tables:bool):
        r"""
        Sets the flag to drop tables on initialization.

        **Parameters:**

        * **drop_tables** (bool): If True, tables will be dropped and recreated on startup.
        """
        self._drop_tables = drop_tables

    @logging_error_handler
    def get_dropped(self)->bool:
        r"""
        Gets the drop tables flag status.
        """
        return self._drop_tables

    @logging_error_handler
    def register_table(self, cls:BaseModel):
        r"""
        Registers a new database model (table) to be managed by the system.

        **Parameters:**

        * **cls** (BaseModel): A class inheriting from `BaseModel`.
        """
        self._tables.append(cls)

    @logging_error_handler
    def get_db_table(self, tablename:str):
        r"""
        Retrieves a registered table model by its table name.

        **Parameters:**

        * **tablename** (str): The name of the table in the database.

        **Returns:**

        * **Model**: The Peewee model class if found, else None.
        """
        for table in self._tables:

            if table._meta.table_name.lower()==tablename.lower():

                return table
            
        return None

    @logging_error_handler
    def create_tables(self):
        r"""
        Creates all registered tables in the database.
        """
        self._tables.extend(self._extra_tables)
        self._logger.create_tables(self._tables)
        self.alarms_logger.create_tables(self._tables)

    @logging_error_handler
    def drop_tables(self):
        r"""
        Drops all registered tables from the database.
        """
        tables = self._tables
        
        self._logger.drop_tables(tables)

    @logging_error_handler
    def clear_default_tables(self):
        r"""
        Clears the list of default tables. Useful for custom applications that don't need the standard schema.
        """
        self._tables = []

    @logging_error_handler
    def get_tags(self)->dict:
        r"""
        Retrieves all tags configured in the database logger.
        """
        return self._logger.get_tags()
    
    @logging_error_handler
    def get_alarms(self)->dict:
        r"""
        Retrieves all alarms from the alarm logger.
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
        Registers a tag in the database logger configuration.

        **Parameters:**

        * **tag** (str): Tag name.
        * **unit** (str): Tag unit.
        * **data_type** (str): Data type (float, int, bool).
        * **description** (str): Description.
        * **tcp_source_address** (str, optional): OPC UA server address.
        * **node_namespace** (str, optional): OPC UA Node ID.
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

    @logging_error_handler
    def set_tags(self):
        r"""
        Applies all staged tags from the LogTable to the database logger.
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

    @logging_error_handler
    def init_database(self):
        r"""
        Initializes the database schema. Drops tables if configured, then creates them.
        """
        if self.get_dropped():
            try:
                self.drop_tables()
            except Exception as e:
                error = str(e)
                logger = logging.getLogger("pyautomation")
                logger.error("Database:{}".format(error))
        
        self.create_tables()

    @logging_error_handler
    def stop_database(self):
        r"""
        Closes the database connection.
        """
        self._logger.stop_db()

    @logging_error_handler
    def get_opcua_clients(self):
        r"""
        Retrieves all OPC UA client configurations from the database.
        """
        return OPCUA.read_all()

    # USERS METHODS
    @logging_error_handler
    def set_role(self, name:str, level:int, identifier:str):
        r"""
        Creates a new user role in the database.
        """
        return self.users_logger.set_role(name=name, level=level, identifier=identifier)

    @logging_error_handler
    def set_user(self, user:User):
        r"""
        Creates a new user in the database.
        """
        return self.users_logger.set_user(user=user)
    
    @logging_error_handler
    def login(self, password:str, username:str="", email:str=""):
        r"""
        Authenticates a user against the database.
        """
        return self.users_logger.login(password=password, username=username, email=email)
    
    @logging_error_handler
    def update_password(self, username:str, new_password:str):
        r"""
        Updates a user's password in the database.
        """
        return self.users_logger.update_password(username=username, new_password=new_password)
    
    @logging_error_handler
    def update_role(self, username:str, new_role_name:str):
        r"""
        Updates a user's role in the database.
        """
        return self.users_logger.update_role(username=username, new_role_name=new_role_name)

    @logging_error_handler
    def summary(self)->dict:
        r"""
        Generates a summary of the database manager configuration.

        **Returns:**

        * **dict**: Summary including period, configured tags, and delay.
        """
        result = dict()

        result["period"] = self._period
        result["tags"] = self.get_tags()
        result["delay"] = self._delay

        return result
    
    @logging_error_handler
    def attach(self, tag_name:str):
        r"""
        Attaches an observer to a tag for database logging purposes.
        """
        observer = TagObserver(self._tag_queue)
        self.engine.attach(name=tag_name, observer=observer)
