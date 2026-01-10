import sys, logging, json, os, jwt, requests, urllib3, secrets
from logging.handlers import RotatingFileHandler
from math import ceil
from datetime import datetime, timezone
# DRIVERS IMPORTATION
from peewee import SqliteDatabase, MySQLDatabase, PostgresqlDatabase
from peewee import OperationalError, DatabaseError, InterfaceError
# from peewee_migrations import Router
from .dbmodels.users import Roles, Users
from .dbmodels.machines import Machines
# PYAUTOMATION MODULES IMPORTATION
from .singleton import Singleton
from .workers import LoggerWorker
from .managers import DBManager, OPCUAClientManager, AlarmManager
from .opcua.models import Client
from .tags import CVTEngine, Tag
from .logger.datalogger import DataLoggerEngine
from .logger.events import EventsLoggerEngine
from .logger.alarms import AlarmsLoggerEngine
from .logger.logs import LogsLoggerEngine
from .logger.machines import MachinesLoggerEngine
from .logger.opcua_server import OPCUAServerLoggerEngine
from .alarms import Alarm
from .state_machine import Machine, DAQ, AutomationStateMachine, StateMachine
from .opcua.subscription import DAS
from .buffer import Buffer
from .models import StringType, FloatType
from .modules.users.users import users, User
from .modules.users.roles import roles, Role
from .dbmodels.core import BaseModel
from .utils.decorators import validate_types, logging_error_handler
from .utils import _colorize_message
from flask_socketio import SocketIO
from geventwebsocket.handler import WebSocketHandler
from .variables import VARIABLES
from flask import Flask
# DASH APP CONFIGURATION PAGES IMPORTATION
# from .pages.main import ConfigView
# from .pages.callbacks import init_callbacks
# import dash_bootstrap_components as dbc


class PyAutomation(Singleton):
    r"""
    Automation is a `singleton <https://en.wikipedia.org/wiki/Singleton_pattern>`_ class designed to develop multi-threaded web applications for Industrial Applications.

    You can initialize and run PyAutomation Framework in different ways depending on your requirements.

    **Example 1**: Using only PyAutomation Framework

    ```python
    from automation import PyAutomation
    app = PyAutomation(certfile=certfile, keyfile=keyfile)
    app.run(debug=True, create_tables=True)

    ```

    **Example 2**: Extending PyAutomation Framework with Flask Application

    ```python
    from automation import PyAutomation
    from app import CreateApp
    application = CreateApp()
    server = application()  # Flask App
    app = PyAutomation(certfile=certfile, keyfile=keyfile)
    app.run(create_tables=True)

    ```

"""

    PORTS = 65535
    

    def __init__(self):
        
        # Initial setup (first time initialization)
        self.machine = Machine()
        self.machine_manager = self.machine.get_state_machine_manager()
        self.is_starting = True
        self.cvt = CVTEngine()
        self.logger_engine = DataLoggerEngine()
        self.events_engine = EventsLoggerEngine()
        self.alarms_engine = AlarmsLoggerEngine()
        self.logs_engine = LogsLoggerEngine()
        self.machines_engine = MachinesLoggerEngine()
        self.opcua_server_engine = OPCUAServerLoggerEngine()
        self.db_manager = DBManager()
        self.opcua_client_manager = OPCUAClientManager()
        self.alarm_manager = AlarmManager()
        self.workers = list()
        self.das = DAS()
        self.sio = None
        self.server = None
        folder_path = os.path.join(".", "logs")

        if not os.path.exists(folder_path):
            
            os.makedirs(folder_path)

        folder_db = os.path.join(".", "db")

        if not os.path.exists(folder_db):
            
            os.makedirs(folder_db)

        folder_db_backups = os.path.join(".", "db", "backups")

        if not os.path.exists(folder_db_backups):
            
            os.makedirs(folder_db_backups)

        folder_ssl = os.path.join(".", "ssl")

        if not os.path.exists(folder_ssl):
            
            os.makedirs(folder_ssl)

        self.set_log(file=os.path.join(folder_path, "app.log") ,level=logging.WARNING)
        self.__log_histories = False

    @logging_error_handler
    def ensure_db_config_from_env(self) -> None:
        r"""
        Bootstrap database configuration from environment variables if no
        ``db/db_config.json`` is present yet.

        This is intended for the very first startup of the application:

        - If ``db/db_config.json`` already exists, it is considered the
          single source of truth and **environment variables are ignored**.
        - If it does not exist and the appropriate ``AUTOMATION_DB_*`` env
          variables are defined, a new configuration file is written and will
          be used for all subsequent connections.

        Supported environment variables:

        - ``AUTOMATION_DB_TYPE``: ``sqlite`` (default), ``postgresql`` or ``mysql``.
        - For SQLite:
          - ``AUTOMATION_DB_FILE``: database filename (default: ``app.db``).
        - For PostgreSQL/MySQL:
          - ``AUTOMATION_DB_HOST`` (default: ``127.0.0.1``)
          - ``AUTOMATION_DB_PORT`` (default: ``5432`` for PostgreSQL, ``3306`` for MySQL)
          - ``AUTOMATION_DB_USER`` (required)
          - ``AUTOMATION_DB_PASSWORD`` (required)
          - ``AUTOMATION_DB_NAME`` (required)
        """
        # If there is already a persisted config, it is the source of truth.
        existing_config = self.get_db_config()
        if existing_config:
            return

        dbtype = os.environ.get("AUTOMATION_DB_TYPE", "sqlite").lower()

        if dbtype == "sqlite":
            dbfile = os.environ.get("AUTOMATION_DB_FILE", "app.db")
            logging.info(f"Bootstrapping SQLite DB config from env: file={dbfile}")
            self.set_db_config(dbtype="sqlite", dbfile=dbfile)
            return

        if dbtype in ("postgresql", "mysql"):
            user = os.environ.get("AUTOMATION_DB_USER")
            password = os.environ.get("AUTOMATION_DB_PASSWORD")
            host = os.environ.get("AUTOMATION_DB_HOST", "127.0.0.1")
            port = os.environ.get("AUTOMATION_DB_PORT")
            name = os.environ.get("AUTOMATION_DB_NAME")

            if not user or not password or not name:
                logging.warning(
                    "AUTOMATION_DB_USER, AUTOMATION_DB_PASSWORD and "
                    "AUTOMATION_DB_NAME must be set to bootstrap DB config "
                    f"for type '{dbtype}'. Skipping env-based DB bootstrap."
                )
                return

            if not port:
                port = "5432" if dbtype == "postgresql" else "3306"

            logging.info(
                f"Bootstrapping {dbtype} DB config from env: host={host}, "
                f"port={port}, name={name}, user={user}"
            )

            self.set_db_config(
                dbtype=dbtype,
                user=user,
                password=password,
                host=host,
                port=port,
                name=name,
            )
            return

        logging.warning(
            f"Unsupported AUTMATION_DB_TYPE '{dbtype}' for env-based DB bootstrap. "
            "Supported types are: sqlite, postgresql, mysql."
        )
    
    @logging_error_handler
    def define_socketio(self, server:Flask, certfile:str=None, keyfile:str=None)->None:
        r"""
        Initializes and configures the Socket.IO server integrated within PyAutomation.

        **Parameters:**
        
        * **certfile** (str, optional): Path to the SSL certificate file.
        * **keyfile** (str, optional): Path to the SSL key file.

        This method sets up the Socket.IO server, configures callbacks, and initializes the Socket.IO server 
        for real-time communication.
        """
        str_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(_colorize_message(f"[{str_date}] [INFO] Defining Socket.IO server with certfile: {certfile} and keyfile: {keyfile}", "INFO"))
        self.server = server
        if certfile and keyfile:

            self.sio = SocketIO(
                self.server, 
                cors_allowed_origins='*', 
                ping_timeout=10, 
                ping_interval=10, 
                async_mode='gevent', 
                ssl_context=(certfile, keyfile), 
                handler_class=WebSocketHandler
            )
        
        else:
            self.sio = SocketIO(self.server, cors_allowed_origins='*', ping_timeout=10, ping_interval=10, async_mode='gevent', handler_class=WebSocketHandler)

        self.cvt._cvt.set_socketio(sio=self.sio)

        @self.sio.on('connect')
        def handle_connect(auth=None):

            payload= {
                "tags": self.get_tags() or list(),
                "alarms": self.serialize_alarms() or list(),
                "machines": self.serialize_machines() or list(),
                "last_alarms": self.get_lasts_alarms(lasts=10) or list(),
                "last_active_alarms": self.get_lasts_active_alarms(lasts=3) or list(),
                "last_events": self.get_lasts_events(lasts=10) or list(),
                "last_logs": self.get_lasts_logs(lasts=10) or list()
            }
            self.sio.emit("on_connection", data=payload)
        print(_colorize_message(f"[{str_date}] [INFO] Socket.IO server defined successfully", "INFO"))

    @logging_error_handler
    @validate_types(name=StringType, output=StateMachine|None)
    def get_machine(self, name:StringType)->StateMachine:
        r"""
        Retrieves a registered State Machine instance by its name.

        **Parameters:**

        * **name** (StringType): The name of the state machine to retrieve.

        **Returns:**

        * **StateMachine**: The state machine instance if found, otherwise None.

        **Usage:**

        ```python
        >>> from automation import PyAutomation
        >>> app = PyAutomation()
        >>> # Retrieve the main machine
        >>> machine = app.get_machine("Main")
        >>> machine is not None
        True

        ```
        """
        return self.machine_manager.get_machine(name=name)

    @logging_error_handler
    def get_machines(self)->list[tuple[Machine, int, str]]:
        r"""
        Retrieves a list of all registered state machines along with their configuration.

        **Returns:**

        * **list[tuple[Machine, int, str]]**: A list of tuples containing (Machine instance, interval, execution_mode).

        **Usage:**

        ```python
        >>> from automation import PyAutomation
        >>> app = PyAutomation()
        >>> machines = app.get_machines()
        >>> isinstance(machines, list)
        True

        ```
        """
        return self.machine_manager.get_machines()

    @logging_error_handler
    @validate_types(output=list)
    def serialize_machines(self)->list[dict]:
        r"""
        Serializes all registered state machines into a dictionary format.

        **Returns:**

        * **list[dict]**: A list of dictionaries representing the state and configuration of each machine.
        """
        return self.machine_manager.serialize_machines()
    
    @logging_error_handler
    @validate_types(machine=AutomationStateMachine, tag=Tag, output=dict)
    def subscribe_tag_into_automation_machine(self, machine:AutomationStateMachine, tag:Tag)->dict:
        r"""
        Subscribes a specific tag to an automation state machine.
        
        This allows the state machine to observe changes in the tag's value and trigger transitions or logic.

        **Parameters:**

        * **machine** (AutomationStateMachine): The target state machine.
        * **tag** (Tag): The tag to subscribe.

        **Returns:**

        * **dict**: Result of the subscription operation.
        """
        machine.subscribe_to(tag)

    # TAGS METHODS
    @logging_error_handler
    @validate_types(
            name=str,
            unit=str,
            display_unit=str,
            variable=str,
            data_type=str,
            description=str|type(None),
            display_name=str|type(None),
            opcua_address=str|type(None),
            opcua_client_name=str|type(None),
            node_namespace=str|type(None),
            scan_time=int|float|type(None),
            dead_band=int|float|type(None),
            process_filter=bool,
            gaussian_filter=bool,
            gaussian_filter_threshold=float|int,
            gaussian_filter_r_value=float|int,
            outlier_detection=bool,
            out_of_range_detection=bool,
            frozen_data_detection=bool,
            manufacturer=str|type(None),
            segment=str|type(None),
            id=str|type(None),
            user=User|type(None),
            reload=bool,
            output=(Tag|None, str)
    )
    def create_tag(self,
            name:str,
            unit:str,
            variable:str,
            display_unit:str="",
            data_type:str='float',
            description:str=None,
            display_name:str=None,
            opcua_address:str=None,
            opcua_client_name:str=None,
            node_namespace:str=None,
            scan_time:int=None,
            dead_band:float=None,
            process_filter:bool=False,
            gaussian_filter:bool=False,
            gaussian_filter_threshold:float=1.0,
            gaussian_filter_r_value:float=0.0,
            outlier_detection:bool=False,
            out_of_range_detection:bool=False,
            frozen_data_detection:bool=False,
            segment:str|None="",
            manufacturer:str|None="",
            id:str=None,
            user:User|None=None,
            reload:bool=False,
        )->tuple[Tag,str]:
        r"""
        Creates a new tag in the automation application.

        Adding a tag this way provides the following features:
        - Adds the tag to the Current Value Table (CVT).
        - Configures data acquisition from OPC UA (if address provided).
        - Sets up filters (Deadband, Kalman/Gaussian).
        - Initializes historical logging.

        **Parameters:**

        * **name** (str): Unique tag name.
        * **unit** (str): Engineering unit.
        * **variable** (str): Variable type (e.g., 'Pressure', 'Temperature').
        * **display_unit** (str, optional): Unit for display purposes.
        * **scan_time** (int, optional): Polling interval in ms.
        * **opcua_address** (str, optional): OPC UA server URL.
        * **node_namespace** (str, optional): OPC UA Node ID.

        **Returns:**

        * **tuple[Tag, str]**: The created Tag object and a status message.

        **Usage:**

        ```python
        >>> from automation import PyAutomation
        >>> app = PyAutomation()
        >>> # Create a Pressure Tag
        >>> tag, msg = app.create_tag(name="PT-101", unit="bar", variable="Pressure")
        >>> tag.name
        'PT-101'
        >>> tag.unit
        'bar'
        
        >>> # Create a Temperature Tag with specific display unit
        >>> tag2, msg = app.create_tag(name="TT-202", unit="C", variable="Temperature", display_unit="F")
        >>> tag2.get_display_unit()
        'F'
        ```
        """
        if not display_name:

            display_name = name

        # Si se proporciona opcua_client_name directamente, usarlo
        # Si no, intentar resolverlo desde opcua_address
        resolved_opcua_address = opcua_address
        if opcua_client_name:
            # Si se proporciona el nombre del cliente directamente, obtener su URL
            client = self.opcua_client_manager.get(opcua_client_name)
            if client:
                resolved_opcua_address = client.serialize().get("server_url", opcua_address)
        elif opcua_address:
            # Si se proporciona opcua_address, intentar resolver el nombre del cliente
            # Si opcua_address es una URL, buscar el nombre del cliente correspondiente
            # Si opcua_address es un nombre de cliente, usarlo directamente
            if "opc.tcp://" in opcua_address:
                # Es una URL, intentar resolver el nombre del cliente
                client_name = self.opcua_client_manager.get_client_name_by_address(opcua_address)
                if client_name:
                    opcua_client_name = client_name
            else:
                # No es una URL, asumir que es un nombre de cliente
                opcua_client_name = opcua_address
                # Intentar obtener la URL del cliente
                client = self.opcua_client_manager.get(opcua_client_name)
                if client:
                    resolved_opcua_address = client.serialize().get("server_url", opcua_address)
        else:
            opcua_client_name = None

        tag, message = self.cvt.set_tag(
            name=name,
            unit=unit,
            display_unit=display_unit,
            variable=variable,
            data_type=data_type,
            description=description,
            display_name=display_name,
            opcua_address=resolved_opcua_address,
            node_namespace=node_namespace,
            scan_time=scan_time,
            dead_band=dead_band,
            process_filter=process_filter,
            gaussian_filter=gaussian_filter,
            gaussian_filter_threshold=gaussian_filter_threshold,
            gaussian_filter_r_value=gaussian_filter_r_value,
            outlier_detection=outlier_detection,
            out_of_range_detection=out_of_range_detection,
            frozen_data_detection=frozen_data_detection,
            segment=segment,
            manufacturer=manufacturer,
            id=id,
            user=user
        )
        
        # Si se resolvió el nombre del cliente, establecerlo en el tag junto con la URL
        if tag and opcua_client_name:
            if hasattr(tag, 'set_opcua_client_name'):
                tag.set_opcua_client_name(opcua_client_name, opcua_address=resolved_opcua_address)

        # CREATE OPCUA SUBSCRIPTION
        if tag:
                
            if self.is_db_connected():
                self.logger_engine.set_tag(tag=tag)
                self.db_manager.attach(tag_name=name)

            if scan_time:

                self.das.buffer[name] = {
                    "timestamp": Buffer(size=ceil(10 / ceil(scan_time / 1000))),
                    "values": Buffer(size=ceil(10 / ceil(scan_time / 1000))),
                    "unit": display_unit
                }

            else:

                self.das.buffer[name] = {
                    "timestamp": Buffer(),
                    "values": Buffer(),
                    "unit": display_unit
                }
            
            # Solo intentar suscribirse si hay opcua_address y node_namespace
            # Si el cliente no está conectado, subscribe_opcua lo manejará gracefully
            if resolved_opcua_address and node_namespace:
                tag_obj = self.cvt.get_tag_by_name(name=name)
                if tag_obj:
                    self.subscribe_opcua(tag=tag_obj, opcua_address=resolved_opcua_address, node_namespace=node_namespace, scan_time=scan_time, reload=reload)

            return tag, message
        
        else:

            return None, message
    
    @logging_error_handler
    @validate_types(output=list)
    def get_tags(self)->list:
        r"""
        Retrieves all tags registered in the Current Value Table (CVT).

        **Returns:**

        * **list**: A list of Tag dictionaries containing their current values and configuration.

        **Usage:**

        ```python
        >>> from automation import PyAutomation
        >>> app = PyAutomation()
        >>> # Ensure a tag exists
        >>> _ = app.create_tag("Tag_List_Test", "bar", "Pressure")
        >>> tags = app.get_tags()
        >>> isinstance(tags, list)
        True
        >>> any(t['name'] == 'Tag_List_Test' for t in tags)
        True

        ```
        """

        return self.cvt.get_tags()

    @logging_error_handler
    @validate_types(names=list, output=list)
    def get_tags_by_names(self, names:list)->list[Tag|None]:
        r"""
        Retrieves multiple tags by their names.

        **Parameters:**

        * **names** (list): A list of tag names to retrieve.

        **Returns:**

        * **list**: A list of Tag objects or None for each requested name.
        """
        return self.cvt.get_tags_by_names(names=names)

    @logging_error_handler
    @validate_types(name=str, output=Tag|None)
    def get_tag_by_name(self, name:str)->Tag:
        r"""
        Retrieves a single tag by its name.

        **Parameters:**

        * **name** (str): The name of the tag.

        **Returns:**

        * **Tag**: The Tag object if found, otherwise None.

        **Usage:**

        ```python
        >>> from automation import PyAutomation
        >>> app = PyAutomation()
        >>> _ = app.create_tag(name="FlowRate", unit="kg/hr", variable="MassFlow")
        >>> tag = app.get_tag_by_name("FlowRate")
        >>> tag.name
        'FlowRate'
        >>> tag.value
        0.0
        ```
        """
        return self.cvt.get_tag_by_name(name=name)
    
    @logging_error_handler
    @validate_types(namespace=str, output=Tag|None)
    def get_tag_by_node_namespace(self, namespace:str)->Tag:
        r"""
        Retrieves a single tag by its OPC UA node namespace.

        **Parameters:**

        * **namespace** (str): The OPC UA node namespace (e.g., 'ns=2;s=Device1').

        **Returns:**

        * **Tag**: The Tag object if found, otherwise None.
        """
        return self.cvt.get_tag_by_node_namespace(node_namespace=namespace)

    @logging_error_handler
    def get_trends(self, start:str, stop:str, timezone:str, *tags):
        r"""
        Retrieves historical trend data for specified tags within a time range.

        **Parameters:**

        * **start** (str): Start datetime string.
        * **stop** (str): Stop datetime string.
        * **timezone** (str): Timezone for the query.
        * **tags** (tuple): One or more tag names to query.

        **Returns:**

        * **dict**: Historical data for the requested tags.
        """
        return self.logger_engine.read_trends(start, stop, timezone, *tags)
    
    @logging_error_handler
    def get_tags_tables(self, start:str, stop:str, timezone:str, tags:list, page:int=1, limit:int=20):
        r"""
        Retrieves historical data in a paginated table format.

        **Parameters:**

        * **start** (str): Start datetime.
        * **stop** (str): Stop datetime.
        * **timezone** (str): Timezone.
        * **tags** (list): List of tag names.
        * **page** (int): Page number for pagination.
        * **limit** (int): Number of records per page.

        **Returns:**

        * **dict**: Paginated historical data.
        """
        return self.logger_engine.read_table(start, stop, timezone, tags, page, limit)
    
    @logging_error_handler
    def get_tabular_data(self, start:str, stop:str, timezone:str, tags:list, sample_time:int, page:int=1, limit:int=20):
        r"""
        Retrieves historical data resampled to a specific time interval (tabular format).

        **Parameters:**

        * **start** (str): Start datetime.
        * **stop** (str): Stop datetime.
        * **timezone** (str): Timezone.
        * **tags** (list): List of tag names.
        * **sample_time** (int): Resampling interval in seconds.
        * **page** (int): Page number.
        * **limit** (int): Records per page.

        **Returns:**

        * **dict**: Resampled tabular data.
        """
        return self.logger_engine.read_tabular_data(start, stop, timezone, tags, sample_time, page, limit)
    
    @logging_error_handler
    def get_segments(self):
        r"""
        Retrieves all unique segments (logical groupings of tags/machines) defined in the system.

        **Returns:**

        * **list**: List of segment names.
        """
        return self.logger_engine.read_segments()

    @logging_error_handler
    @validate_types(id=str, output=None|str)
    def delete_tag(self, id:str, user:User|None=None)->None|str:
        r"""
        Deletes a tag from the system by its ID.

        **Parameters:**

        * **id** (str): The unique identifier of the tag.
        * **user** (User, optional): The user performing the action (for audit logs).

        **Returns:**

        * **None|str**: None if successful, or an error message string if failed (e.g., tag has active alarms).
        """
        tag = self.cvt.get_tag(id=id)
        tag_name = tag.get_name()
        alarm = self.alarm_manager.get_alarm_by_tag(tag=tag_name)
        if alarm:

            return f"Tag {tag_name} has an alarm associated"

        self.unsubscribe_opcua(tag=tag)
        self.cvt.delete_tag(id=id, user=user)
        self.das.buffer.pop(tag_name)
        # Persist Tag on Database
        if self.is_db_connected():

            self.logger_engine.delete_tag(id=id)

    @logging_error_handler
    def update_tag(
            self, 
            id:str,  
            user:User|None=None,
            **kwargs
        )->tuple[Tag|None, str]:
        r"""
        Updates the configuration of an existing tag.

        **Parameters:**

        * **id** (str): Tag ID.
        * **user** (User, optional): User performing the update.
        * **kwargs**: Tag attributes to update (e.g., name, unit, scan_time, alarm limits).

        **Returns:**

        * **tuple[Tag|None, str]**: A tuple containing the updated Tag object (or None on failure) and a status message.

        **Usage:**

        ```python
        >>> from automation import PyAutomation
        >>> app = PyAutomation()
        >>> tag, _ = app.create_tag("Tag_Update", "C", "Temperature")
        >>> # Update scan time
        >>> updated_tag, msg = app.update_tag(tag.id, scan_time=1000)
        >>> updated_tag.scan_time
        1000

        ```
        """
        tag = self.cvt.get_tag(id=id)       
        if "name" in kwargs:
            tag_name = tag.get_name()
            machines_with_tags_subscribed = list()
            for _machine, _, _ in self.get_machines():
                
                if tag_name in _machine.get_subscribed_tags():

                    machines_with_tags_subscribed.append(_machine.name.value)
            
            if machines_with_tags_subscribed:

                return None, f"{tag_name} is subscribed into {machines_with_tags_subscribed}"

        keys_to_check = ["gaussian_filter", "threshold", "R-value"]
        
        if not any(key in kwargs for key in keys_to_check):
            
            self.unsubscribe_opcua(tag)

        # Persist Tag on Database
        if "variable" in kwargs:
            
            kwargs["unit"] = list(VARIABLES[kwargs["variable"]].values())[0]
            kwargs["display_unit"] = list(VARIABLES[kwargs["variable"]].values())[0]

        if "R-value" in kwargs:

            try:
                r_value = float(kwargs.pop("R-value"))
                if r_value < 0.0 or r_value > 100.0:

                    r_value = tag.gaussian_filter_r_value * 100.0

            except Exception as err:

                r_value = tag.gaussian_filter_r_value

            kwargs['gaussian_filter_r_value'] = r_value / 100.0

        if "threshold" in kwargs:

            try:

                threshold = float(kwargs.pop("threshold"))
                if threshold < 0.0:

                    threshold = tag.gaussian_filter_threshold

            except Exception as err:

                threshold = tag.gaussian_filter_threshold

            kwargs['gaussian_filter_threshold'] = threshold

        # Si se está actualizando opcua_address, intentar resolver el nombre del cliente
        if "opcua_address" in kwargs:
            opcua_address = kwargs["opcua_address"]
            opcua_client_name = None
            resolved_opcua_address = opcua_address
            
            if opcua_address:
                if "opc.tcp://" in opcua_address:
                    # Es una URL, intentar resolver el nombre del cliente
                    client_name = self.opcua_client_manager.get_client_name_by_address(opcua_address)
                    if client_name:
                        opcua_client_name = client_name
                else:
                    # No es una URL, asumir que es un nombre de cliente
                    opcua_client_name = opcua_address
                    # Intentar obtener la URL del cliente
                    client = self.opcua_client_manager.get(opcua_client_name)
                    if client:
                        resolved_opcua_address = client.serialize().get("server_url", opcua_address)
                
                kwargs["opcua_address"] = resolved_opcua_address
        
        result = self.cvt.update_tag(
            id=id,  
            user=user,
            **kwargs
        )
        
        # Si se resolvió el nombre del cliente, establecerlo en el tag actualizado junto con la URL
        if result and "opcua_address" in kwargs and opcua_client_name:
            updated_tag = self.cvt.get_tag(id=id)
            if updated_tag and hasattr(updated_tag, 'set_opcua_client_name'):
                updated_tag.set_opcua_client_name(opcua_client_name, opcua_address=resolved_opcua_address)
        if self.is_db_connected():

            if 'variable' in kwargs:
                
                kwargs.pop("variable")
            
            if kwargs:

                self.logger_engine.update_tag(
                    id=id,  
                    **kwargs
                )

        if "name" in kwargs:

            self.das.buffer.pop(tag_name)

        keys_to_check = ["gaussian_filter", "gaussian_filter_threshold", "gaussian_filter_r_value"]

        if kwargs:

            if not any(key in kwargs for key in keys_to_check):
                
                self.__update_buffer(tag=tag)

                if "scan_time" in kwargs:
                    scan_time = kwargs["scan_time"]
                    if isinstance(scan_time, int):
                        self.subscribe_opcua(tag, opcua_address=tag.get_opcua_address(), node_namespace=tag.get_node_namespace(), scan_time=scan_time)
                    else:
                        self.subscribe_opcua(tag, opcua_address=tag.get_opcua_address(), node_namespace=tag.get_node_namespace(), scan_time=tag.get_scan_time())
                else:

                    self.subscribe_opcua(tag, opcua_address=tag.get_opcua_address(), node_namespace=tag.get_node_namespace(), scan_time=tag.get_scan_time())
        
        return result

    @logging_error_handler
    @validate_types(name=str, output=None|str)
    def delete_tag_by_name(self, name:str, user:User|None=None):
        r"""
        Deletes a tag from the system by its name.

        **Parameters:**

        * **name** (str): The name of the tag.
        * **user** (User, optional): The user performing the action.

        **Usage:**

        ```python
        >>> from automation import PyAutomation
        >>> app = PyAutomation()
        >>> _ = app.create_tag("Tag_Delete", "m", "Length")
        >>> app.delete_tag_by_name("Tag_Delete")
        >>> app.get_tag_by_name("Tag_Delete") is None
        True

        ```
        """
        tag = self.cvt.get_tag_by_name(name=name)
        alarm = self.alarm_manager.get_alarm_by_tag(tag=name)
        if alarm:

            return f"Tag {name} has an alarm associated"

        self.unsubscribe_opcua(tag=tag)
        # Persist Tag on Database
        if self.is_db_connected():

            self.logger_engine.delete_tag(id=tag.id)

        self.cvt.delete_tag(id=tag.id, user=user)

    # USERS METHODS
    @logging_error_handler
    @validate_types(
            username=str|type(None),
            email=str|type(None),
            password=str,
            name=str|type(None),
            output=tuple
    )
    def login(
            self,
            password:str,
            username:str="",
            email:str=""
        )->tuple[User|None, str]:
        r"""
        Authenticates a user by username or email.

        **Parameters:**

        * **password** (str): User password.
        * **username** (str, optional): Username.
        * **email** (str, optional): Email address.

        **Returns:**

        * **tuple[User|None, str]**: User object if successful, plus status message.

        **Usage:**

        ```python
        >>> from automation import PyAutomation
        >>> app = PyAutomation()
        >>> _ = app.set_role("operator_login", 1)
        >>> _ = app.signup("jane_login", "operator_login", "jane_l@example.com", "mypassword")
        >>> user, msg = app.login("mypassword", username="jane_login")
        >>> user.email
        'jane_l@example.com'

        ```
        """
        # Check Token on Database
        try:
            # Verificar si se debe usar la base de datos
            if self.is_db_connected():
                # Intentar verificar la conexión real antes de hacer login
                try:
                    # Verificar que la conexión realmente funciona haciendo una consulta simple
                    db = self.db_manager.get_db()
                    if db is None:
                        # Intentar obtener el error real de conexión
                        conn_error = self._try_get_database_connection_error()
                        if conn_error:
                            return None, self._format_database_error(conn_error, "during login")
                        return None, "Database is not configured correctly. Please configure the database connection first."
                    
                    # Intentar una consulta simple para verificar la conexión real
                    try:
                        db.execute_sql('SELECT 1;')
                    except (OperationalError, InterfaceError, DatabaseError) as db_conn_error:
                        # Error de conexión real (conexión perdida, servidor caído, etc.)
                        return None, self._format_database_error(db_conn_error, "during login")
                    except Exception as db_conn_error:
                        # Otro tipo de error de base de datos
                        return None, self._format_database_error(db_conn_error, "during login")
                    
                    # Si llegamos aquí, la conexión funciona, intentar hacer login
                    result = self.db_manager.login(password=password, username=username, email=email)
                    
                    # Verificar el resultado
                    if result is None:
                        # Si result es None, puede ser porque BaseEngine.query() retornó None (error interno)
                        # Esto indica que hubo un error durante la consulta a la base de datos
                        # Puede ser que la conexión se haya perdido o que haya un problema con la base de datos
                        return None, "Could not process authentication in the database. The connection may have been lost during the query or there is a problem with the database configuration."
                    
                    # Verificar que sea una tupla válida
                    if isinstance(result, tuple) and len(result) == 2:
                        user, message = result
                        # Si el usuario es None pero hay un mensaje, puede ser error de credenciales
                        if user is None and message:
                            # Distinguir entre error de autenticación y otros errores
                            if "Invalid" in message or "invalid" in message.lower() or "credentials" in message.lower() or "password" in message.lower():
                                # Error de autenticación (credenciales incorrectas)
                                return None, f"Authentication error: {message}"
                            else:
                                # Otro tipo de error
                                return None, f"Authentication error: {message}"
                        return result
                    else:
                        return None, "Error: Invalid response from database server."
                        
                except (OperationalError, InterfaceError, DatabaseError) as db_error:
                    # Error específico de base de datos al intentar acceder
                    return None, self._format_database_error(db_error, "during login")
                except Exception as db_error:
                    # Otro tipo de error inesperado
                    return None, self._format_database_error(db_error, "during login")
            else:
                # No hay base de datos configurada, intentar obtener el error real de conexión
                conn_error = self._try_get_database_connection_error()
                if conn_error:
                    return None, self._format_database_error(conn_error, "during login")
                # Si no hay configuración, retornar mensaje genérico
                db_config = self.get_db_config()
                if not db_config:
                    return None, "Database is not configured correctly. Please configure the database connection first."
                else:
                    # Hay configuración pero no se puede conectar y no se pudo obtener el error específico
                    # Intentar formatear un mensaje con la información de configuración disponible
                    dbtype = db_config.get("dbtype", "").lower()
                    if dbtype == "sqlite":
                        config_info = f"SQLite database file: {db_config.get('dbfile', 'unknown')}"
                    else:
                        host = db_config.get("host", "unknown")
                        port = db_config.get("port", "unknown")
                        user = db_config.get("user", "unknown")
                        config_info = f'connection to server at "{host}", port {port} failed for user "{user}"'
                    return None, f'CONNECTING DATABASE ERROR: {config_info}: Unable to establish connection. Please verify the database server is running and the configuration is correct.'
                    
        except Exception as e:
            # En caso de cualquier excepción no prevista, retornar una tupla válida con mensaje descriptivo
            if isinstance(e, (OperationalError, InterfaceError, DatabaseError)):
                return None, self._format_database_error(e, "during login")
            else:
                error_msg = str(e) if e else "Unknown error while attempting to authenticate"
                error_lower = error_msg.lower()
                if "connection" in error_lower or "connect" in error_lower:
                    return None, self._format_database_error(e, "during login") if hasattr(e, '__class__') else f"Database connection error: {error_msg}"
                else:
                    return None, f"Unexpected error during authentication: {error_msg}"

    @logging_error_handler
    @validate_types(
            username=str,
            email=str,
            password=str,
            name=str|type(None),
            lastname=str|type(None),
            role_name=str,
            identifier=str|type(None),
            encode_password=bool,
            output=(User|None, str)
    )
    def signup(
            self,
            username:str,
            email:str,
            password:str,
            name:str=None,
            lastname:str=None,
            role_name:str='guest',
            identifier:str=None,
            encode_password:bool=True,
        )->tuple[User|None, str]:
        r"""
        Registers a new user in the system.

        **Parameters:**

        * **username** (str): Unique username.
        * **email** (str): User's email address.
        * **password** (str): User's password (plain text or hash if encode_password=False).
        * **name** (str, optional): First name.
        * **lastname** (str, optional): Last name.
        * **role_name** (str, optional): Name of the role to assign (e.g., 'admin', 'operator'). Default: 'guest'.
        * **identifier** (str, optional): Unique identifier for the user. If not provided, a random one is generated.
        * **encode_password** (bool, optional): If True, password will be hashed. If False, password is assumed to be already hashed. Default: True.

        **Returns:**

        * **tuple[User|None, str]**: The created User object and a status message.

        **Usage:**

        ```python
        >>> from automation import PyAutomation
        >>> app = PyAutomation()
        >>> # Ensure role exists
        >>> _ = app.set_role("operator_signup", 1)
        >>> user, msg = app.signup("john_signup", "operator_signup", "john_s@example.com", "securepass")
        >>> user.username
        'john_signup'

        ```
        """
        try:
            
            # Persist user on Database if connected
            if self.is_db_connected():

                try:
                    user, message = users.signup(
                        username=username,
                        role_name=role_name,
                        email=email,
                        password=password,
                        name=name,
                        lastname=lastname,
                        identifier=identifier,
                        encode_password=encode_password
                    )
                    # Verificar que la conexión realmente funciona antes de intentar guardar
                    db = self.db_manager.get_db()
                    if db is None:
                        return None, "Database is not configured correctly. User created in memory but cannot be persisted. Please configure the database connection."
                    
                    # Intentar una consulta simple para verificar la conexión real
                    try:
                        db.execute_sql('SELECT 1;')
                    except (OperationalError, InterfaceError, DatabaseError) as db_conn_error:
                        # Error de conexión real
                        error_msg = self._format_database_error(db_conn_error, "while persisting user")
                        return None, f"User created in memory but cannot be persisted. {error_msg}"
                    except Exception as db_conn_error:
                        error_msg = self._format_database_error(db_conn_error, "while persisting user")
                        return None, f"User created in memory but cannot be persisted. {error_msg}"
                    
                    # Si llegamos aquí, la conexión funciona, intentar guardar el usuario
                    try:
                        result = self.db_manager.set_user(user=user)
                        # Verificar que el resultado sea válido
                        if result is None:
                            return None, "Could not persist user to database. The connection may have been lost during the operation or there is a problem with the database configuration."
                        # Si result es una tupla, usar el mensaje
                        if isinstance(result, tuple) and len(result) == 2:
                            _, db_message = result
                            message = db_message if db_message else message
                    except (OperationalError, InterfaceError, DatabaseError) as db_error:
                        # Error específico de base de datos al intentar guardar
                        error_msg = self._format_database_error(db_error, "while persisting user")
                        return None, f"User created in memory but cannot be persisted. {error_msg}"
                    except Exception as db_error:
                        # Otro tipo de error inesperado
                        error_msg = self._format_database_error(db_error, "while persisting user")
                        return None, f"User created in memory but cannot be persisted. {error_msg}"
                except Exception as db_error:
                    # Error al intentar acceder a la base de datos
                    error_msg = self._format_database_error(db_error, "while persisting user")
                    return None, f"User created in memory but cannot be persisted. {error_msg}"

            else:
                # No hay base de datos configurada, usar autenticación en memoria
                return None, "Database is not configured correctly. Please configure the database connection first."

            return user, message
            
        except Exception as e:
            # En caso de cualquier excepción no prevista
            if isinstance(e, (OperationalError, InterfaceError, DatabaseError)):
                return None, self._format_database_error(e, "during signup")
            else:
                error_msg = str(e) if e else "Unknown error while attempting to signup"
                error_lower = error_msg.lower()
                if "connection" in error_lower or "connect" in error_lower:
                    return None, self._format_database_error(e, "during signup") if hasattr(e, '__class__') else f"Database connection error during signup: {error_msg}"
                else:
                    return None, f"Unexpected error during signup: {error_msg}"

    @logging_error_handler
    @validate_types(role_name=str, output=str)
    def create_token(self, role_name:str)->str:
        r"""
        Creates a JWT token for a specific role (used for Third Party integration).

        **Parameters:**

        * **role_name** (str): The role to embed in the token.

        **Returns:**

        * **str**: The encoded JWT token.

        **Usage:**

        ```python
        >>> from automation import PyAutomation
        >>> app = PyAutomation()
        >>> token = app.create_token("admin")
        >>> isinstance(token, str)
        True
        >>> len(token) > 0
        True

        ```
        """
        from . import server
        payload = {
            "created_on": datetime.now(timezone.utc).strftime(self.cvt.DATETIME_FORMAT),
            "role": role_name
        }
        return jwt.encode(payload, server.config['APP_SECRET_KEY'], algorithm="HS256")

    @logging_error_handler
    @validate_types(name=str, level=int, output=(Role|None, str))
    def set_role(self, name:str, level:int)->Role|None:
        r"""
        Defines a new user role in the system.

        **Parameters:**

        * **name** (str): Name of the role.
        * **level** (int): Permission level (lower might mean higher privilege depending on implementation, usually 0 is highest).

        **Returns:**

        * **Role|None**: The created Role object or None if it already exists.

        **Usage:**

        ```python
        >>> from automation import PyAutomation
        >>> app = PyAutomation()
        >>> role, msg = app.set_role("supervisor", 0)
        >>> role.name
        'supervisor'

        ```
        """
        role = Role(name=name, level=level)
        if roles.check_role_name(name=name):

            return None, f"Role {name} exists"
        
        role_id, message = roles.add(role=role)
        if role_id:

            # Persist Tag on Database
            if self.is_db_connected():
                
                _, message = self.db_manager.set_role(name=name, level=level, identifier=role.identifier)

            return role, message

        return None, message

    @logging_error_handler
    @validate_types(
            target_username=str,
            new_password=str,
            current_password=str|type(None),
            output=tuple
    )
    def change_password(
            self,
            target_username:str,
            new_password:str,
            current_password:str=None
        )->tuple[str|None, str]:
        r"""
        Changes a user's password. Internal method without authorization restrictions.

        **Parameters:**

        * **target_username** (str): Username whose password will be changed.
        * **new_password** (str): New password to set.
        * **current_password** (str, optional): Current password (for validation when changing own password).

        **Returns:**

        * **tuple[str|None, str]**: Success message or None, and status message.

        **Usage:**

        ```python
        >>> from automation import PyAutomation
        >>> app = PyAutomation()
        >>> # Change password (internal use, no restrictions)
        >>> msg, status = app.change_password("john", "newpass123", current_password="oldpass")
        ```
        """
        # Get target user
        target_user = users.get_by_username(username=target_username)
        if not target_user:
            return None, f"User {target_username} not found"

        # If current_password is provided, validate it
        if current_password:
            # Validate current password
            if self.is_db_connected():
                db_user = Users.get_or_none(username=target_username)
                if not db_user or not db_user.decode_password(current_password):
                    return None, "Current password is incorrect"
            else:
                # Validate against CVT user
                credentials_valid, _ = users.verify_credentials(password=current_password, username=target_username)
                if not credentials_valid:
                    return None, "Current password is incorrect"

        # Update password
        if self.is_db_connected():
            _, message = self.db_manager.update_password(username=target_username, new_password=new_password)
            # Also update CVT user password
            if target_user:
                target_user.password = users.encode(new_password)
        else:
            # Update CVT user password
            if target_user:
                target_user.password = users.encode(new_password)
            message = f"Password updated successfully for {target_username}"

        return message, "Password changed successfully"

    @logging_error_handler
    @validate_types(
            target_username=str,
            new_password=str,
            output=tuple
    )
    def reset_password(
            self,
            target_username:str,
            new_password:str
        )->tuple[str|None, str]:
        r"""
        Resets a user's password (for forgotten password scenario). Internal method without authorization restrictions.

        **Parameters:**

        * **target_username** (str): Username whose password will be reset.
        * **new_password** (str): New password to set.

        **Returns:**

        * **tuple[str|None, str]**: Success message or None, and status message.

        **Usage:**

        ```python
        >>> from automation import PyAutomation
        >>> app = PyAutomation()
        >>> # Reset password (internal use, no restrictions, no current password validation)
        >>> msg, status = app.reset_password("john", "newpass123")
        ```
        """
        # Get target user
        target_user = users.get_by_username(username=target_username)
        if not target_user:
            return None, f"User {target_username} not found"

        # Update password (no current password validation)
        if self.is_db_connected():
            _, message = self.db_manager.update_password(username=target_username, new_password=new_password)
            # Also update CVT user password
            if target_user:
                target_user.password = users.encode(new_password)
        else:
            # Update CVT user password
            if target_user:
                target_user.password = users.encode(new_password)
            message = f"Password reset successfully for {target_username}"

        return message, "Password reset successfully"

    @logging_error_handler
    @validate_types(
            target_username=str,
            new_role_name=str,
            output=tuple
    )
    def update_user_role(
            self,
            target_username:str,
            new_role_name:str
        )->tuple[str|None, str]:
        r"""
        Updates a user's role. Internal method without authorization restrictions.

        **Parameters:**

        * **target_username** (str): Username whose role will be updated.
        * **new_role_name** (str): New role name to assign.

        **Returns:**

        * **tuple[str|None, str]**: Success message or None, and status message.

        **Usage:**

        ```python
        >>> from automation import PyAutomation
        >>> app = PyAutomation()
        >>> # Update user role (internal use, no restrictions)
        >>> msg, status = app.update_user_role("john", "operator")
        ```
        """
        # Get target user
        target_user = users.get_by_username(username=target_username)
        if not target_user:
            return None, f"User {target_username} not found"

        # Update role
        if self.is_db_connected():
            _, message = self.db_manager.update_role(username=target_username, new_role_name=new_role_name)
            # Also update CVT user role
            if target_user:
                updated_user, cvt_message = users.update_role(username=target_username, new_role_name=new_role_name)
                if updated_user:
                    message = f"Role updated successfully for {target_username}"
        else:
            # Update CVT user role
            updated_user, message = users.update_role(username=target_username, new_role_name=new_role_name)
            if not updated_user:
                return None, message

        return message, "Role updated successfully"

    # OPCUA METHODS
    @logging_error_handler
    @validate_types(host=str|type(None), port=int|type(None), output=dict)
    def find_opcua_servers(self, host:str='127.0.0.1', port:int=4840)->dict:
        r"""
        Attempts to discover OPC UA servers at the specified host and port.

        **Parameters:**

        * **host** (str): IP address or hostname.
        * **port** (int): OPC UA TCP port (default 4840).

        **Returns:**

        * **dict**: Discovery results including endpoint URLs.
        """
        result = {
            "message": f"Connection refused to opc.tcp://{host}:{port}"
        }
        try:

            server = self.opcua_client_manager.discovery(host=host, port=port)
            result["message"] = f"Successfully connection to {server[0]['DiscoveryUrls'][0]}"
            result["data"] = server

        except Exception as err:

            result["data"] = list()

        return result

    @logging_error_handler
    @validate_types(output=dict)
    def get_opcua_clients(self):
        r"""
        Retrieves all configured OPC UA clients from both memory and database.

        Returns all clients that are in the database, regardless of their connection status.
        This allows viewing and editing clients even if they are not currently connected
        (e.g., due to host IP changes).

        **Returns:**

        * **dict**: A dictionary of configured clients with their connection status.
                  Format: {client_name: {client_name, host, port, server_url, is_opened, ...}}
        """
        # Obtener clientes conectados en memoria
        connected_clients = self.opcua_client_manager.serialize()
        
        # Obtener todos los clientes de la base de datos
        all_clients = {}
        
        if self.is_db_connected():
            db_clients = self.db_manager.get_opcua_clients()
            for db_client in db_clients:
                client_name = db_client.get("client_name")
                host = db_client.get("host")
                port = db_client.get("port")
                server_url = f"opc.tcp://{host}:{port}"
                
                # Si el cliente está en memoria (conectado), usar esos datos y agregar campos adicionales
                if client_name in connected_clients:
                    client_data = connected_clients[client_name].copy() if isinstance(connected_clients[client_name], dict) else {}
                    # Agregar campos que pueden faltar para consistencia
                    client_data['client_name'] = client_name
                    client_data['name'] = client_name  # Alias para compatibilidad con frontend
                    client_data['host'] = host
                    client_data['port'] = port
                    all_clients[client_name] = client_data
                else:
                    # Si no está en memoria, crear entrada con datos de BD pero desconectado
                    all_clients[client_name] = {
                        'client_name': client_name,
                        'name': client_name,  # Alias para compatibilidad con frontend
                        'host': host,
                        'port': port,
                        'server_url': server_url,
                        'is_opened': False,
                        'connected': False
                    }
        else:
            # Si no hay BD conectada, retornar solo los clientes en memoria
            # Pero intentar agregar client_name, host, port si están disponibles
            for client_name, client_data in connected_clients.items():
                # Crear una copia para no modificar el original
                client_info = client_data.copy() if isinstance(client_data, dict) else {}
                # Extraer host y port de server_url si está disponible
                if 'server_url' in client_info:
                    try:
                        url = client_info['server_url']
                        if url.startswith('opc.tcp://'):
                            parts = url.replace('opc.tcp://', '').split(':')
                            if len(parts) == 2:
                                client_info['host'] = parts[0]
                                client_info['port'] = int(parts[1])
                    except:
                        pass
                client_info['client_name'] = client_name
                client_info['name'] = client_name  # Alias para compatibilidad con frontend
                all_clients[client_name] = client_info
        
        return all_clients

    @logging_error_handler
    @validate_types(client_name=str, output=Client|type(None))
    def get_opcua_client(self, client_name:str):
        r"""
        Retrieves a specific OPC UA client instance by name.

        **Parameters:**

        * **client_name** (str): The name of the client to retrieve.

        **Returns:**

        * **Client|None**: The OPC UA Client object if found and connected, else None.
        """
        return self.opcua_client_manager.get(client_name=client_name)
    
    @logging_error_handler
    @validate_types(opcua_address=str, output=Client|None)
    def get_opcua_client_by_address(self, opcua_address:str)->Client|None:
        r"""
        Retrieves an OPC UA client corresponding to a specific server address.
        
        **Parameters:**

        * **opcua_address** (str): OPC UA Server address (e.g., "opc.tcp://localhost:4840").
        
        **Returns:**

        * **Client**: The OPC UA client if connected, else None.

        **Usage:**

        ```python
        >>> from automation import PyAutomation
        >>> app = PyAutomation()
        >>> # Returns None if no client connected to that address
        >>> client = app.get_opcua_client_by_address("opc.tcp://localhost:9999")
        >>> client is None
        True

        ```
        """
        return self.opcua_client_manager.get_client_by_address(opcua_address=opcua_address)
    
    @logging_error_handler
    @validate_types(opcua_address=str, node_namespace=str, value=float|int|bool|str, output=tuple)
    def write_opcua_value(self, opcua_address:str, node_namespace:str, value:float|int|bool|str)->tuple[dict, int]:
        r"""
        Writes a value to a specific OPC UA node.
        
        **Parameters:**

        * **opcua_address** (str): Address of the OPC UA server.
        * **node_namespace** (str): Namespace of the node (e.g., "ns=2;i=1234").
        * **value** (float|int|bool|str): The value to write.
        
        **Returns:**

        * **tuple**: A tuple containing a result dictionary and an HTTP status code.

        **Usage:**

        ```python
        >>> from automation import PyAutomation
        >>> from unittest.mock import MagicMock
        >>> app = PyAutomation()
        >>> # Mock client and write method
        >>> app.get_opcua_client_by_address = MagicMock()
        >>> app.get_opcua_client_by_address.return_value.write_value.return_value = ({'success': True}, 200)
        >>> res, status = app.write_opcua_value("opc.tcp://loc", "ns=1;i=1", 10)
        >>> status
        200

        ```
        """
        opcua_client = self.get_opcua_client_by_address(opcua_address=opcua_address)
        
        if not opcua_client:
            return {
                'message': f'Cliente OPC UA no encontrado o no conectado para {opcua_address}',
                'opcua_address': opcua_address,
                'node_namespace': node_namespace,
                'success': False
            }, 404
        
        return opcua_client.write_value(node_namespace=node_namespace, value=value)
    
    @logging_error_handler
    def create_opcua_server_record(self, name:str, namespace:str, access_type:str="Read"):
        r"""
        Creates a record for an OPC UA server node in the database.

        **Parameters:**

        * **name** (str): Name of the node.
        * **namespace** (str): Namespace URI or index.
        * **access_type** (str): Access level (Read, Write, ReadWrite).

        **Usage:**

        ```python
        >>> from automation import PyAutomation
        >>> from unittest.mock import MagicMock
        >>> app = PyAutomation()
        >>> app.opcua_server_engine.create = MagicMock(return_value=True)
        >>> app.create_opcua_server_record("Node1", "ns=1;i=1", "Read")
        True

        ```
        """
        return self.opcua_server_engine.create(name=name, namespace=namespace, access_type=access_type)
    
    @logging_error_handler
    def update_opcua_server_access_type(self, namespace:str, access_type:str):
        r"""
        Updates the access type for a specific OPC UA server node.

        **Parameters:**

        * **namespace** (str): The namespace of the node.
        * **access_type** (str): New access type (Read, Write, ReadWrite).

        **Usage:**

        ```python
        >>> from automation import PyAutomation
        >>> from unittest.mock import MagicMock
        >>> app = PyAutomation()
        >>> app.opcua_server_engine.put = MagicMock(return_value=True)
        >>> app.update_opcua_server_access_type("ns=1;i=1", "Write")
        True

        ```
        """
        return self.opcua_server_engine.put(namespace=namespace, access_type=access_type)
    
    @logging_error_handler
    def get_opcua_server_record_by_namespace(self, namespace:str):
        r"""
        Retrieves an OPC UA server node record by its namespace.

        **Parameters:**

        * **namespace** (str): The namespace to search for.

        **Returns:**

        * **dict**: Node record data.

        **Usage:**

        ```python
        >>> from automation import PyAutomation
        >>> from unittest.mock import MagicMock
        >>> app = PyAutomation()
        >>> app.opcua_server_engine.read_by_namespace = MagicMock(return_value={'name': 'Node1'})
        >>> record = app.get_opcua_server_record_by_namespace("ns=1;i=1")
        >>> record['name']
        'Node1'

        ```
        """
        return self.opcua_server_engine.read_by_namespace(namespace=namespace)

    @logging_error_handler
    @validate_types(output=list)
    def get_opcua_server_attrs(self)->list:
        r"""
        Retrieves all attributes (variables and properties) from the OPC UA Server state machine.

        This method scans the OPCUAServer state machine instance and extracts all OPC UA nodes
        (variables and their properties) with their access levels.

        **Returns:**

        * **list**: List of dictionaries containing:
            - **name**: Full name path (parent_folder.variable_name or parent_folder.variable_name.property_name)
            - **namespace**: OPC UA node namespace string
            - **access_type**: Access level ("Read", "Write", or "ReadWrite")

        **Usage:**

        ```python
        >>> from automation import PyAutomation
        >>> app = PyAutomation()
        >>> attrs = app.get_opcua_server_attrs()
        >>> isinstance(attrs, list)
        True
        >>> if attrs:
        ...     print(attrs[0].keys())
        dict_keys(['name', 'namespace', 'access_type'])
        ```
        """
        from .state_machine import Node, ua
        from .models import StringType
        
        attrs = list()
        
        # Get OPCUAServer machine by name
        opcua_server_machine = self.get_machine(name=StringType("OPCUAServer"))
        
        if not opcua_server_machine:
            return attrs
        
        # Iterate through all attributes of the machine
        for attr in dir(opcua_server_machine):
            if hasattr(opcua_server_machine, attr):
                node = getattr(opcua_server_machine, attr)
                if isinstance(node, Node):
                    
                    node_class = node.get_node_class()
                    if node_class == ua.NodeClass.Variable:
                        
                        display_name = node.get_attribute(ua.AttributeIds.DisplayName).Value.Value.Text
                        # Get parent node
                        parent_node = node.get_parent()
                        
                        # Get parent folder name
                        parent_name = parent_node.get_browse_name().Name
                        access_level = node.get_access_level()
                        
                        # Determine access type
                        write_only = ua.AccessLevel.CurrentWrite in access_level and ua.AccessLevel.CurrentRead not in access_level
                        read_write = ua.AccessLevel.CurrentRead in access_level and ua.AccessLevel.CurrentWrite in access_level
                        access_type = "Read"
                        if write_only:
                            access_type = "Write"
                        elif read_write:
                            access_type = "ReadWrite"
                        
                        attrs.append({
                            "name": f"{parent_name}.{display_name}",
                            "namespace": node.nodeid.to_string(),
                            "access_type": access_type
                        })
                        
                        # Get properties of the variable
                        properties = node.get_properties()
                        for prop in properties:
                            prop_name = prop.get_display_name().Text
                            
                            access_level = prop.get_access_level()
                            # Determine access type for property
                            write_only = ua.AccessLevel.CurrentWrite in access_level and ua.AccessLevel.CurrentRead not in access_level
                            read_write = ua.AccessLevel.CurrentRead in access_level and ua.AccessLevel.CurrentWrite in access_level
                            access_type = "Read"
                            if write_only:
                                access_type = "Write"
                            elif read_write:
                                access_type = "ReadWrite"
                            
                            attrs.append({
                                "name": f"{parent_name}.{display_name}.{prop_name}",
                                "namespace": prop.nodeid.to_string(),
                                "access_type": access_type
                            })
        
        return attrs

    @logging_error_handler
    @validate_types(namespace=str, access_type=str, name=str|type(None), output=tuple)
    def update_opcua_server_node_access_type(self, namespace:str, access_type:str, name:str=None)->tuple[bool, str]:
        r"""
        Updates the access type (Read, Write, ReadWrite) for a specific OPC UA Server node.

        This method finds the node by its namespace, updates the access type in the database,
        modifies the node's access level bits, and manages subscriptions for write-enabled nodes.

        **Parameters:**

        * **namespace** (str): The OPC UA node namespace string (e.g., "ns=2;i=1234").
        * **access_type** (str): New access type ("Read", "Write", or "ReadWrite").
        * **name** (str, optional): Node name for database record creation if it doesn't exist.

        **Returns:**

        * **tuple[bool, str]**: (Success boolean, Message string).

        **Usage:**

        ```python
        >>> from automation import PyAutomation
        >>> app = PyAutomation()
        >>> success, msg = app.update_opcua_server_node_access_type(
        ...     namespace="ns=2;i=1234",
        ...     access_type="ReadWrite"
        ... )
        >>> success
        True
        ```
        """
        from .state_machine import Node, ua
        from .models import StringType
        from .opcua.subscription import SubHandlerServer
        
        # Get OPCUAServer machine
        opcua_server_machine = self.get_machine(name=StringType("OPCUAServer"))
        
        if not opcua_server_machine:
            return False, "OPC UA Server machine not found"
        
        # Find the node by namespace
        node = None
        opcua_server_attrs = dir(opcua_server_machine)
        
        for item in opcua_server_attrs:
            if hasattr(opcua_server_machine, item):
                candidate_node = getattr(opcua_server_machine, item)
                if isinstance(candidate_node, Node):
                    node_class = candidate_node.get_node_class()
                    
                    if node_class == ua.NodeClass.Variable:
                        if candidate_node.nodeid.to_string() == namespace:
                            node = candidate_node
                            break
                        else:
                            # Check properties
                            props = candidate_node.get_properties()
                            for prop in props:
                                if prop.nodeid.to_string() == namespace:
                                    node = prop
                                    break
                            if node:
                                break
        
        if not node:
            return False, f"Node with namespace '{namespace}' not found"
        
        # Validate access_type
        access_type_lower = access_type.lower()
        if access_type_lower not in ["read", "write", "readwrite"]:
            return False, f"Invalid access_type '{access_type}'. Must be 'Read', 'Write', or 'ReadWrite'"
        
        # Update or create database record
        opcua_server_obj = self.get_opcua_server_record_by_namespace(namespace=namespace)
        if opcua_server_obj:
            self.update_opcua_server_access_type(namespace=namespace, access_type=access_type)
        else:
            if not name:
                # Try to get name from node
                try:
                    display_name = node.get_display_name().Text
                    parent_node = node.get_parent()
                    parent_name = parent_node.get_browse_name().Name
                    name = f"{parent_name}.{display_name}"
                except:
                    name = f"Node_{namespace}"
            self.create_opcua_server_record(name=name, namespace=namespace, access_type=access_type)
        
        # Get handler for subscriptions
        handler = SubHandlerServer()
        
        # Clear all access bits first
        node.unset_attr_bit(ua.AttributeIds.AccessLevel, ua.AccessLevel.CurrentRead)
        node.unset_attr_bit(ua.AttributeIds.AccessLevel, ua.AccessLevel.CurrentWrite)
        node.unset_attr_bit(ua.AttributeIds.UserAccessLevel, ua.AccessLevel.CurrentRead)
        node.unset_attr_bit(ua.AttributeIds.UserAccessLevel, ua.AccessLevel.CurrentWrite)
        
        # Unsubscribe if exists
        subscriptions = handler.subscriptions
        if namespace in subscriptions:
            _sub = subscriptions.pop(namespace)
            _sub.delete()
        
        # Set new access level
        if access_type_lower == "write":
            # Write only: disable read, enable write
            node.set_attr_bit(ua.AttributeIds.AccessLevel, ua.AccessLevel.CurrentWrite)
            node.set_attr_bit(ua.AttributeIds.UserAccessLevel, ua.AccessLevel.CurrentWrite)
            # Create subscription for write-enabled nodes
            sub = opcua_server_machine.server.create_subscription(100, handler)
            sub.subscribe_data_change(node)
            handler.subscriptions[namespace] = sub
        elif access_type_lower == "read":
            # Read only: enable read, disable write
            node.set_attr_bit(ua.AttributeIds.AccessLevel, ua.AccessLevel.CurrentRead)
            node.set_attr_bit(ua.AttributeIds.UserAccessLevel, ua.AccessLevel.CurrentRead)
        elif access_type_lower == "readwrite":
            # Read and write: enable both
            node.set_attr_bit(ua.AttributeIds.AccessLevel, ua.AccessLevel.CurrentRead)
            node.set_attr_bit(ua.AttributeIds.AccessLevel, ua.AccessLevel.CurrentWrite)
            node.set_attr_bit(ua.AttributeIds.UserAccessLevel, ua.AccessLevel.CurrentRead)
            node.set_attr_bit(ua.AttributeIds.UserAccessLevel, ua.AccessLevel.CurrentWrite)
            # Create subscription for readwrite nodes
            sub = opcua_server_machine.server.create_subscription(100, handler)
            sub.subscribe_data_change(node)
            handler.subscriptions[namespace] = sub
        
        return True, f"Access type updated successfully to '{access_type}'"

    @logging_error_handler
    @validate_types(client_name=str, namespaces=list, output=list)
    def get_node_values(self, client_name:str, namespaces:list)->list:
        r"""
        Reads values from multiple nodes using a specific OPC UA client.

        **Parameters:**

        * **client_name** (str): The name of the client to use.
        * **namespaces** (list): List of node namespaces/IDs to read.

        **Returns:**

        * **list**: List of values read from the nodes.

        **Usage:**

        ```python
        >>> from automation import PyAutomation
        >>> from unittest.mock import MagicMock
        >>> app = PyAutomation()
        >>> app.opcua_client_manager.get_node_values = MagicMock(return_value=[10, 20])
        >>> app.get_node_values("PLC1", ["ns=1;i=1", "ns=1;i=2"])
        [10, 20]

        ```
        """

        return self.opcua_client_manager.get_node_values(client_name=client_name, namespaces=namespaces)

    @logging_error_handler
    @validate_types(client_name=str, namespaces=list, output=list|None)
    def get_node_attributes(self, client_name:str, namespaces:list)->list[dict]:
        r"""
        Reads attributes (e.g., Description, DataType) from multiple nodes.

        **Parameters:**

        * **client_name** (str): The name of the client to use.
        * **namespaces** (list): List of node namespaces/IDs.

        **Returns:**

        * **list[dict]**: List of attribute dictionaries.

        **Usage:**

        ```python
        >>> from automation import PyAutomation
        >>> from unittest.mock import MagicMock
        >>> app = PyAutomation()
        >>> app.opcua_client_manager.get_node_attributes = MagicMock(return_value=[{'description': 'test'}])
        >>> app.get_node_attributes("PLC1", ["ns=1;i=1"])
        [{'description': 'test'}]

        ```
        """

        return self.opcua_client_manager.get_node_attributes(client_name=client_name, namespaces=namespaces)

    @logging_error_handler
    def get_opcua_tree(self, client_name:str):
        r"""
        Retrieves the hierarchical node tree structure from a connected OPC UA server.

        **Parameters:**

        * **client_name** (str): The name of the client to use.

        **Returns:**

        * **dict**: Nested dictionary representing the node tree.

        **Usage:**

        ```python
        >>> from automation import PyAutomation
        >>> from unittest.mock import MagicMock
        >>> app = PyAutomation()
        >>> app.opcua_client_manager.get_opcua_tree = MagicMock(return_value={'Root': {}})
        >>> app.get_opcua_tree("PLC1")
        {'Root': {}}

        ```
        """
        return self.opcua_client_manager.get_opcua_tree(client_name=client_name)

    @logging_error_handler
    @validate_types(client_name=str, host=str|type(None), port=int|type(None), output=(bool, str|dict))
    def add_opcua_client(self, client_name:str, host:str="127.0.0.1", port:int=4840):
        r"""
        Registers and connects a new OPC UA client.

        **Parameters:**

        * **client_name** (str): A unique name for this client connection.
        * **host** (str): Server IP or hostname.
        * **port** (int): Server port.

        **Returns:**

        * **tuple**: (Success boolean, Message or client data).

        **Usage:**

        ```python
        >>> from automation import PyAutomation
        >>> from unittest.mock import MagicMock
        >>> app = PyAutomation()
        >>> # Mock discovery to return a fake server
        >>> app.find_opcua_servers = MagicMock(return_value=[{'DiscoveryUrls': ['opc.tcp://localhost:4840']}])
        >>> # Mock client manager add
        >>> app.opcua_client_manager.add = MagicMock(return_value=(True, "Client added"))
        >>> success, msg = app.add_opcua_client("PLC1", "localhost", 4840)
        >>> success
        True

        ```
        """
        servers = self.find_opcua_servers(host=host, port=port)

        # Intentar agregar el cliente al manager incluso si no encuentra servidores
        # El manager manejará la conexión y agregará el cliente a memoria aunque falle
        result = self.opcua_client_manager.add(client_name=client_name, host=host, port=port)
        
        if result:
            return result
        
        # Si no hay servidores pero el cliente se agregó a memoria (aunque no conectado),
        # retornar éxito parcial para permitir actualizaciones
        if client_name in self.opcua_client_manager._clients:
            return False, f"Client '{client_name}' added to memory but connection failed. Servers not found or connection error."
        
        return False, f"Failed to add client '{client_name}'. Servers not found."
        
    @logging_error_handler
    @validate_types(client_name=str, host=str|type(None), port=int|type(None), output=bool)
    def remove_opcua_client(self, client_name:str):
        r"""
        Disconnects and removes an OPC UA client configuration.

        **Parameters:**

        * **client_name** (str): The name of the client to remove.

        **Returns:**

        * **bool**: True if successful, False otherwise.

        **Usage:**

        ```python
        >>> from automation import PyAutomation
        >>> from unittest.mock import MagicMock
        >>> app = PyAutomation()
        >>> app.opcua_client_manager.remove = MagicMock(return_value=True)
        >>> app.remove_opcua_client("PLC1")
        True

        ```
        """
        return self.opcua_client_manager.remove(client_name=client_name)

    @logging_error_handler
    @validate_types(old_client_name=str, new_client_name=str|type(None), host=str|type(None), port=int|type(None), output=(bool, str|dict))
    def update_opcua_client(self, old_client_name:str, new_client_name:str=None, host:str=None, port:int=None):
        r"""
        Updates the configuration of an existing OPC UA client.

        **Parameters:**

        * **old_client_name** (str): The current name of the client to update (required).
        * **new_client_name** (str, optional): New name for the client. If None, keeps the current name.
        * **host** (str, optional): New server IP or hostname. If None, keeps the current host.
        * **port** (int, optional): New server port. If None, keeps the current port.

        **Returns:**

        * **tuple**: (Success boolean, Message or client data).

        **Usage:**

        ```python
        >>> from automation import PyAutomation
        >>> from unittest.mock import MagicMock
        >>> app = PyAutomation()
        >>> # Mock discovery to return a fake server (only needed if changing host/port)
        >>> app.find_opcua_servers = MagicMock(return_value=[{'DiscoveryUrls': ['opc.tcp://localhost:4840']}])
        >>> # Mock client manager update
        >>> app.opcua_client_manager.update = MagicMock(return_value=(True, "Client updated"))
        >>> # Update only the name
        >>> success, msg = app.update_opcua_client("PLC1", new_client_name="PLC1_Updated")
        >>> success
        True
        >>> # Update only host and port
        >>> success, msg = app.update_opcua_client("PLC1", host="192.168.1.100", port=4841)
        >>> success
        True

        ```
        """
        # Obtener valores actuales del cliente si no se proporcionan
        current_host = None
        current_port = None
        if host is None or port is None:
            client = self.opcua_client_manager.get(old_client_name)
            if not client:
                return False, f"Client '{old_client_name}' not found"
            
            # Obtener host y port actuales del cliente
            serialized = client.serialize()
            current_url = serialized.get("server_url", "")
            try:
                if current_url.startswith("opc.tcp://"):
                    parts = current_url.replace("opc.tcp://", "").split(":")
                    if len(parts) == 2:
                        current_host = parts[0]
                        current_port = int(parts[1])
                        if host is None:
                            host = current_host
                        if port is None:
                            port = current_port
            except:
                pass
        
        # Solo hacer discovery si se está cambiando el host/port
        # Si solo se cambia el nombre, no necesitamos verificar el servidor
        if host is not None and port is not None and current_host is not None and current_port is not None:
            new_url = f"opc.tcp://{host}:{port}"
            current_url = f"opc.tcp://{current_host}:{current_port}"
            # Solo hacer discovery si el URL cambió
            if current_url != new_url:
                servers = self.find_opcua_servers(host=host, port=port)
                if not servers:
                    return False, f"Failed to discover OPC UA server at {host}:{port}"

        return self.opcua_client_manager.update(old_client_name=old_client_name, new_client_name=new_client_name, host=host, port=port)

    @logging_error_handler
    @validate_types(tag=Tag, opcua_address=str|type(None), node_namespace=str|type(None), scan_time=float|int|type(None), reload=bool, output=None)
    def subscribe_opcua(self, tag:Tag, opcua_address:str, node_namespace:str, scan_time:float, reload:bool=False):
        r"""
        Subscribes a tag to an OPC UA server, either via DAS (Subscription) or DAQ (Polling).
        
        If `scan_time` is small (<= 100ms), it uses DAS for event-based subscription.
        Otherwise, it creates or updates a DAQ machine for polling at the specified interval.

        **Parameters:**

        * **tag** (Tag): The tag object to subscribe.
        * **opcua_address** (str): The address of the OPC UA server (e.g., 'opc.tcp://localhost:4840').
        * **node_namespace** (str): The node ID to subscribe to.
        * **scan_time** (float): The scan time or sampling interval in milliseconds.
        * **reload** (bool, optional): If True, reloads the subscription if it already exists.

        **Usage:**

        ```python
        >>> from automation import PyAutomation
        >>> from unittest.mock import MagicMock
        >>> app = PyAutomation()
        >>> tag, _ = app.create_tag("Tag_Sub", "bar", "Pressure")
        >>> # Mock internal subscription method
        >>> app.subscribe_tag = MagicMock()
        >>> # Subscribe with 1000ms scan time (uses DAQ/subscribe_tag)
        >>> app.subscribe_opcua(tag, "opc.tcp://localhost:4840", "ns=2;s=Press", 1000)
        >>> app.subscribe_tag.called
        True

        ```
        """
        if opcua_address and node_namespace:

            if not scan_time or scan_time<=100:                                                           # SUBSCRIBE BY DAS
                
                for client_name, info in self.get_opcua_clients().items():

                    if opcua_address==info.get("server_url"):
                        # Verificar que el cliente esté conectado antes de intentar suscribirse
                        is_connected = info.get("is_opened", False) or info.get("connected", False)
                        if not is_connected:
                            # Si el cliente no está conectado, saltar y continuar con el siguiente
                            # Esto puede pasar cuando se carga un tag desde la BD y el cliente no está conectado
                            continue

                        opcua_client = self.get_opcua_client(client_name=client_name)
                        # Verificar que el cliente sea válido antes de usarlo
                        if opcua_client is None:
                            continue
                            
                        # Verificar que el cliente esté realmente conectado
                        if not opcua_client.is_connected():
                            continue
                            
                        subscription = opcua_client.create_subscription(1000, self.das)
                        node_id = opcua_client.get_node_id_by_namespace(node_namespace)
                        if node_id:
                            self.das.subscribe(subscription=subscription, client_name=client_name, node_id=node_id)
                        break

            else:                                                                       # SUBSCRIBE BY DAQ
                
                self.subscribe_tag(tag_name=tag.get_name(), scan_time=scan_time, reload=reload)

        # Asegurar que el buffer existe antes de actualizarlo
        if tag.get_name() in self.das.buffer:
            self.das.buffer[tag.get_name()].update({
                "unit": tag.get_display_unit()
            })

    @logging_error_handler
    @validate_types(tag_name=str, scan_time=float|int, reload=bool, output=None)
    def subscribe_tag(self, tag_name:str, scan_time:float|int, reload:bool=False):
        r"""
        Subscribes a tag to a Data Acquisition (DAQ) machine for polling.

        It manages the creation of DAQ machines based on the scan time interval.

        **Parameters:**

        * **tag_name** (str): The name of the tag.
        * **scan_time** (float|int): The polling interval in milliseconds.
        * **reload** (bool, optional): If True, forces a reload of the machine configuration.

        **Usage:**

        ```python
        >>> from automation import PyAutomation
        >>> app = PyAutomation()
        >>> _ = app.create_tag("Tag_Poll", "C", "Temperature")
        >>> # This will create/update a DAQ machine
        >>> app.subscribe_tag("Tag_Poll", 1000)
        >>> machines = app.get_machines()
        >>> any(m[0].name.value == "DAQ-1000" for m in machines)
        True

        ```
        """
        scan_time = float(scan_time)
        daq_name = StringType(f"DAQ-{int(scan_time)}")
        daq = self.machine_manager.get_machine(name=daq_name)
        tag = self.cvt.get_tag_by_name(name=tag_name)
        if not daq:

            daq = DAQ(name=daq_name)
            interval = FloatType(scan_time / 1000)
            daq.set_opcua_client_manager(manager=self.opcua_client_manager)
            self.machine.append_machine(machine=daq, interval=interval, mode="async")
            
            if not reload:

                if self.machine.state_worker:
                    self.machine.join(machine=daq)
                else:
                    self.machine.start()

        daq.subscribe_to(tag=tag)

    @logging_error_handler    
    @validate_types(tag=Tag, output=None)
    def unsubscribe_opcua(self, tag:Tag):
        r"""
        Unsubscribes a tag from its OPC UA source (DAS or DAQ).

        **Parameters:**

        * **tag** (Tag): The tag object to unsubscribe.

        **Usage:**

        ```python
        >>> from automation import PyAutomation
        >>> app = PyAutomation()
        >>> tag, _ = app.create_tag("Tag_Unsub", "m", "Length")
        >>> app.subscribe_tag("Tag_Unsub", 1000)
        >>> app.unsubscribe_opcua(tag)
        >>> # Verification: check log or internal state if possible
        ```
        """

        if tag.get_node_namespace():

            for client_name, info in self.get_opcua_clients().items():

                if tag.get_opcua_address()==info["server_url"]:

                    opcua_client = self.get_opcua_client(client_name=client_name)
                    node_id = opcua_client.get_node_id_by_namespace(tag.get_node_namespace())
                    self.das.unsubscribe(client_name=client_name, node_id=node_id)
                    break

            drop_machine_from_worker, _, _ = self.machine_manager.unsubscribe_tag(tag=tag)
            if drop_machine_from_worker:
                
                self.machine.drop(machine=drop_machine_from_worker)

            # CLEAR BUFFER
            scan_time = tag.get_scan_time()
            if scan_time:

                self.das.buffer[tag.get_name()].update({
                    "timestamp": Buffer(size=ceil(10 / ceil(scan_time / 1000))),
                    "values": Buffer(size=ceil(10 / ceil(scan_time / 1000)))
                })
            else:
                self.das.buffer[tag.get_name()].update({
                    "timestamp": Buffer(),
                    "values": Buffer()
                })

    @logging_error_handler
    def __update_buffer(self, tag:Tag):
        r"""
        Updates the internal buffer size for a tag based on its scan time.

        **Parameters:**

        * **tag** (Tag): The tag object.
        """
        tag_name = tag.get_name()
        scan_time = tag.get_scan_time()
        unit = tag.get_display_unit()
    
        if scan_time:

            self.das.buffer[tag_name] = {
                "timestamp": Buffer(size=ceil(10 / ceil(scan_time / 1000))),
                "values": Buffer(size=ceil(10 / ceil(scan_time / 1000))),
                "unit": unit
            }

        else:

            self.das.buffer[tag_name] = {
                "timestamp": Buffer(),
                "values": Buffer(),
                "unit": unit
            }

    # ERROR LOGS
    @logging_error_handler
    @validate_types(level=int, file=str, output=None)
    def set_log(self, level:int=logging.INFO, file:str="logs/app.log"):
        r"""
        Sets the log file and level.

        **Parameters:**

        * **level** (str): `logging.LEVEL` (default: logging.INFO).
        * **file** (str): log filename (default: 'app.log').

        **Returns:** `None`

        **Usage:**

        ```python
        >>> from automation import PyAutomation
        >>> app = PyAutomation()
        >>> app.set_log(file="app.log")

        ```
        """

        self._logging_level = level
        self._log_file = file
        
    # DATABASES
    @validate_types(
            dbtype=str, 
            drop_table=bool, 
            clear_default_tables=bool, 
            dbfile=str|type(None),
            user=str|type(None),
            password=str|type(None),
            host=str|type(None),
            port=int|type(None),
            name=str|type(None),
            output=None)
    def set_db(
        self, 
        dbtype:str='sqlite', 
        drop_table:bool=False, 
        clear_default_tables:bool=False,
        **kwargs):
        r"""
        Sets the database connection settings.
        
        Supports SQLite, MySQL, and PostgreSQL.

        **Parameters:**

        * **dbtype** (str): 'sqlite', 'mysql', or 'postgresql'.
        * **dbfile** (str): Path to database file (for SQLite).
        * **drop_table** (bool): If True, drops existing tables (Use with caution!).
        * **clear_default_tables** (bool): If True, truncates default tables.
        * **kwargs**: Additional connection parameters (user, password, host, port, name).

        **Returns:** `None`

        **Usage:**

        ```python
        >>> from automation import PyAutomation
        >>> app = PyAutomation()
        >>> app.set_db(dbtype="sqlite", dbfile="test_set_db.db")
        >>> app.connect_to_db()
        True

        ```
        """

        from .dbmodels import proxy
        str_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        if clear_default_tables:

            self.db_manager.clear_default_tables()

        if dbtype.lower()=='sqlite':

            dbfile = kwargs.get("dbfile", ":memory:")
            if not dbfile.endswith(".db"):
                dbfile = f"{dbfile}.db"
            
            self._db = SqliteDatabase(os.path.join(".", "db", dbfile), pragmas={
                'journal_mode': 'wal',
                'wal_checkpoint': 1,
                'cache_size': -1024 * 10,  # 10MB
                'foreign_keys': 1,
                'ignore_check_constraints': 0,
                'synchronous': 1
                }
            )
            logging.warning(f"SQLite database is not recommended for production: {dbfile}")
            print(_colorize_message(f"[{str_date}] [WARNING] SQLite database is not recommended for production: {dbfile}", "WARNING"))

        elif dbtype.lower()=='mysql':

            db_name = kwargs['name']
            del kwargs['name']
            self._db = MySQLDatabase(db_name, **kwargs)

        elif dbtype.lower()=='postgresql':

            db_name = kwargs['name']
            del kwargs['name']
            self._db = PostgresqlDatabase(db_name, **kwargs)

        proxy.initialize(self._db)
        self._db.connect()
        self.db_manager.set_db(self._db, is_history_logged=self.__log_histories)
        self.db_manager.set_dropped(drop_table)

    @logging_error_handler
    @validate_types(
            dbtype=str, 
            dbfile=str, 
            user=str|type(None), 
            password=str|type(None), 
            host=str|type(None), 
            port=int|str|type(None), 
            name=str|type(None), 
            output=None)
    def set_db_config(
            self,
            dbtype:str="sqlite",
            dbfile:str="app.db",
            user:str|None="admin",
            password:str|None="admin",
            host:str|None="127.0.0.1",
            port:int|str|None=5432,
            name:str|None="app_db"
        ):
        r"""
        Writes the database configuration to a `db_config.json` file.

        **Parameters:**

        * **dbtype** (str): Database type ('sqlite', 'postgresql', 'mysql').
        * **dbfile** (str): Filename for SQLite database (default 'app.db').
        * **user** (str, optional): Database user.
        * **password** (str, optional): Database password.
        * **host** (str, optional): Database host.
        * **port** (int|str, optional): Database port.
        * **name** (str, optional): Database name (for non-SQLite).

        **Usage:**

        ```python
        >>> from automation import PyAutomation
        >>> import os
        >>> app = PyAutomation()
        >>> app.set_db_config(dbtype="sqlite", dbfile="test_config.db")
        >>> os.path.exists("./db/db_config.json")
        True

        ```
        """
        str_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        if dbtype.lower()=="sqlite":

            db_config = {
                "dbtype": dbtype,
                "dbfile": dbfile
            }
            logging.warning(f"Setting database config: {db_config}")
            print(_colorize_message(f"[{str_date}] [WARNING] Setting database config: {db_config}", "WARNING"))

        else:

            # Asegurar que el puerto sea un entero si es posible
            try:
                port_value = int(port) if port is not None else None
            except (TypeError, ValueError):
                port_value = None

            db_config = {
                "dbtype": dbtype,
                'user': user,
                'password': password,
                'host': host,
                'port': port_value,
                'name': name,
            }

        with open('./db/db_config.json', 'w') as json_file:

            json.dump(db_config, json_file)

    @logging_error_handler
    @validate_types(output=dict|None)
    def get_db_config(self):
        r"""
        Reads the database configuration from `db_config.json`.

        **Returns:**

        * **dict|None**: The database configuration dictionary or None if reading fails.

        **Usage:**

        ```python
        >>> from automation import PyAutomation
        >>> app = PyAutomation()
        >>> app.set_db_config(dbtype="sqlite", dbfile="test_read.db")
        >>> config = app.get_db_config()
        >>> config['dbfile']
        'test_read.db'

        ```
        """
        try:

            with open('./db/db_config.json', 'r') as json_file:

                db_config = json.load(json_file)

            return db_config
        
        except Exception as e:
            str_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            _, _, e_traceback = sys.exc_info()
            e_filename = os.path.split(e_traceback.tb_frame.f_code.co_filename)[1]
            e_message = str(e)
            e_line_number = e_traceback.tb_lineno
            message = f"Database is not configured: {e_line_number} - {e_filename} - {e_message}"
            logging.warning(message)
            print(_colorize_message(f"[{str_date}] [WARNING] {message}", "WARNING"))
            return None

    @logging_error_handler
    def set_app_config(self, **kwargs):
        r"""
        Updates application configuration in `app_config.json`.

        **Parameters:**

        * **kwargs**: Configuration keys and values to update (e.g., logger_period).

        **Usage:**

        ```python
        >>> from automation import PyAutomation
        >>> app = PyAutomation()
        >>> app.set_app_config(logger_period=5.0)
        >>> config = app.get_app_config()
        >>> config['logger_period']
        5.0

        ```
        """
        try:
            config_path = os.path.join(".", "db", "app_config.json")
            config = {}
            
            if os.path.exists(config_path):
                with open(config_path, 'r') as f:
                    config = json.load(f)
            
            config.update(kwargs)
            
            with open(config_path, 'w') as f:
                json.dump(config, f, indent=4)
                
        except Exception as e:
            logging.error(f"Failed to persist app config: {e}")

    @logging_error_handler
    def get_app_config(self) -> dict:
        r"""
        Retrieves the application configuration from `app_config.json`.

        If the file doesn't exist, it creates one with default values.

        **Returns:**

        * **dict**: Application configuration dictionary.

        **Usage:**

        ```python
        >>> from automation import PyAutomation
        >>> app = PyAutomation()
        >>> config = app.get_app_config()
        >>> isinstance(config, dict)
        True

        ```
        """
        try:
            config_path = os.path.join(".", "db", "app_config.json")
            if os.path.exists(config_path):
                with open(config_path, 'r') as f:
                    return json.load(f)
            else:
                # Create default config if not exists
                default_config = {
                    "logger_period": 10.0,
                    "log_level": 20
                }
                self.set_app_config(**default_config)
                return default_config
                
        except Exception as e:
            logging.error(f"Failed to read app config: {e}")
            return {"logger_period": 10.0, "log_level": 20}

    def _format_database_error(self, error: Exception, context: str = "") -> str:
        """
        Formatea un mensaje de error de base de datos de manera descriptiva,
        incluyendo información de configuración (IP, puerto, usuario) cuando esté disponible.
        
        Args:
            error: La excepción de base de datos
            context: Contexto adicional (ej: "during login", "while persisting user")
        
        Returns:
            Mensaje de error formateado con detalles descriptivos
        """
        error_str = str(error)
        error_lower = error_str.lower()
        
        # Intentar obtener la configuración de la base de datos
        db_config = self.get_db_config()
        config_info = ""
        if db_config:
            if db_config.get("dbtype", "").lower() == "sqlite":
                config_info = f"SQLite database file: {db_config.get('dbfile', 'unknown')}"
            else:
                host = db_config.get("host", "unknown")
                port = db_config.get("port", "unknown")
                user = db_config.get("user", "unknown")
                config_info = f'connection to server at "{host}", port {port} failed for user "{user}"'
        
        # Determinar el tipo de error y formatear el mensaje
        if "password authentication failed" in error_lower or "access denied" in error_lower:
            if config_info:
                return f'CONNECTING DATABASE ERROR: {config_info}: FATAL: {error_str}'
            else:
                return f'CONNECTING DATABASE ERROR: FATAL: {error_str}'
        elif "could not connect" in error_lower or "connection refused" in error_lower or "timeout" in error_lower:
            if config_info:
                return f'CONNECTING DATABASE ERROR: {config_info}: {error_str}'
            else:
                return f'CONNECTING DATABASE ERROR: {error_str}'
        elif "connection" in error_lower or "connect" in error_lower:
            if config_info:
                return f'CONNECTING DATABASE ERROR: {config_info}: {error_str}'
            else:
                return f'CONNECTING DATABASE ERROR: {error_str}'
        elif "authentication" in error_lower or "auth" in error_lower:
            if config_info:
                return f'CONNECTING DATABASE ERROR: {config_info}: FATAL: {error_str}'
            else:
                return f'CONNECTING DATABASE ERROR: FATAL: {error_str}'
        else:
            if config_info:
                return f'CONNECTING DATABASE ERROR: {config_info}: {error_str}'
            else:
                return f'CONNECTING DATABASE ERROR: {error_str}'
    
    def _try_get_database_connection_error(self) -> Exception | None:
        """
        Intenta obtener el error real de conexión a la base de datos.
        Útil cuando is_db_connected() retorna False o db es None.
        
        Returns:
            Excepción de base de datos si se puede obtener, None en caso contrario
        """
        try:
            db_config = self.get_db_config()
            if not db_config:
                return None
            
            # Intentar conectar para obtener el error real
            dbtype = db_config.get("dbtype", "").lower()
            if dbtype == "sqlite":
                dbfile = db_config.get("dbfile", "app.db")
                if not dbfile.endswith(".db"):
                    dbfile = f"{dbfile}.db"
                test_db = SqliteDatabase(os.path.join(".", "db", dbfile))
            elif dbtype == "mysql":
                test_db = MySQLDatabase(
                    db_config.get("name", "app_db"),
                    host=db_config.get("host", "127.0.0.1"),
                    port=db_config.get("port", 3306),
                    user=db_config.get("user", "admin"),
                    password=db_config.get("password", "admin")
                )
            elif dbtype == "postgresql":
                test_db = PostgresqlDatabase(
                    db_config.get("name", "app_db"),
                    host=db_config.get("host", "127.0.0.1"),
                    port=db_config.get("port", 5432),
                    user=db_config.get("user", "admin"),
                    password=db_config.get("password", "admin")
                )
            else:
                return None
            
            # Intentar conectar para capturar el error
            test_db.connect()
            test_db.close()
            return None  # Si llegamos aquí, la conexión fue exitosa
        except (OperationalError, InterfaceError, DatabaseError) as e:
            return e
        except Exception as e:
            # Capturar cualquier otra excepción que pueda estar relacionada con la conexión
            error_str = str(e).lower()
            if any(keyword in error_str for keyword in ["connection", "connect", "database", "server", "authentication", "password", "timeout", "refused"]):
                # Crear una excepción genérica de base de datos para formatear
                return DatabaseError(str(e))
            return None
    
    @logging_error_handler
    @validate_types(output=bool)
    def is_db_connected(self):
        r"""
        Checks if the database connection is active.

        **Returns:**

        * **bool**: True if connected, False otherwise.

        **Usage:**

        ```python
        >>> from automation import PyAutomation
        >>> app = PyAutomation()
        >>> # Initially not connected
        >>> app.is_db_connected()
        False

        ```
        """
        """
        Lightweight check to know whether a live DB connection has been
        established for the current process.

        It intentionally does **not** attempt to connect or bootstrap
        configuration; it only reflects the current state of the DB manager.

        Connection attempts and configuration bootstrap are handled by:

        - ``ensure_db_config_from_env()`` (for first-run bootstrap), and
        - ``connect_to_db()`` / ``reconnect_to_db()``.
        """
        return bool(self.db_manager.get_db())

    @validate_types(test=bool|type(None), reload=bool|type(None), output=None|bool)
    def connect_to_db(self, test:bool=False, reload:bool=False):
        r"""
        Establishes a connection to the database based on the stored configuration.

        It also loads initial data like tags, roles, users, and OPC UA clients into memory.

        **Parameters:**

        * **test** (bool): If True, connects to a test SQLite database.
        * **reload** (bool): If True, reloads tags into the machine.

        **Returns:**

        * **bool**: True if connection was successful.

        **Usage:**

        ```python
        >>> from automation import PyAutomation
        >>> app = PyAutomation()
        >>> # Connect to test DB
        >>> app.connect_to_db(test=True)
        True
        >>> app.is_db_connected()
        True

        ```
        """
        str_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        try:
            db_config = self.get_db_config()

            logging.info(f"Connecting to database {db_config['dbtype']} with config: {db_config}")
            print(_colorize_message(f"[{str_date}] [INFO] Connecting to database {db_config['dbtype']} with config: {db_config}", "INFO"))
            # Para tests forzamos siempre una DB SQLite temporal.
            if test:
                db_config = {"dbtype": "sqlite", "dbfile": "test.db"}

            # Si no hay configuración y no estamos en modo test,
            # intentamos hacer bootstrap desde variables de entorno.
            if not test and not db_config:
                try:
                    self.ensure_db_config_from_env()
                    db_config = self.get_db_config()
                except Exception as env_err:
                    logging.warning(
                        f"Error while bootstrapping DB config from environment: {env_err}"
                    )
                    print(_colorize_message(f"[{str_date}] [WARNING] Error while bootstrapping DB config from environment: {env_err}", "WARNING"))

            if not db_config:
                logging.warning(
                    "No database configuration available (db_config.json not found "
                    "and no valid AUTOMATION_DB_* env vars). Skipping DB connection."
                )
                print(_colorize_message(f"[{str_date}] [WARNING] No database configuration available (db_config.json not found and no valid AUTOMATION_DB_* env vars). Skipping DB connection.", "WARNING"))
                return False

            # Normalizar tipos (especialmente el puerto) antes de set_db
            dbtype = db_config.pop("dbtype")
            if "port" in db_config:
                try:
                    if db_config["port"] is not None:
                        db_config["port"] = int(db_config["port"])
                except (TypeError, ValueError):
                    logging.warning(
                        f"Invalid port value in db_config ({db_config.get('port')}), "
                        "setting port=None."
                    )
                    print(_colorize_message(f"[{str_date}] [WARNING] Invalid port value in db_config ({db_config.get('port')}), setting port=None.", "WARNING"))
                    db_config["port"] = None

            self.__log_histories = True
            self.set_db(dbtype=dbtype, **db_config)
            # init_database crea tablas y aplica migraciones si corresponde
            self.db_manager.init_database()
            self.load_opcua_clients_from_db()
            self.load_db_to_cvt()
            self.load_db_to_alarm_manager()
            self.load_db_to_roles()
            self.load_db_to_users()
            if reload:
                self.load_db_tags_to_machine()
            logging.info(f"Database connected successfully")
            print(_colorize_message(f"[{str_date}] [INFO] Database connected successfully", "INFO"))
            return True

        except Exception as err:
            logging.critical(f"CONNECTING DATABASE ERROR: {err}")
            print(_colorize_message(f"[{str_date}] [CRITICAL] CONNECTING DATABASE ERROR: {err}", "CRITICAL"))
            return False
        
    @validate_types(test=bool|type(None), reload=bool|type(None), output=None|bool)
    def reconnect_to_db(self, test:bool=False):
        r"""
        Re-establishes the database connection and reloads all data.

        **Parameters:**

        * **test** (bool): If True, connects to test database.

        **Returns:**

        * **bool**: True if reconnection was successful.

        **Usage:**

        ```python
        >>> from automation import PyAutomation
        >>> app = PyAutomation()
        >>> app.connect_to_db(test=True)
        True
        >>> app.reconnect_to_db(test=True)
        True

        ```
        """
        try:
            db_config = self.get_db_config()

            if test:
                db_config = {"dbtype": "sqlite", "dbfile": "test.db"}

            if db_config:

                dbtype = db_config.pop("dbtype")
                if "port" in db_config:
                    try:
                        if db_config["port"] is not None:
                            db_config["port"] = int(db_config["port"])
                    except (TypeError, ValueError):
                        logging.warning(
                            f"Invalid port value in db_config ({db_config.get('port')}), "
                            "setting port=None."
                        )
                        db_config["port"] = None

                self.__log_histories = True
                self.set_db(dbtype=dbtype, **db_config) 
                self.db_manager.init_database()   
                self.load_opcua_clients_from_db()
                self.load_db_to_cvt()
                self.load_db_to_alarm_manager()
                self.load_db_to_roles()
                self.load_db_to_users()
                self.load_db_tags_to_machine()            

                return True
            else:
                return False
        
        except Exception as err:
            self.db_manager._logger.logger._db = None
            return False

    @logging_error_handler
    @validate_types(output=None)
    def disconnect_to_db(self):
        r"""
        Closes the database connection and stops history logging.

        **Usage:**

        ```python
        >>> from automation import PyAutomation
        >>> app = PyAutomation()
        >>> app.connect_to_db(test=True)
        True
        >>> app.disconnect_to_db()
        >>> app.is_db_connected()
        False

        ```
        """
        self.__log_histories = False
        self.db_manager._logger.logger.stop_db()
        str_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        logging.info(f"Database disconnected successfully")
        print(_colorize_message(f"[{str_date}] [INFO] Database disconnected successfully", "INFO"))

    @logging_error_handler
    @validate_types(output=None)
    def load_db_to_cvt(self):
        r"""
        Loads active tags from the database into the Current Value Table (CVT).

        **Usage:**

        ```python
        >>> from automation import PyAutomation
        >>> app = PyAutomation()
        >>> app.connect_to_db(test=True)
        True
        >>> # Create a tag to persist it
        >>> tag, _ = app.create_tag("Tag_Load_Test", "m", "Length")
        >>> # Clear memory to simulate restart
        >>> app.cvt._cvt.tags = {} 
        >>> app.load_db_to_cvt()
        >>> app.get_tag_by_name("Tag_Load_Test") is not None
        True

        ```
        """
        if self.is_db_connected():

            tags = self.db_manager.get_tags()
            str_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            # Asegurar que tags sea siempre una lista
            if tags is None:
                tags = []
            elif not isinstance(tags, list):
                tags = list(tags) if tags else []

            for tag in tags:

                active = tag.pop("active")

                if active:
                    # Si el tag tiene opcua_client_name pero no opcua_address, resolver la URL
                    if tag.get("opcua_client_name") and not tag.get("opcua_address"):
                        client_name = tag.get("opcua_client_name")
                        client = self.opcua_client_manager.get(client_name)
                        if client:
                            tag["opcua_address"] = client.serialize().get("server_url")
                    
                    logging.info(f"Loading tag {tag['name']} from database")
                    print(_colorize_message(f"[{str_date}] [INFO] Loading tag {tag['name']} from database", "INFO"))
                    self.create_tag(reload=True, **tag)
                    logging.info(f"Tag {tag['name']} loaded from database")
                    print(_colorize_message(f"[{str_date}] [INFO] Tag {tag['name']} loaded from database", "INFO"))

    @logging_error_handler
    @validate_types(output=None)
    def load_db_to_alarm_manager(self):
        r"""
        Loads configured alarms from the database into the Alarm Manager.

        **Usage:**

        ```python
        >>> from automation import PyAutomation
        >>> app = PyAutomation()
        >>> app.connect_to_db(test=True)
        True
        >>> _ = app.create_tag("Tag_Alarm_Load", "m", "Length")
        >>> _, _ = app.create_alarm("Alarm_Load_Test", "Tag_Alarm_Load")
        >>> # Manually clear alarms in memory to test load
        >>> app.alarm_manager.alarms = {}
        >>> app.load_db_to_alarm_manager()
        >>> app.get_alarm_by_name("Alarm_Load_Test") is not None
        True

        ```
        """
        str_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        logging.info(f"Loading alarms from database")
        print(_colorize_message(f"[{str_date}] [INFO] Loading alarms from database", "INFO"))
        if self.is_db_connected():

            alarms = self.db_manager.get_alarms() or list()
            logging.info(f"{len(alarms)} alarms found in database")
            print(_colorize_message(f"[{str_date}] [INFO] {len(alarms)} alarms found in database", "INFO"))
            if alarms:
                for alarm in alarms:

                    self.create_alarm(reload=True, **alarm)
                    logging.info(f"Alarm {alarm['name']} loaded from database")
                    print(_colorize_message(f"[{str_date}] [INFO] Alarm {alarm['name']} loaded from database", "INFO"))
            else:
                logging.info(f"No alarms found in database")
                print(_colorize_message(f"[{str_date}] [INFO] No alarms found in database", "INFO"))

    @logging_error_handler
    @validate_types(output=None)
    def load_db_to_roles(self):
        r"""
        Loads user roles from the database into the system's role manager.

        **Usage:**

        ```python
        >>> from automation import PyAutomation
        >>> from automation.dbmodels.users import Roles
        >>> app = PyAutomation()
        >>> app.connect_to_db(test=True)
        True
        >>> _ = app.set_role("new_role", 5)
        >>> # Clear roles memory
        >>> Roles.get_all_roles().pop("new_role", None)
        >>> app.load_db_to_roles()
        >>> "new_role" in Roles.get_all_roles()
        True

        ```
        """
        str_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        logging.info(f"Loading roles from database")
        print(_colorize_message(f"[{str_date}] [INFO] Loading roles from database", "INFO"))
        if self.is_db_connected():

            Roles.fill_cvt_roles()
            logging.info(f"Roles loaded from database")
            print(_colorize_message(f"[{str_date}] [INFO] Roles loaded from database", "INFO"))

    @logging_error_handler
    @validate_types(output=None)
    def load_db_to_users(self):
        r"""
        Loads users from the database into the system's user manager.

        **Usage:**

        ```python
        >>> from automation import PyAutomation
        >>> from automation.modules.users.users import users
        >>> app = PyAutomation()
        >>> app.connect_to_db(test=True)
        True
        >>> _ = app.set_role("user_role", 1)
        >>> _ = app.signup("new_user", "user_role", "u@test.com", "pass")
        >>> # Clear users memory
        >>> users._Users__by_username.pop("new_user", None)
        >>> app.load_db_to_users()
        >>> users.get_by_username("new_user") is not None
        True

        ```
        """
        str_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        logging.info(f"Loading users from database")
        print(_colorize_message(f"[{str_date}] [INFO] Loading users from database", "INFO"))
        if self.is_db_connected():

            Users.fill_cvt_users()
            logging.info(f"Users loaded from database")
            print(_colorize_message(f"[{str_date}] [INFO] Users loaded from database", "INFO"))
    
    @logging_error_handler
    @validate_types(output=None)
    def load_opcua_clients_from_db(self):
        r"""
        Loads OPC UA client configurations from the database and initializes them.
        """
        str_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        logging.info(f"Loading OPC UA clients from database")
        print(_colorize_message(f"[{str_date}] [INFO] Loading OPC UA clients from database", "INFO"))
        if self.is_db_connected():

            clients = self.db_manager.get_opcua_clients()
            logging.info(f"{len(clients)} OPC UA clients found in database")
            if len(clients)>0:
                
                print(_colorize_message(f"[{str_date}] [INFO] {len(clients)} OPC UA clients found in database", "INFO"))
            else:
                print(_colorize_message(f"[{str_date}] [WARNING] No OPC UA clients found in database", "WARNING"))
            
            for client in clients:
                client_name = client.get('client_name')
                # Intentar agregar el cliente, incluso si falla la conexión
                # Esto asegura que esté en memoria para poder actualizarlo
                result = self.add_opcua_client(**client)
                if result:
                    success, message = result
                    if success:
                        logging.info(f"OPC UA client {client_name} loaded from database and connected")
                        print(_colorize_message(f"[{str_date}] [INFO] OPC UA client {client_name} loaded from database and connected", "INFO"))
                    else:
                        # Cliente agregado a memoria pero no conectado
                        logging.warning(f"OPC UA client {client_name} loaded from database but not connected: {message}")
                        print(_colorize_message(f"[{str_date}] [WARNING] OPC UA client {client_name} loaded from database but not connected: {message}", "WARNING"))
                else:
                    # Si add_opcua_client retorna None, intentar agregar directamente al manager
                    # para asegurar que esté en memoria aunque no se conecte
                    try:
                        self.opcua_client_manager.add(client_name=client_name, host=client.get('host'), port=client.get('port'))
                        logging.warning(f"OPC UA client {client_name} added to memory from database (connection may have failed)")
                        print(_colorize_message(f"[{str_date}] [WARNING] OPC UA client {client_name} added to memory from database (connection may have failed)", "WARNING"))
                    except Exception as e:
                        logging.error(f"Failed to load OPC UA client {client_name} from database: {e}")
                        print(_colorize_message(f"[{str_date}] [ERROR] Failed to load OPC UA client {client_name} from database: {e}", "ERROR"))

    @logging_error_handler
    def load_db_tags_to_machine(self):
        r"""
        Loads tag subscriptions for state machines from the database.
        """
        str_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        logging.info(f"Loading tag subscriptions for state machines from database")
        print(_colorize_message(f"[{str_date}] [INFO] Loading tag subscriptions for state machines from database", "INFO"))
        machines = self.machine_manager.get_machines()


        for machine, _, _ in machines:
            logging.info(f"Loading tag subscriptions for state machine {machine.name.value} from database")
            print(_colorize_message(f"[{str_date}] [INFO] Loading tag subscriptions for state machine {machine.name.value} from database", "INFO"))

            if machine.classification.value.lower()!="data acquisition system":

                machine_name = machine.name.value
                machine_db = Machines.get_or_none(name=machine_name)
                
                if not machine_db:

                    return f"{machine_name} not found into DB", 404
                
                machine.identifier.value = machine_db.identifier
                logging.info(f"State machine {machine.name.value} identifier set to {machine.identifier.value} from database")
                print(_colorize_message(f"[{str_date}] [INFO] State machine {machine.name.value} identifier set to {machine.identifier.value} from database", "INFO"))
                tags_machine = machine_db.get_tags()
                logging.info(f"{len(tags_machine)} tags found for state machine {machine.name.value} in database")
                print(_colorize_message(f"[{str_date}] [INFO] {len(tags_machine)} tags found for state machine {machine.name.value} in database", "INFO"))
                for tag_machine in tags_machine:

                    logging.info(f"Loading tag {tag_machine.name} from database")
                    print(_colorize_message(f"[{str_date}] [INFO] Loading tag {tag_machine.name} from database", "INFO"))
                    _tag = tag_machine.serialize()
                    tag_name = _tag["tag"]["name"]
                    tag = self.cvt.get_tag_by_name(name=tag_name)
                    machine.subscribe_to(tag=tag, default_tag_name=_tag["default_tag_name"])
                    logging.info(f"Tag {tag_machine.name} loaded from database")
                    print(_colorize_message(f"[{str_date}] [INFO] Tag {tag_machine.name} loaded from database", "INFO"))
            else:
                logging.info(f"State machine {machine.name.value} is a data acquisition system, skipping tag subscriptions")
                print(_colorize_message(f"[{str_date}] [INFO] State machine {machine.name.value} is a data acquisition system, skipping tag subscriptions", "INFO"))
                machine_name = machine.name.value
                machine_db = Machines.get_or_none(name=machine_name)
                machine.identifier.value = machine_db.identifier

    @logging_error_handler
    def add_db_table(self, table:BaseModel):
        r"""
        Registers a new table model in the database manager.

        **Parameters:**

        * **table** (BaseModel): The Peewee model class to register.

        **Usage:**

        ```python
        >>> from automation import PyAutomation
        >>> from peewee import CharField
        >>> from automation.dbmodels.core import BaseModel
        >>> class MyTable(BaseModel):
        ...     name = CharField()
        >>> app = PyAutomation()
        >>> app.add_db_table(MyTable)
        >>> app.get_db_table("MyTable") is not None
        True

        ```
        """
        self.db_manager.register_table(table)

    @logging_error_handler
    def get_db_table(self, tablename:str):
        r"""
        Retrieves a registered database table model by its name.

        **Parameters:**

        * **tablename** (str): The name of the table.

        **Returns:**

        * **Model**: The Peewee model class.

        **Usage:**

        ```python
        >>> from automation import PyAutomation
        >>> app = PyAutomation()
        >>> # Assuming 'Users' table is registered by default
        >>> table = app.get_db_table("Users")
        >>> table is not None
        True

        ```
        """
        return self.db_manager.get_db_table(tablename=tablename)

    # ALARMS METHODS
    @logging_error_handler
    @validate_types(output=AlarmManager)
    def get_alarm_manager(self)->AlarmManager:
        r"""
        Returns the Alarm Manager instance.

        **Usage:**

        ```python
        >>> from automation import PyAutomation
        >>> app = PyAutomation()
        >>> manager = app.get_alarm_manager()
        >>> manager is not None
        True

        ```
        """
        return self.alarm_manager

    @logging_error_handler
    @validate_types(
            name=str,
            tag=str,
            alarm_type=str,
            trigger_value=bool|float|int,
            description=str|type(None),
            identifier=str|type(None),
            state=str,
            timestamp=str|type(None),
            ack_timestamp=str|type(None),
            user=User|type(None),
            reload=bool,
            output=(Alarm, str)
    )
    def create_alarm(
            self,
            name:str,
            tag:str,
            alarm_type:str="BOOL",
            trigger_value:bool|float|int=True,
            description:str="",
            identifier:str=None,
            state:str="Normal",
            timestamp:str=None,
            ack_timestamp:str=None,
            user:User=None,
            reload:bool=False
        )->tuple[Alarm, str]:
        r"""
        Creates and registers a new alarm in the system.

        **Parameters:**

        * **name** (str): Alarm name.
        * **tag** (str): Name of the tag to monitor.
        * **alarm_type** (str): Trigger type (e.g., 'BOOL', 'HI', 'LO').
        * **trigger_value** (bool|float|int): Value that triggers the alarm.
        * **description** (str, optional): Alarm description.
        * **user** (User, optional): User creating the alarm.

        **Returns:**

        * **tuple[Alarm, str]**: Created Alarm object and status message.

        **Usage:**

        ```python
        >>> from automation import PyAutomation
        >>> app = PyAutomation()
        >>> _ = app.create_tag(name="TankLevel", unit="m", variable="Length")
        >>> # Create a High Level Alarm
        >>> alarm, msg = app.create_alarm(
        ...     name="ALM_HI_LEVEL",
        ...     tag="TankLevel",
        ...     alarm_type="HI",
        ...     trigger_value=8.5,
        ...     description="High level detected in tank"
        ... )
        >>> alarm.name
        'ALM_HI_LEVEL'
        >>> alarm.trigger_value
        8.5
        ```
        """
        alarm, message = self.alarm_manager.append_alarm(
            name=name,
            tag=tag,
            type=alarm_type,
            trigger_value=trigger_value,
            description=description,
            identifier=identifier,
            state=state,
            timestamp=timestamp,
            ack_timestamp=ack_timestamp,
            user=user,
            reload=reload,
            sio=self.sio
        )

        if alarm:

            # Persist Tag on Database
            if not reload:
                if self.is_db_connected():
                    
                    alarm = self.alarm_manager.get_alarm_by_name(name=name)
                    
                    self.alarms_engine.create(
                        id=alarm.identifier,
                        name=name,
                        tag=tag,
                        trigger_type=alarm_type,
                        trigger_value=trigger_value,
                        description=description
                    )
            
            return alarm, message

        return None, message

    @logging_error_handler
    @validate_types(lasts=int, output=list)
    def get_lasts_alarms(self, lasts:int=10)->list:
        r"""
        Retrieves the last N alarms recorded in history.

        **Parameters:**

        * **lasts** (int): Number of records to retrieve.

        **Returns:**

        * **list**: List of alarm records.

        **Usage:**

        ```python
        >>> from automation import PyAutomation
        >>> app = PyAutomation()
        >>> app.connect_to_db(test=True)
        True
        >>> alarms = app.get_lasts_alarms(5)
        >>> isinstance(alarms, list)
        True

        ```
        """
        if self.is_db_connected():
            
            return self.alarms_engine.get_lasts(lasts=lasts)
        
        return list()

    @logging_error_handler
    def filter_alarms_by(self, **fields):
        r"""
        Filters alarm history based on provided fields.

        **Parameters:**

        * **fields**: Keyword arguments for filtering (e.g., name, tag, state).

        **Returns:**

        * **list**: Filtered list of alarms.

        **Usage:**

        ```python
        >>> from automation import PyAutomation
        >>> app = PyAutomation()
        >>> # Assuming database is already connected
        >>> # Filter by alarm names (returns dict with data and pagination)
        >>> alarms = app.filter_alarms_by(names=["NonExistentAlarm"])
        >>> isinstance(alarms, dict)
        True
        >>> isinstance(alarms['data'], list)
        True

        ```
        """
        if self.is_db_connected():
            
            # Ensure pagination parameters are present or defaulted
            if 'page' not in fields: fields['page'] = 1
            if 'limit' not in fields: fields['limit'] = 20

            return self.alarms_engine.filter_alarm_summary_by(**fields)

    @logging_error_handler
    @validate_types(id=str, name=str|None, tag=str|None, description=str|None, alarm_type=str|None, trigger_value=int|float|None, output=None)
    def update_alarm(
            self, 
            id:str, 
            name:str=None,
            tag:str=None,
            description:str=None,
            alarm_type:str=None,
            trigger_value:int|float=None)->None:
        r"""
        Updates the properties of an existing alarm.

        **Parameters:**

        * **id** (str): Alarm ID.
        * **name** (str, optional): New name.
        * **tag** (str, optional): New associated tag.
        * **description** (str, optional): New description.
        * **alarm_type** (str, optional): New type.
        * **trigger_value** (int|float, optional): New trigger value.

        **Usage:**

        ```python
        >>> from automation import PyAutomation
        >>> app = PyAutomation()
        >>> _ = app.create_tag("Tag_Alarm_Upd", "bar", "Pressure")
        >>> alarm, _ = app.create_alarm("Alarm_Upd", "Tag_Alarm_Upd", trigger_value=10.0)
        >>> app.update_alarm(alarm.identifier, trigger_value=20.0, description="Updated limit")
        >>> updated_alarm = app.get_alarm(alarm.identifier)
        >>> updated_alarm.trigger_value
        20.0
        >>> updated_alarm.description
        'Updated limit'

        ```
        """
        self.alarm_manager.put(
            id=id,
            name=name,
            tag=tag,
            description=description,
            alarm_type=alarm_type,
            trigger_value=trigger_value
        )
        # Persist Tag on Database
        if self.is_db_connected():

            self.alarms_engine.put(
                id=id,
                name=name,
                tag=tag,
                description=description,
                alarm_type=alarm_type,
                trigger_value=trigger_value)

    @logging_error_handler
    @validate_types(id=str, output=Alarm)
    def get_alarm(self, id:str)->Alarm:
        r"""
        Retrieves an alarm object by its ID.

        **Parameters:**

        * **id** (str): Alarm ID.

        **Returns:**

        * **Alarm**: The Alarm object.

        **Usage:**

        ```python
        >>> from automation import PyAutomation
        >>> app = PyAutomation()
        >>> _ = app.create_tag("Tag_Get_Alm", "m", "Length")
        >>> alarm, _ = app.create_alarm("Get_Alm_1", "Tag_Get_Alm")
        >>> fetched_alarm = app.get_alarm(alarm.identifier)
        >>> fetched_alarm.name
        'Get_Alm_1'

        ```
        """
        return self.alarm_manager.get_alarm(id=id)

    @logging_error_handler
    @validate_types(output=dict)
    def get_alarms(self)->dict:
        r"""
        Retrieves all currently active alarms in memory.

        **Returns:**

        * **dict**: Dictionary of Alarm objects.

        **Usage:**

        ```python
        >>> from automation import PyAutomation
        >>> app = PyAutomation()
        >>> _ = app.create_tag("Tag_Alarm_List", "m", "Length")
        >>> _, _ = app.create_alarm("Alarm_List_1", "Tag_Alarm_List")
        >>> alarms = app.get_alarms()
        >>> "Alarm_List_1" in [a.name for a in alarms.values()]
        True

        ```
        """
        return self.alarm_manager.get_alarms()
    
    @logging_error_handler
    @validate_types(output=list)
    def serialize_alarms(self)->list:
        r"""
        Serializes all alarms into a list of dictionaries.

        **Returns:**

        * **list**: Serialized alarm data.
        """
        result = list()
        for _, alarm in self.alarm_manager.get_alarms().items():

            result.append(alarm.serialize())

        return result

    @logging_error_handler
    @validate_types(lasts=int|None, output=list)
    def get_lasts_active_alarms(self, lasts:int=None)->list:
        r"""
        Retrieves the most recent active (unacknowledged or active state) alarms.

        **Parameters:**

        * **lasts** (int, optional): Limit number of results.

        **Returns:**

        * **list**: List of active alarms.
        """
        return self.alarm_manager.get_lasts_active_alarms(lasts=lasts) or list()

    @logging_error_handler
    @validate_types(name=str, output=Alarm)
    def get_alarm_by_name(self, name:str)->Alarm:
        r"""
        Retrieves an alarm by its name.

        **Parameters:**

        * **name** (str): Alarm name.

        **Returns:**

        * **Alarm**: The Alarm object.
        """
        return self.alarm_manager.get_alarm_by_name(name=name)

    @logging_error_handler
    @validate_types(tag=str, output=list)
    def get_alarms_by_tag(self, tag:str)->list:
        r"""
        Retrieves all alarms associated with a specific tag.

        **Parameters:**

        * **tag** (str): Tag name.

        **Returns:**

        * **list**: List of Alarm objects.
        """
        return self.alarm_manager.get_alarms_by_tag(tag=tag)

    @logging_error_handler
    @validate_types(id=str, user=User|type(None), output=None)
    def delete_alarm(self, id:str, user:User=None):
        r"""
        Deletes an alarm from the system.

        **Parameters:**

        * **id** (str): Alarm ID.
        * **user** (User, optional): User performing the deletion.
        """
        self.alarm_manager.delete_alarm(id=id, user=user)
        if self.is_db_connected():

            self.alarms_engine.delete(id=id)

    # EVENTS METHODS
    @logging_error_handler
    @validate_types(lasts=int, output=list)
    def get_lasts_events(self, lasts:int=10)->list:
        r"""
        Retrieves the last N system events.

        **Parameters:**

        * **lasts** (int): Number of events to retrieve.

        **Returns:**

        * **list**: List of event dictionaries.

        **Usage:**

        ```python
        >>> from automation import PyAutomation
        >>> app = PyAutomation()
        >>> events = app.get_lasts_events(5)
        >>> isinstance(events, list)
        True

        ```
        """
        if self.is_db_connected():

            return self.events_engine.get_lasts(lasts=lasts)
        
        return list()

    @logging_error_handler
    def filter_events_by(
            self,
            usernames:list[str]=None,
            priorities:list[int]=None,
            criticities:list[int]=None,
            message:str="",
            classification:str="",
            description:str="",
            greater_than_timestamp:datetime=None,
            less_than_timestamp:datetime=None,
            timezone:str="UTC",
            page:int=1,
            limit:int=20)->list:
        r"""
        Filters system events based on multiple criteria.

        **Parameters:**

        * **usernames** (list[str]): Filter by user.
        * **priorities** (list[int]): Filter by priority level.
        * **criticities** (list[int]): Filter by criticity level.
        * **message** (str): Text search in message.
        * **classification** (str): Filter by event classification.
        * **timezone** (str): Timezone for timestamp filtering.
        * **page**, **limit**: Pagination parameters.

        **Returns:**

        * **list**: Filtered list of events.
        """
        if self.is_db_connected():
            
            return self.events_engine.filter_by(
                usernames=usernames,
                priorities=priorities,
                criticities=criticities,
                message=message,
                description=description,
                classification=classification,
                greater_than_timestamp=greater_than_timestamp,
                less_than_timestamp=less_than_timestamp,
                timezone=timezone,
                page=page,
                limit=limit
            )
        
        return list()
        
    # LOGS METHODS
    @logging_error_handler
    def create_log(
        self, 
        message:str, 
        user:User, 
        description:str=None, 
        classification:str=None,
        alarm_summary_id:int=None,
        event_id:int=None,
        timestamp:datetime=None
        )->tuple:
        r"""
        Creates a new log entry.

        **Parameters:**

        * **message** (str): Log message.
        * **user** (User): User associated with the log.
        * **description** (str, optional): Detailed description.
        * **classification** (str, optional): Log category.

        **Returns:**

        * **tuple**: Created log object and status message.

        **Usage:**

        ```python
        >>> from automation import PyAutomation
        >>> from automation.modules.users.users import User
        >>> from automation.modules.users.roles import Role
        >>> app = PyAutomation()
        >>> # Mock user for logging
        >>> role = Role(name="logger_role", level=1)
        >>> user = User(username="logger_test", email="log@test.com", role=role, password="password")
        >>> # Example of log creation (requires active DB connection)
        >>> # if app.is_db_connected():
        >>> #     log, msg = app.create_log("System started", user)
        >>> #     print(log.message)
        >>> # 'System started'
        ```
        """
        if self.is_db_connected():
            
            log, message = self.logs_engine.create(
                message=message, 
                user=user, 
                description=description, 
                classification=classification,
                alarm_summary_id=alarm_summary_id,
                event_id=event_id,
                timestamp=timestamp
            )

            if log and self.sio:

                self.sio.emit("on.log", data=log.serialize())

            return log, message
        
        return None, "Logs DB is not up"
        
    @logging_error_handler
    def filter_logs_by(
            self,
            usernames:list[str]=None,
            alarm_names:list[str]=None,
            event_ids:list[int]=None,
            classification:str="",
            message:str="",
            description:str="",
            greater_than_timestamp:datetime=None,
            less_than_timestamp:datetime=None,
            timezone:str="UTC",
            page:int=1,
            limit:int=20
        )->dict:
        r"""
        Filters system logs based on criteria with pagination.

        **Parameters:**

        * **usernames** (list[str]): Filter by user.
        * **alarm_names** (list[str]): Filter by linked alarm names.
        * **event_ids** (list[int]): Filter by linked event IDs.
        * **classification** (str): Filter by category.
        * **message** (str): Partial match message.
        * **description** (str): Partial match description.
        * **greater_than_timestamp** (datetime): Start time.
        * **less_than_timestamp** (datetime): End time.
        * **timezone** (str): Timezone.
        * **page** (int): Page number for pagination.
        * **limit** (int): Items per page.

        **Returns:**

        * **dict**: {data: list, pagination: dict}
        """
        if self.is_db_connected():

            return self.logs_engine.filter_by(
                usernames=usernames,
                alarm_names=alarm_names,
                event_ids=event_ids,
                classification=classification,
                message=message,
                description=description,
                greater_than_timestamp=greater_than_timestamp,
                less_than_timestamp=less_than_timestamp,
                timezone=timezone,
                page=page,
                limit=limit
            )
        
    @logging_error_handler
    @validate_types(lasts=int, output=list)
    def get_lasts_logs(self, lasts:int=10)->list:
        r"""
        Retrieves the last N logs.

        **Parameters:**

        * **lasts** (int): Number of logs to retrieve.

        **Returns:**

        * **list**: List of log entries.
        """
        if self.is_db_connected():

            return self.logs_engine.get_lasts(lasts=lasts) or list()
        
        return list()

    # INIT APP
    @logging_error_handler
    def run(self, server:Flask, debug:bool=False, test:bool=False, create_tables:bool=False, machines:tuple=None, certfile:str=None, keyfile:str=None)->None:
        r"""
        Starts the PyAutomation application.

        Initializes the logger, database connections, and worker threads.

        **Parameters:**

        * **debug** (bool): Enable debug mode for Dash server.
        * **test** (bool): Run in test mode (using test DB).
        * **create_tables** (bool): Create database tables on startup.
        * **machines** (tuple, optional): Initial state machines to run.

        **Returns:** `None`

        **Usage:**

        ```python
        # Standard execution
        # from automation import PyAutomation
        # app = PyAutomation()
        # if __name__ == "__main__":
        #     app.run(debug=True, create_tables=True)
        ```
        """
        str_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.define_socketio(server=server, certfile=certfile, keyfile=keyfile)
        logging.info(f"Starting app with configuration:")
        logging.info(f"Logger period: {self.get_app_config().get('logger_period', 10.0)} seconds")
        logging.info(f"Log max bytes: {self.get_app_config().get('log_max_bytes', 10 * 1024 * 1024)} bytes")
        logging.info(f"Log backup count: {self.get_app_config().get('log_backup_count', 3)} backups")
        logging.info(f"Log level: {self.get_app_config().get('log_level', 20)}")
        print(_colorize_message(f"[{str_date}] [INFO] Starting app with configuration:", "INFO"))
        print(_colorize_message(f"[{str_date}] [INFO] Logger period: {self.get_app_config().get('logger_period', 10.0)} seconds", "INFO"))
        print(_colorize_message(f"[{str_date}] [INFO] Log max bytes: {self.get_app_config().get('log_max_bytes', 10 * 1024 * 1024)} bytes", "INFO"))
        print(_colorize_message(f"[{str_date}] [INFO] Log backup count: {self.get_app_config().get('log_backup_count', 3)} backups", "INFO"))
        print(_colorize_message(f"[{str_date}] [INFO] Log level: {self.get_app_config().get('log_level', 20)}", "INFO"))

        # Start workers (logger, DB worker, state machines)
        self.safe_start(test=test, create_tables=create_tables, machines=machines)

        # After safe_start, the DB may still not be connected (e.g. DB container
        # was not ready on first attempt). Try one more time to ensure that:
        # - env-based bootstrap has a chance to run, and
        # - a connection is established before creating the system user.
        if not self.is_db_connected():
            # Bootstrap from env if needed (no-op if db_config.json already exists)
            self.ensure_db_config_from_env()
            # Attempt to connect using the current configuration
            self.connect_to_db(test=test)

        if self.is_db_connected():
            self.create_system_user()
        else:
            logging.critical("Database is not connected, skipping system user creation")
            print(_colorize_message(f"[{str_date}] [CRITICAL] Database is not connected, skipping system user creation", "CRITICAL"))

    @logging_error_handler
    def create_system_user(self):
        r"""
        Ensures a 'system' user exists with 'sudo' role. Used for automated internal actions.
        """
        # Create system user
        users = Users()
        roles = Roles()
        system_password = self.server.config.get("AUTOMATION_SUPERUSER_PASSWORD", "super_ultra_secret_password")
        
        # Verificar si el usuario system existe
        if not users.read_by_username(username="system"):
            # Obtener el rol de administrador
            admin_role = roles.read_by_name(name="sudo")
            if admin_role:
                # Generar password e identificador dinámicamente
                self.signup(
                    username="system",
                    role_name="sudo",
                    email="system@intelcon.com",
                    password=system_password,
                    name="System",
                    lastname="Intelcon"
                )
        else:

            self.reset_password(target_username="system", new_password=system_password)

    @logging_error_handler
    def safe_start(self, test:bool=False, create_tables:bool=True, machines:tuple=None):
        r"""
        Initializes app components without blocking the main thread.
        
        Used by `run()` and for testing.
        """
        self._create_tables = create_tables
        self.__start_logger()
        self.__start_workers(test=test, machines=machines)
        str_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        logging.info(f"App started successfully")
        print(_colorize_message(f"[{str_date}] [INFO] App started successfully", "INFO"))

    @logging_error_handler
    @validate_types(period=float, output=None)
    def update_logger_period(self, period:float):
        r"""
        Updates the interval for the data logger worker.

        **Parameters:**

        * **period** (float): New interval in seconds.
        """
        if hasattr(self, 'db_worker'):
            self.db_worker._period = period
            str_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            logging.info(f"Logger period updated to {period} seconds")
            print(f"[INFO] {str_date} Logger period updated to {period} seconds")
        
        self.set_app_config(logger_period=period)

    @logging_error_handler
    @validate_types(output=None)
    def safe_stop(self)->None:
        r"""
        Stops the application and all worker threads gracefully.
        """
        self.__stop_workers()

    @logging_error_handler
    def state_machine_diagrams(self, folder_path:str):
        r"""
        Generates and saves state diagrams for all active state machines.

        **Parameters:**

        * **folder_path** (str): Destination directory for PNG images.
        """
        for machine, _, _ in self._manager.get_machines():
            # SAVE STATE DIAGRAM
            img_path = f"{folder_path}{machine.name.value}.png"
            machine._graph().write_png(img_path)

    # WORKERS
    @logging_error_handler
    def __start_workers(self, test:bool=False, machines:tuple=None)->None:
        r"""
        Starts all background worker threads (Logger, StateMachines, DAS).
        """
        if self._create_tables:
            
            app_config = self.get_app_config()
            logger_period = float(app_config.get("logger_period", 10.0))

            self.db_worker = LoggerWorker(self.db_manager, period=logger_period)

            # Bootstrap DB configuration from environment variables on first run,
            # but once db_config.json exists, it will override any env changes.
            self.ensure_db_config_from_env()

            self.connect_to_db(test=test)
            self.db_worker.start()

        if machines:

            for machine in machines:
            
                machine.set_socketio(sio=self.sio)
 
        self.machine.start(machines=machines)
        
        if self.is_db_connected():
            
            self.load_db_tags_to_machine()

        self.is_starting = False

    @logging_error_handler
    @validate_types(output=None)
    def __stop_workers(self)->None:
        r"""
        Signals all worker threads to stop.
        """
        self.machine.stop()
        self.db_worker.stop()
        if hasattr(self, 'subscription_monitor'):
            self.subscription_monitor.stop()

    @logging_error_handler
    @validate_types(level=int, output=None)
    def update_log_level(self, level:int):
        r"""
        Updates logger level dynamically and persists it.

        **Parameters:**

        * **level** (int): New logging level.
        """
        self._logging_level = level
        
        # Update root logger
        root_logger = logging.getLogger()
        root_logger.setLevel(level)
        
        # Update app logger
        app_logger = logging.getLogger("pyautomation")
        app_logger.setLevel(level)
        
        logging.log(level, f"Log level updated to {level}")
        
        # Persist to config
        self.set_app_config(log_level=level)

    @logging_error_handler
    @validate_types(max_bytes=int, backup_count=int, output=None)
    def update_log_config(self, max_bytes:int, backup_count:int):
        r"""
        Updates logger rotation configuration dynamically and persists it.

        **Parameters:**

        * **max_bytes** (int): Max size per log file.
        * **backup_count** (int): Number of backups to keep.
        """
        # 1. Update runtime logger
        root_logger = logging.getLogger()
        for handler in root_logger.handlers:
            if isinstance(handler, RotatingFileHandler):
                # Update handler properties
                handler.maxBytes = max_bytes
                handler.backupCount = backup_count
                # Trigger rollover if needed (optional, or wait for next write)
                # handler.doRollover() 
                str_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                logging.info(f"Log configuration updated: maxBytes={max_bytes}, backupCount={backup_count}")
                print(f"[INFO] {str_date} Log configuration updated: maxBytes={max_bytes}, backupCount={backup_count}")
                break
        
        # 2. Persist to config
        self.set_app_config(log_max_bytes=max_bytes, log_backup_count=backup_count)

    @logging_error_handler
    @validate_types(output=None)
    def __start_logger(self)->None:
        r"""
        Initializes and configures the logging system.
        """

        requests.urllib3.disable_warnings()
        urllib3.disable_warnings()
        logging.getLogger("urllib3").setLevel(logging.WARNING)
        logging.getLogger("requests").setLevel(logging.WARNING)
        logging.getLogger('peewee').setLevel(logging.WARNING)
        logging.getLogger('opcua').setLevel(logging.CRITICAL)
        # Configure root logger with rotating file handler (size-based)
        root_logger = logging.getLogger()
        
        # Load level from config
        app_config = self.get_app_config()
        # Default logging.INFO (20) if not set in config, overriding __init__ warning default
        persisted_level = int(app_config.get('log_level', logging.INFO))
        self._logging_level = persisted_level
        
        root_logger.setLevel(self._logging_level)
        # Clear existing handlers to avoid duplicates
        for _h in list(root_logger.handlers):
            root_logger.removeHandler(_h)

        app_config = self.get_app_config()
        # Default fallback to env or hardcoded
        env_max_bytes = int(os.environ.get('AUTOMATION_LOG_MAX_BYTES', 10 * 1024 * 1024))
        env_backup_count = int(os.environ.get('AUTOMATION_LOG_BACKUP_COUNT', 3))

        max_bytes = int(app_config.get('log_max_bytes', env_max_bytes))
        backup_count = int(app_config.get('log_backup_count', env_backup_count))

        handler = RotatingFileHandler(
            filename=self._log_file,
            maxBytes=max_bytes,
            backupCount=backup_count,
            encoding="utf-8",
        )
        log_format = "%(asctime)s:%(levelname)s:%(message)s"
        formatter = logging.Formatter(log_format)
        handler.setFormatter(formatter)
        root_logger.addHandler(handler)

        # Ensure named logger propagates to root (no extra handler to avoid duplicates)
        app_logger = logging.getLogger("pyautomation")
        app_logger.setLevel(self._logging_level)
        app_logger.propagate = True

    @logging_error_handler
    @validate_types(output=dict)
    def export_configuration(self)->dict:
        r"""
        Exports all configuration data from database models (excluding historical data).

        Exports configuration tables: Manufacturer, Segment, Variables, Units, DataTypes,
        Tags, AlarmTypes, AlarmStates, Alarms, Roles, Users, OPCUA, AccessType,
        OPCUAServer, Machines, TagsMachines.

        Excludes historical tables: TagValue, Events, Logs, AlarmSummary.

        **Returns:**

        * **dict**: Dictionary containing all configuration data organized by model name.

        **Usage:**

        ```python
        >>> from automation import PyAutomation
        >>> app = PyAutomation()
        >>> app.connect_to_db(test=True)
        >>> config = app.export_configuration()
        >>> import json
        >>> with open('config.json', 'w') as f:
        ...     json.dump(config, f, indent=2)
        ```
        """
        if not self.is_db_connected():
            return {"error": "Database not connected"}

        from .dbmodels import (
            Manufacturer, Segment, Variables, Units, DataTypes,
            Tags, AlarmTypes, AlarmStates, Alarms,
            Roles, Users, OPCUA, AccessType, OPCUAServer,
            Machines, TagsMachines
        )

        config = {
            "version": "1.0",
            "exported_at": datetime.now(timezone.utc).isoformat(),
            "data": {
                "Manufacturer": [m.serialize() for m in Manufacturer.select()],
                "Segment": [s.serialize() for s in Segment.select()],
                "Variables": [v.serialize() for v in Variables.select()],
                "Units": [u.serialize() for u in Units.select()],
                "DataTypes": [dt.serialize() for dt in DataTypes.select()],
                "Tags": [t.serialize() for t in Tags.select()],
                "AlarmTypes": [at.serialize() for at in AlarmTypes.select()],
                "AlarmStates": [as_obj.serialize() for as_obj in AlarmStates.select()],
                "Alarms": [a.serialize() for a in Alarms.select()],
                "Roles": [r.serialize() for r in Roles.select()],
                "Users": [
                    {
                        **u.serialize(),
                        "password": u.password  # Include password hash for import
                    } for u in Users.select()
                ],
                "OPCUA": [o.serialize() for o in OPCUA.select()],
                "AccessType": [at.serialize() for at in AccessType.select()],
                "OPCUAServer": [os_obj.serialize() for os_obj in OPCUAServer.select()],
                "Machines": [m.serialize() for m in Machines.select()],
                "TagsMachines": [tm.serialize() for tm in TagsMachines.select()]
            }
        }

        return config

    @logging_error_handler
    @validate_types(config_data=dict, output=dict)
    def import_configuration(self, config_data:dict)->dict:
        r"""
        Imports configuration data into database models.

        Imports configuration in the correct order to handle foreign key relationships.
        Order: Variables -> Units -> DataTypes -> Manufacturer -> Segment -> Tags ->
               AlarmTypes -> AlarmStates -> Alarms -> Roles -> Users -> OPCUA ->
               AccessType -> OPCUAServer -> Machines -> TagsMachines

        **Parameters:**

        * **config_data** (dict): Dictionary containing configuration data (from export_configuration).

        **Returns:**

        * **dict**: Dictionary with import results and statistics.

        **Usage:**

        ```python
        >>> from automation import PyAutomation
        >>> import json
        >>> app = PyAutomation()
        >>> app.connect_to_db(test=True)
        >>> with open('config.json', 'r') as f:
        ...     config = json.load(f)
        >>> result = app.import_configuration(config)
        >>> print(result['message'])
        ```
        """
        if not self.is_db_connected():
            return {"error": "Database not connected", "message": "Database not connected"}

        from .dbmodels import (
            Manufacturer, Segment, Variables, Units, DataTypes,
            Tags, AlarmTypes, AlarmStates, Alarms,
            Roles, Users, OPCUA, AccessType, OPCUAServer,
            Machines, TagsMachines
        )

        results = {
            "imported": {},
            "errors": {},
            "skipped": {}
        }

        try:
            data = config_data.get("data", config_data)

            # 1. Variables (no dependencies)
            if "Variables" in data:
                for item in data["Variables"]:
                    try:
                        if not Variables.name_exist(item["name"]):
                            Variables.create(name=item["name"])
                            results["imported"].setdefault("Variables", 0)
                            results["imported"]["Variables"] += 1
                        else:
                            results["skipped"].setdefault("Variables", 0)
                            results["skipped"]["Variables"] += 1
                    except Exception as e:
                        results["errors"].setdefault("Variables", []).append(f"{item.get('name', 'unknown')}: {str(e)}")

            # 2. Units (depends on Variables)
            if "Units" in data:
                for item in data["Units"]:
                    try:
                        if not Units.name_exist(item["name"]):
                            variable_name = item.get("variable", item.get("variable_id", {}).get("name"))
                            if variable_name:
                                Units.create(name=item["name"], unit=item["unit"], variable=variable_name)
                                results["imported"].setdefault("Units", 0)
                                results["imported"]["Units"] += 1
                            else:
                                results["errors"].setdefault("Units", []).append(f"{item.get('name', 'unknown')}: Missing variable")
                        else:
                            results["skipped"].setdefault("Units", 0)
                            results["skipped"]["Units"] += 1
                    except Exception as e:
                        results["errors"].setdefault("Units", []).append(f"{item.get('name', 'unknown')}: {str(e)}")

            # 3. DataTypes (no dependencies)
            if "DataTypes" in data:
                for item in data["DataTypes"]:
                    try:
                        if not DataTypes.name_exist(item["name"]):
                            DataTypes.create(name=item["name"])
                            results["imported"].setdefault("DataTypes", 0)
                            results["imported"]["DataTypes"] += 1
                        else:
                            results["skipped"].setdefault("DataTypes", 0)
                            results["skipped"]["DataTypes"] += 1
                    except Exception as e:
                        results["errors"].setdefault("DataTypes", []).append(f"{item.get('name', 'unknown')}: {str(e)}")

            # 4. Manufacturer (no dependencies)
            if "Manufacturer" in data:
                for item in data["Manufacturer"]:
                    try:
                        if not Manufacturer.name_exist(item["name"]):
                            Manufacturer.create(name=item["name"])
                            results["imported"].setdefault("Manufacturer", 0)
                            results["imported"]["Manufacturer"] += 1
                        else:
                            results["skipped"].setdefault("Manufacturer", 0)
                            results["skipped"]["Manufacturer"] += 1
                    except Exception as e:
                        results["errors"].setdefault("Manufacturer", []).append(f"{item.get('name', 'unknown')}: {str(e)}")

            # 5. Segment (depends on Manufacturer)
            if "Segment" in data:
                for item in data["Segment"]:
                    try:
                        manufacturer_name = item.get("manufacturer", {}).get("name") if isinstance(item.get("manufacturer"), dict) else item.get("manufacturer")
                        if manufacturer_name:
                            if not Segment.name_exist(item["name"]):
                                Segment.create(name=item["name"], manufacturer=manufacturer_name)
                                results["imported"].setdefault("Segment", 0)
                                results["imported"]["Segment"] += 1
                            else:
                                results["skipped"].setdefault("Segment", 0)
                                results["skipped"]["Segment"] += 1
                        else:
                            results["errors"].setdefault("Segment", []).append(f"{item.get('name', 'unknown')}: Missing manufacturer")
                    except Exception as e:
                        results["errors"].setdefault("Segment", []).append(f"{item.get('name', 'unknown')}: {str(e)}")

            # 6. Tags (depends on Units, DataTypes, Segment)
            if "Tags" in data:
                for item in data["Tags"]:
                    try:
                        if not Tags.name_exist(item["name"]):
                            # Extract related data - Tags.serialize() returns strings, not objects
                            unit_name = item.get("unit")
                            if isinstance(unit_name, dict):
                                unit_name = unit_name.get("unit")
                            
                            display_unit_name = item.get("display_unit")
                            if isinstance(display_unit_name, dict):
                                display_unit_name = display_unit_name.get("unit")
                            
                            data_type_name = item.get("data_type")
                            if isinstance(data_type_name, dict):
                                data_type_name = data_type_name.get("name")
                            
                            segment_name = item.get("segment")
                            manufacturer_name = item.get("manufacturer")
                            
                            # Handle segment as string or dict
                            if isinstance(segment_name, dict):
                                manufacturer_name = segment_name.get("manufacturer", {}).get("name") if isinstance(segment_name.get("manufacturer"), dict) else segment_name.get("manufacturer")
                                segment_name = segment_name.get("name")
                            
                            Tags.create(
                                id=item.get("id", item.get("identifier")),
                                name=item["name"],
                                unit=unit_name or display_unit_name,
                                data_type=data_type_name,
                                description=item.get("description"),
                                display_name=item.get("display_name", item["name"]),
                                display_unit=display_unit_name or unit_name,
                                opcua_address=item.get("opcua_address"),
                                node_namespace=item.get("node_namespace"),
                                segment=segment_name or "",
                                manufacturer=manufacturer_name or "",
                                scan_time=item.get("scan_time"),
                                dead_band=item.get("dead_band"),
                                active=item.get("active", True),
                                process_filter=item.get("process_filter", False),
                                gaussian_filter=item.get("gaussian_filter", False),
                                gaussian_filter_threshold=item.get("gaussian_filter_threshold", 1.0),
                                gaussian_filter_r_value=item.get("gaussian_filter_r_value", 0.0),
                                out_of_range_detection=item.get("out_of_range_detection", False),
                                outlier_detection=item.get("outlier_detection", False),
                                frozen_data_detection=item.get("frozen_data_detection", False)
                            )
                            results["imported"].setdefault("Tags", 0)
                            results["imported"]["Tags"] += 1
                        else:
                            results["skipped"].setdefault("Tags", 0)
                            results["skipped"]["Tags"] += 1
                    except Exception as e:
                        results["errors"].setdefault("Tags", []).append(f"{item.get('name', 'unknown')}: {str(e)}")

            # 7. AlarmTypes (no dependencies)
            if "AlarmTypes" in data:
                for item in data["AlarmTypes"]:
                    try:
                        if not AlarmTypes.name_exist(item["name"]):
                            AlarmTypes.create(name=item["name"])
                            results["imported"].setdefault("AlarmTypes", 0)
                            results["imported"]["AlarmTypes"] += 1
                        else:
                            results["skipped"].setdefault("AlarmTypes", 0)
                            results["skipped"]["AlarmTypes"] += 1
                    except Exception as e:
                        results["errors"].setdefault("AlarmTypes", []).append(f"{item.get('name', 'unknown')}: {str(e)}")

            # 8. AlarmStates (no dependencies)
            if "AlarmStates" in data:
                for item in data["AlarmStates"]:
                    try:
                        if not AlarmStates.name_exist(item["name"]):
                            AlarmStates.create(
                                name=item["name"],
                                mnemonic=item.get("mnemonic", ""),
                                condition=item.get("condition", ""),
                                status=item.get("status", "")
                            )
                            results["imported"].setdefault("AlarmStates", 0)
                            results["imported"]["AlarmStates"] += 1
                        else:
                            results["skipped"].setdefault("AlarmStates", 0)
                            results["skipped"]["AlarmStates"] += 1
                    except Exception as e:
                        results["errors"].setdefault("AlarmStates", []).append(f"{item.get('name', 'unknown')}: {str(e)}")

            # 9. Alarms (depends on Tags, AlarmTypes, AlarmStates)
            if "Alarms" in data:
                for item in data["Alarms"]:
                    try:
                        if not Alarms.name_exists(item["name"]):
                            # Alarms.serialize() returns strings, not objects
                            tag_name = item.get("tag")
                            if isinstance(tag_name, dict):
                                tag_name = tag_name.get("name")
                            
                            trigger_type_name = item.get("trigger_type") or item.get("alarm_type")
                            if isinstance(trigger_type_name, dict):
                                trigger_type_name = trigger_type_name.get("name")
                            
                            state_name = item.get("state")
                            if isinstance(state_name, dict):
                                state_name = state_name.get("name")
                            
                            if tag_name and trigger_type_name:
                                Alarms.create(
                                    identifier=item.get("identifier", item.get("id")),
                                    name=item["name"],
                                    tag=tag_name,
                                    trigger_type=trigger_type_name,
                                    trigger_value=item.get("trigger_value", 0.0),
                                    description=item.get("description"),
                                    state=state_name or "Normal"
                                )
                                results["imported"].setdefault("Alarms", 0)
                                results["imported"]["Alarms"] += 1
                            else:
                                results["errors"].setdefault("Alarms", []).append(f"{item.get('name', 'unknown')}: Missing tag or trigger_type")
                        else:
                            results["skipped"].setdefault("Alarms", 0)
                            results["skipped"]["Alarms"] += 1
                    except Exception as e:
                        results["errors"].setdefault("Alarms", []).append(f"{item.get('name', 'unknown')}: {str(e)}")

            # 10. Roles (no dependencies)
            if "Roles" in data:
                for item in data["Roles"]:
                    try:
                        if not Roles.name_exist(item["name"]):
                            Roles.create(
                                name=item["name"],
                                level=item["level"],
                                identifier=item.get("identifier", secrets.token_hex(4))
                            )
                            results["imported"].setdefault("Roles", 0)
                            results["imported"]["Roles"] += 1
                        else:
                            results["skipped"].setdefault("Roles", 0)
                            results["skipped"]["Roles"] += 1
                    except Exception as e:
                        results["errors"].setdefault("Roles", []).append(f"{item.get('name', 'unknown')}: {str(e)}")

            # 11. Users (depends on Roles)
            if "Users" in data:
                for item in data["Users"]:
                    try:
                        if not Users.username_exist(item["username"]):
                            role_name = item.get("role", {}).get("name") if isinstance(item.get("role"), dict) else item.get("role")
                            if role_name:
                                # Check if password is already hashed (from export) or plain text
                                password = item.get("password")
                                encode_password = True
                                
                                # If password looks like a hash (starts with pbkdf2:sha256: or scrypt:), use it directly
                                if password and (password.startswith("pbkdf2:sha256:") or password.startswith("scrypt:")):
                                    encode_password = False
                                elif not password:
                                    # If no password provided, use default (will be hashed)
                                    password = "default_password"
                                    encode_password = True
                                
                                # Create user using signup method with encode_password flag
                                user, message = self.signup(
                                    username=item["username"],
                                    role_name=role_name,
                                    email=item["email"],
                                    password=password,
                                    name=item.get("name"),
                                    lastname=item.get("lastname"),
                                    identifier=item.get("identifier"),
                                    encode_password=encode_password
                                )
                                if user:
                                    results["imported"].setdefault("Users", 0)
                                    results["imported"]["Users"] += 1
                                else:
                                    results["errors"].setdefault("Users", []).append(f"{item.get('username', 'unknown')}: {message}")
                            else:
                                results["errors"].setdefault("Users", []).append(f"{item.get('username', 'unknown')}: Missing role")
                        else:
                            results["skipped"].setdefault("Users", 0)
                            results["skipped"]["Users"] += 1
                    except Exception as e:
                        results["errors"].setdefault("Users", []).append(f"{item.get('username', 'unknown')}: {str(e)}")

            # 12. OPCUA (no dependencies)
            if "OPCUA" in data:
                for item in data["OPCUA"]:
                    try:
                        if not OPCUA.client_name_exist(item["client_name"]):
                            OPCUA.create(
                                client_name=item["client_name"],
                                host=item["host"],
                                port=item["port"]
                            )
                            results["imported"].setdefault("OPCUA", 0)
                            results["imported"]["OPCUA"] += 1
                        else:
                            results["skipped"].setdefault("OPCUA", 0)
                            results["skipped"]["OPCUA"] += 1
                    except Exception as e:
                        results["errors"].setdefault("OPCUA", []).append(f"{item.get('client_name', 'unknown')}: {str(e)}")

            # 13. AccessType (no dependencies)
            if "AccessType" in data:
                for item in data["AccessType"]:
                    try:
                        if not AccessType.name_exist(item["name"]):
                            AccessType.create(name=item["name"])
                            results["imported"].setdefault("AccessType", 0)
                            results["imported"]["AccessType"] += 1
                        else:
                            results["skipped"].setdefault("AccessType", 0)
                            results["skipped"]["AccessType"] += 1
                    except Exception as e:
                        results["errors"].setdefault("AccessType", []).append(f"{item.get('name', 'unknown')}: {str(e)}")

            # 14. OPCUAServer (depends on AccessType)
            if "OPCUAServer" in data:
                for item in data["OPCUAServer"]:
                    try:
                        if not OPCUAServer.name_exist(item["name"]):
                            access_type_name = item.get("access_type", {}).get("name") if isinstance(item.get("access_type"), dict) else item.get("access_type")
                            if access_type_name:
                                OPCUAServer.create(
                                    name=item["name"],
                                    namespace=item.get("namespace", ""),
                                    access_type=access_type_name
                                )
                                results["imported"].setdefault("OPCUAServer", 0)
                                results["imported"]["OPCUAServer"] += 1
                            else:
                                results["errors"].setdefault("OPCUAServer", []).append(f"{item.get('name', 'unknown')}: Missing access_type")
                        else:
                            results["skipped"].setdefault("OPCUAServer", 0)
                            results["skipped"]["OPCUAServer"] += 1
                    except Exception as e:
                        results["errors"].setdefault("OPCUAServer", []).append(f"{item.get('name', 'unknown')}: {str(e)}")

            # 15. Machines (no dependencies)
            if "Machines" in data:
                for item in data["Machines"]:
                    try:
                        if not Machines.name_exist(item["name"]):
                            Machines.create(
                                identifier=item.get("identifier", secrets.token_hex(4)),
                                name=item["name"],
                                interval=item.get("interval", 1.0),
                                description=item.get("description", ""),
                                classification=item.get("classification", ""),
                                buffer_size=item.get("buffer_size", 100),
                                buffer_roll_type=item.get("buffer_roll_type", "FIFO"),
                                criticity=item.get("criticity", 0),
                                priority=item.get("priority", 0),
                                threshold=item.get("threshold"),
                                on_delay=item.get("on_delay")
                            )
                            results["imported"].setdefault("Machines", 0)
                            results["imported"]["Machines"] += 1
                        else:
                            results["skipped"].setdefault("Machines", 0)
                            results["skipped"]["Machines"] += 1
                    except Exception as e:
                        results["errors"].setdefault("Machines", []).append(f"{item.get('name', 'unknown')}: {str(e)}")

            # 16. TagsMachines (depends on Tags and Machines)
            if "TagsMachines" in data:
                for item in data["TagsMachines"]:
                    try:
                        tag_name = item.get("tag", {}).get("name") if isinstance(item.get("tag"), dict) else item.get("tag")
                        machine_name = item.get("machine", {}).get("name") if isinstance(item.get("machine"), dict) else item.get("machine")
                        
                        if tag_name and machine_name:
                            TagsMachines.create(
                                tag_name=tag_name,
                                machine_name=machine_name,
                                default_tag_name=item.get("default_tag_name")
                            )
                            results["imported"].setdefault("TagsMachines", 0)
                            results["imported"]["TagsMachines"] += 1
                        else:
                            results["errors"].setdefault("TagsMachines", []).append(f"Missing tag or machine: {item}")
                    except Exception as e:
                        results["errors"].setdefault("TagsMachines", []).append(f"{str(e)}")

            total_imported = sum(results["imported"].values())
            total_skipped = sum(results["skipped"].values())
            total_errors = sum(len(errs) for errs in results["errors"].values())

            return {
                "message": f"Configuration imported: {total_imported} records imported, {total_skipped} skipped, {total_errors} errors",
                "results": results,
                "summary": {
                    "imported": total_imported,
                    "skipped": total_skipped,
                    "errors": total_errors
                }
            }

        except Exception as e:
            return {
                "error": str(e),
                "message": f"Import failed: {str(e)}",
                "results": results
            }
