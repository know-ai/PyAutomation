import sys, logging, json, os, jwt, requests, urllib3, secrets
from logging.handlers import RotatingFileHandler
from math import ceil
from datetime import datetime, timezone
# DRIVERS IMPORTATION
from peewee import SqliteDatabase, MySQLDatabase, PostgresqlDatabase
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
from flask_socketio import SocketIO
from geventwebsocket.handler import WebSocketHandler
from .variables import VARIABLES
# DASH APP CONFIGURATION PAGES IMPORTATION
from .pages.main import ConfigView
from .pages.callbacks import init_callbacks
import dash_bootstrap_components as dbc


class PyAutomation(Singleton):
    r"""
    Automation is a `singleton <https://en.wikipedia.org/wiki/Singleton_pattern>`_ class designed to develop multi-threaded web applications for Industrial Applications.

    You can initialize and run PyAutomation Framework in different ways depending on your requirements.

    **Example 1**: Using only PyAutomation Framework

    ```python
    from automation import PyAutomation, server
    app = PyAutomation()
    app.define_dash_app(server=server)  # This is the configuration page
    app.run(debug=True, create_tables=True)

    ```

    **Example 2**: Extending PyAutomation Framework with Flask Application

    ```python
    from automation import PyAutomation
    from app import CreateApp
    application = CreateApp()
    server = application()  # Flask App
    app = PyAutomation()
    app.define_dash_app(server=server)  # This is the configuration page
    app.run(create_tables=True)

    ```

"""

    PORTS = 65535
    def __init__(self):

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
    def define_dash_app(self,  certfile:str=None, keyfile:str=None, **kwargs)->None:
        r"""
        Initializes and configures the Dash application integrated within PyAutomation.

        **Parameters:**
        
        * **certfile** (str, optional): Path to the SSL certificate file.
        * **keyfile** (str, optional): Path to the SSL key file.
        * **kwargs**: Additional keyword arguments passed to the Dash application constructor.

        This method sets up the Dash frontend, configures callbacks, and initializes the Socket.IO server 
        for real-time communication.
        """
        self.dash_app = ConfigView(use_pages=True, external_stylesheets=[dbc.themes.BOOTSTRAP], prevent_initial_callbacks=True, pages_folder=".", **kwargs)
        self.dash_app.set_automation_app(self)
        init_callbacks(app=self.dash_app)
        if certfile and keyfile:
            
            self.sio = SocketIO(
                self.dash_app.server, 
                cors_allowed_origins='*', 
                ping_timeout=10, 
                ping_interval=10, 
                async_mode='gevent', 
                ssl_context=(certfile, keyfile), 
                handler_class=WebSocketHandler
            )
        
        else:
            self.sio = SocketIO(self.dash_app.server, cors_allowed_origins='*', ping_timeout=10, ping_interval=10, async_mode='gevent', handler_class=WebSocketHandler)

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

        tag, message = self.cvt.set_tag(
            name=name,
            unit=unit,
            display_unit=display_unit,
            variable=variable,
            data_type=data_type,
            description=description,
            display_name=display_name,
            opcua_address=opcua_address,
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
            
            self.subscribe_opcua(tag=self.cvt.get_tag_by_name(name=name), opcua_address=opcua_address, node_namespace=node_namespace, scan_time=scan_time, reload=reload)

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

        
        result = self.cvt.update_tag(
            id=id,  
            user=user,
            **kwargs
        )
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
        if self.is_db_connected():

            return self.db_manager.login(password=password, username=username, email=email)
        
        return users.login(password=password, username=username, email=email)

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
        if user:

            # Persist Tag on Database
            if self.is_db_connected():
                
                _, message = self.db_manager.set_user(user=user)

            return user, message

        return None, message

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
        Retrieves all configured OPC UA clients.

        **Returns:**

        * **dict**: A dictionary of configured clients.
        """
        return self.opcua_client_manager.serialize()

    @logging_error_handler
    @validate_types(client_name=str, output=Client)
    def get_opcua_client(self, client_name:str):
        r"""
        Retrieves a specific OPC UA client instance by name.

        **Parameters:**

        * **client_name** (str): The name of the client to retrieve.

        **Returns:**

        * **Client**: The OPC UA Client object.
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

        if servers:

            return self.opcua_client_manager.add(client_name=client_name, host=host, port=port)
        
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

                    if opcua_address==info["server_url"]:

                        opcua_client = self.get_opcua_client(client_name=client_name)
                        subscription = opcua_client.create_subscription(1000, self.das)
                        node_id = opcua_client.get_node_id_by_namespace(node_namespace)
                        self.das.subscribe(subscription=subscription, client_name=client_name, node_id=node_id)
                        break

            else:                                                                       # SUBSCRIBE BY DAQ
                
                self.subscribe_tag(tag_name=tag.get_name(), scan_time=scan_time, reload=reload)

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
        if dbtype.lower()=="sqlite":

            db_config = {
                "dbtype": dbtype,
                "dbfile": dbfile
            }

        else:

            db_config = {
                "dbtype": dbtype,
                'user': user,
                'password': password,
                'host': host,
                'port': port,
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
            _, _, e_traceback = sys.exc_info()
            e_filename = os.path.split(e_traceback.tb_frame.f_code.co_filename)[1]
            e_message = str(e)
            e_line_number = e_traceback.tb_lineno
            message = f"Database is not configured: {e_line_number} - {e_filename} - {e_message}"
            logging.warning(message)
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
        if self.db_manager.get_db():

            return True
        
        return False

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
        try:
            db_config = self.get_db_config()

            if test:
                
                db_config = {"dbtype": "sqlite", "dbfile": "test.db"}
            
            if db_config:
            
                dbtype = db_config.pop("dbtype")
                self.__log_histories = True
                self.set_db(dbtype=dbtype, **db_config)
                self.db_manager.init_database()
                self.load_opcua_clients_from_db()
                self.load_db_to_cvt()
                self.load_db_to_alarm_manager()
                self.load_db_to_roles()
                self.load_db_to_users()
                if reload:

                    self.load_db_tags_to_machine()
                
            return True
        
        except Exception as err:
            logging.critical(f"CONNECTING DATABASE ERROR: {err}")
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


            for tag in tags:

                active = tag.pop("active")

                if active:
                    
                    self.create_tag(reload=True, **tag)

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
        if self.is_db_connected():

            alarms = self.db_manager.get_alarms()
            if alarms:
                for alarm in alarms:

                        self.create_alarm(reload=True, **alarm)

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
        if self.is_db_connected():

            Roles.fill_cvt_roles()

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
        if self.is_db_connected():

            Users.fill_cvt_users()
        
    @logging_error_handler
    @validate_types(output=None)
    def load_opcua_clients_from_db(self):
        r"""
        Loads OPC UA client configurations from the database and initializes them.
        """
        
        if self.is_db_connected():

            clients = self.db_manager.get_opcua_clients()
            
            for client in clients:

                self.add_opcua_client(**client)

    @logging_error_handler
    def load_db_tags_to_machine(self):
        r"""
        Loads tag subscriptions for state machines from the database.
        """
        
        machines = self.machine_manager.get_machines()

        for machine, _, _ in machines:

            if machine.classification.value.lower()!="data acquisition system":

                machine_name = machine.name.value
                machine_db = Machines.get_or_none(name=machine_name)
                
                if not machine_db:

                    return f"{machine_name} not found into DB", 404
                
                machine.identifier.value = machine_db.identifier
                tags_machine = machine_db.get_tags()
                
                for tag_machine in tags_machine:

                    _tag = tag_machine.serialize()
                    tag_name = _tag["tag"]["name"]
                    tag = self.cvt.get_tag_by_name(name=tag_name)
                    machine.subscribe_to(tag=tag, default_tag_name=_tag["default_tag_name"])

            else:

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
        >>> app.connect_to_db(test=True)
        True
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
    @validate_types(id=str, name=str|None, description=str|None, alarm_type=str|None, trigger_value=int|float|None, output=None)
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

            if self.sio:

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
            timezone:str="UTC"
        )->list:
        r"""
        Filters system logs based on criteria.

        **Parameters:**

        * **usernames** (list[str]): Filter by user.
        * **classification** (str): Filter by category.
        * **timezone** (str): Timezone.

        **Returns:**

        * **list**: Filtered list of logs.
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
                timezone=timezone
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
    def run(self, debug:bool=False, test:bool=False, create_tables:bool=False, machines:tuple=None)->None:
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
        logging.critical(f"{str_date} Starting app with configuration:")
        logging.critical(f"{str_date} Logger period: {self.get_app_config().get('logger_period', 10.0)} seconds")
        logging.critical(f"{str_date} Log max bytes: {self.get_app_config().get('log_max_bytes', 10 * 1024 * 1024)} bytes")
        logging.critical(f"{str_date} Log backup count: {self.get_app_config().get('log_backup_count', 3)} backups")
        logging.critical(f"{str_date} Log level: {self.get_app_config().get('log_level', 20)}")
        print(f"[INFO] {str_date} Starting app with configuration:")
        print(f"[INFO] {str_date} Logger period: {self.get_app_config().get('logger_period', 10.0)} seconds")
        print(f"[INFO] {str_date} Log max bytes: {self.get_app_config().get('log_max_bytes', 10 * 1024 * 1024)} bytes")
        print(f"[INFO] {str_date} Log backup count: {self.get_app_config().get('log_backup_count', 3)} backups")
        print(f"[INFO] {str_date} Log level: {self.get_app_config().get('log_level', 20)}")

        self.safe_start(test=test, create_tables=create_tables, machines=machines)
        self.create_system_user()

        if not test:
        
            if debug:
                
                self.dash_app.run(debug=debug, use_reloader=False)

    @logging_error_handler
    def create_system_user(self):
        r"""
        Ensures a 'system' user exists with 'sudo' role. Used for automated internal actions.
        """
        # Create system user
        users = Users()
        roles = Roles()
        system_password = self.server.config["AUTOMATION_SUPERUSER_PASSWORD"]
        
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
        logging.critical(f"{str_date} App started successfully")
        print(f"[INFO] {str_date} App started successfully")

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
            logging.info(f"{str_date} Logger period updated to {period} seconds")
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
                logging.info(f"{str_date} Log configuration updated: maxBytes={max_bytes}, backupCount={backup_count}")
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
