import sys, logging, json, os, jwt
from math import ceil
from datetime import datetime, timezone
# DRIVERS IMPORTATION
from peewee import SqliteDatabase, MySQLDatabase, PostgresqlDatabase
from .dbmodels.users import Roles, Users
from .dbmodels.machines import Machines
# PYAUTOMATION MODULES IMPORTATION
from .utils import log_detailed
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
from .alarms import Alarm
from .state_machine import Machine, DAQ, AutomationStateMachine, StateMachine
from .opcua.subscription import DAS
from .buffer import Buffer
from .models import StringType, FloatType, IntegerType
from .modules.users.users import users, User
from .modules.users.roles import roles, Role
from .utils.decorators import validate_types, logging_error_handler
# DASH APP CONFIGURATION PAGES IMPORTATION
from .pages.main import ConfigView
from .pages.callbacks import init_callbacks
import dash_bootstrap_components as dbc


class PyAutomation(Singleton):
    r"""
    Automation is a [singleton](https://en.wikipedia.org/wiki/Singleton_pattern) class to develop multi threads web application
    for general purposes.
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
        self.db_manager = DBManager()
        self.opcua_client_manager = OPCUAClientManager()
        self.alarm_manager = AlarmManager()
        self.workers = list()
        self.das = DAS()
        self.set_log(level=logging.WARNING)
    
    @logging_error_handler
    def define_dash_app(self, **kwargs)->None:
        r"""
        Documentation here
        """
        self.dash_app = ConfigView(use_pages=True, external_stylesheets=[dbc.themes.BOOTSTRAP], prevent_initial_callbacks=True, pages_folder=".", **kwargs)
        self.dash_app.set_automation_app(self)
        init_callbacks(app=self.dash_app)

    # MACHINES METHODS
    @logging_error_handler
    @validate_types(machine=StateMachine, interval=FloatType|IntegerType, mode=str, output=None)
    def append_machine(self, machine, interval:float=FloatType(1.0), mode:str="async")->None:
        r"""
        Documentation here
        """
        self.machine.append_machine(machine=machine, interval=interval, mode=mode)

    @logging_error_handler
    @validate_types(name=StringType, output=StateMachine)
    def get_machine(self, name:StringType)->StateMachine:
        r"""
        Documentation here
        """
        return self.machine_manager.get_machine(name=name)

    @logging_error_handler
    @validate_types(output=[(Machine, int, str)])
    def get_machines(self)->list[tuple[Machine, int, str]]:
        r"""
        Documentation here
        """
        return self.machine_manager.get_machines()

    @logging_error_handler
    @validate_types(output=list)
    def serialize_machines(self)->list[dict]:
        r"""
        Documentation here
        """
        return self.machine_manager.serialize_machines()
    
    @logging_error_handler
    @validate_types(machine=AutomationStateMachine, tag=Tag, output=dict)
    def subscribe_tag_into_automation_machine(self, machine:AutomationStateMachine, tag:Tag)->dict:
        r"""
        Documentation here
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
            outlier_detection=bool,
            out_of_range_detection=bool,
            frozen_data_detection=bool,
            id=str|type(None),
            user=User,
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
            outlier_detection:bool=False,
            out_of_range_detection:bool=False,
            frozen_data_detection:bool=False,
            id:str=None,
            user:User|None=None,
            reload:bool=False,
        )->tuple[Tag,str]:
        """Create tag to automation app.

        Addding tag from this way, you get the following features.

        - Add tag to CVT.
        - 

        ```python
        >>> from automation import PyAutomation
        >>> app = PyAutomation()
        >>> tag_name = "tag1"
        >>> unit = "Pa"
        >>> variable = "Pressure"
        >>> app.create_tag(name=tag_name, unit=unit, variable=variable)
        tag, message

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
            outlier_detection=outlier_detection,
            out_of_range_detection=out_of_range_detection,
            frozen_data_detection=frozen_data_detection,
            id=id,
            user=user
        )

        # CREATE OPCUA SUBSCRIPTION
        if tag:

            # Persist Tag on Database
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
        r"""Documentation here

        # Parameters

        -

        # Returns

        -
        """

        return self.cvt.get_tags()

    @logging_error_handler
    @validate_types(name=str, output=Tag|None)
    def get_tag_by_name(self, name:str)->Tag:

        return self.cvt.get_tag_by_name(name=name)

    @logging_error_handler
    def get_trends(self, start:str, stop:str, timezone:str, *tags):
        r"""
        Documentation here
        """
        return self.logger_engine.read_trends(start, stop, timezone, *tags)

    @logging_error_handler
    @validate_types(id=str, output=None|str)
    def delete_tag(self, id:str, user:User|None=None)->None|str:
        r"""
        Documentation here
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
    @validate_types(
            id=str,  
            name=str, 
            unit=str, 
            data_type=str, 
            description=str, 
            variable=str,
            display_name=str,
            display_unit=str,
            opcua_address=str,
            node_namespace=str,
            scan_time=int|float|type(None),
            dead_band=int|float|type(None),
            user=User|type(None),
            output=(Tag, str)
        )
    def update_tag(
            self, 
            id:str,  
            name:str="", 
            unit:str="", 
            data_type:str="", 
            description:str="", 
            variable:str="",
            display_name:str="",
            display_unit:str="",
            opcua_address:str="",
            node_namespace:str="",
            scan_time:int=None,
            dead_band:int|float=None,
            user:User|None=None, 
        )->dict:
        r"""
        Documentation here
        """
        tag = self.cvt.get_tag(id=id)
        self.unsubscribe_opcua(tag)
        if name:
            tag_name = tag.get_name()
        # Persist Tag on Database
        if self.is_db_connected():

            self.logger_engine.update_tag(
                id=id,  
                name=name, 
                unit=unit, 
                data_type=data_type, 
                description=description, 
                variable=variable,
                display_name=display_name,
                display_unit=display_unit,
                opcua_address=opcua_address,
                node_namespace=node_namespace,
                scan_time=scan_time,
                dead_band=dead_band
            )

        result = self.cvt.update_tag(
            id=id,  
            name=name, 
            unit=unit, 
            data_type=data_type, 
            description=description, 
            variable=variable,
            display_name=display_name,
            display_unit=display_unit,
            opcua_address=opcua_address,
            node_namespace=node_namespace,
            scan_time=scan_time,
            dead_band=dead_band,
            user=user
        )
        if name:
            self.das.buffer.pop(tag_name)
            self.__update_buffer(tag=tag)

        self.subscribe_opcua(tag, opcua_address=tag.get_opcua_address(), node_namespace=tag.get_node_namespace(), scan_time=tag.get_scan_time())
        return result

    @logging_error_handler
    @validate_types(name=str, output=None|str)
    def delete_tag_by_name(self, name:str, user:User|None=None):
        r"""
        Documentation here
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
            username=str,
            role_name=str,
            email=str,
            password=str,
            name=str|type(None),
            lastname=str|type(None),
            output=(User|None, str)
    )
    def signup(
            self,
            username:str,
            role_name:str,
            email:str,
            password:str,
            name:str=None,
            lastname:str=None
        )->tuple[User|None, str]:
        r"""
        Documentation here
        """
        user, message = users.signup(
            username=username,
            role_name=role_name,
            email=email,
            password=password,
            name=name,
            lastname=lastname
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
        Documentation here
        """
        from . import server
        payload = {
            "created_on": datetime.now(timezone.utc).strftime(self.cvt.DATETIME_FORMAT),
            "role": role_name
        }
        return jwt.encode(payload, server.config['TPT_TOKEN'], algorithm="HS256")

    @logging_error_handler
    @validate_types(name=str, level=int, output=(Role|None, str))
    def set_role(self, name:str, level:int)->Role|None:
        r"""
        Documentation here
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

    # OPCUA METHODS
    @logging_error_handler
    @validate_types(host=str|type(None), port=int|type(None), output=dict)
    def find_opcua_servers(self, host:str='127.0.0.1', port:int=4840)->dict:
        r"""
        Documentation here
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
        Documentation here
        """
        return self.opcua_client_manager.serialize()

    @logging_error_handler
    @validate_types(client_name=str, output=Client)
    def get_opcua_client(self, client_name:str):
        r"""
        Documentation here
        """
        return self.opcua_client_manager.get(client_name=client_name)

    @logging_error_handler
    @validate_types(client_name=str, namespaces=list, output=list)
    def get_node_values(self, client_name:str, namespaces:list)->list:
        r"""
        Documentation here
        """

        return self.opcua_client_manager.get_node_values(client_name=client_name, namespaces=namespaces)

    @logging_error_handler
    @validate_types(client_name=str, namespaces=list, output=list)
    def get_node_attributes(self, client_name:str, namespaces:list)->list[dict]:
        r"""
        Documentation here
        """

        return self.opcua_client_manager.get_node_attributes(client_name=client_name, namespaces=namespaces)

    @logging_error_handler
    def get_opcua_tree(self, client_name:str):
        r"""
        Documentation here
        """
        return self.opcua_client_manager.get_opcua_tree(client_name=client_name)

    @logging_error_handler
    @validate_types(client_name=str, host=str|type(None), port=int|type(None), output=None)
    def add_opcua_client(self, client_name:str, host:str="127.0.0.1", port:int=4840):
        r"""
        Documentation here
        """
        servers = self.find_opcua_servers(host=host, port=port)

        if servers:

            self.opcua_client_manager.add(client_name=client_name, host=host, port=port)

    @logging_error_handler
    @validate_types(tag=Tag, opcua_address=str|type(None), node_namespace=str|type(None), scan_time=float|int|type(None), reload=bool, output=None)
    def subscribe_opcua(self, tag:Tag, opcua_address:str, node_namespace:str, scan_time:float, reload:bool=False):
        r"""
        Documentation here
        """
        if opcua_address and node_namespace:

            if not scan_time:                                                           # SUBSCRIBE BY DAS

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
        Documentatio here
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
        Documentation here
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
        Documentation here
        """
        if tag.get_scan_time():

            self.das.buffer[tag.get_name()] = {
                "timestamp": Buffer(size=ceil(10 / ceil(tag.get_scan_time() / 1000))),
                "values": Buffer(size=ceil(10 / ceil(tag.get_scan_time() / 1000))),
                "unit": tag.get_display_unit()
            }

        else:

            self.das.buffer[tag.get_name()] = {
                "timestamp": Buffer(),
                "values": Buffer(),
                "unit": tag.get_display_unit()
            }

    # ERROR LOGS
    @logging_error_handler
    @validate_types(level=int, file=str, output=None)
    def set_log(self, level:int=logging.INFO, file:str="app.log"):
        r"""
        Sets the log file and level.

        **Parameters:**

        * **level** (str): `logging.LEVEL` (default: logging.INFO).
        * **file** (str): log filename (default: 'app.log').

        **Returns:** `None`

        Usage:

        ```python
        >>> app.set_log(file="app.log")
        ```
        """

        self._logging_level = level

        if file:

            self._log_file = file

    # DATABASES
    @logging_error_handler
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
    def set_db(self, dbtype:str='sqlite', drop_table=False, clear_default_tables=False, **kwargs):
        r"""
        Sets the database, it supports SQLite and Postgres,
        in case of SQLite, the filename must be provided.

        if app mode is "Development" you must use SQLite Databse

        **Parameters:**

        * **dbfile** (str): a path to database file.
        * *drop_table** (bool): If you want to drop table.
        * **cascade** (bool): if there are some table dependency, drop it as well
        * **kwargs**: Same attributes to a postgres connection.

        **Returns:** `None`

        Usage:

        ```python
        >>> app.set_db(dbfile="app.db")
        ```
        """

        from .dbmodels import proxy

        if clear_default_tables:

            self.db_manager.clear_default_tables()

        if dbtype.lower()=='sqlite':

            dbfile = kwargs.get("dbfile", ":memory:")

            self._db = SqliteDatabase(dbfile, pragmas={
                'journal_mode': 'wal',
                'journal_size_limit': 1024,
                'cache_size': -1024 * 64,  # 64MB
                'foreign_keys': 1,
                'ignore_check_constraints': 0,
                'synchronous': 0}
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
        self.db_manager.set_db(self._db)
        self.db_manager.set_dropped(drop_table)

    @logging_error_handler
    @validate_types(
            dbtype=str, 
            dbfile=str, 
            user=str|type(None), 
            password=str|type(None), 
            host=str|type(None), 
            port=int|type(None), 
            name=str|type(None), 
            output=None)
    def set_db_config(
            self,
            dbtype:str="sqlite",
            dbfile:str="app.db",
            user:str|None="admin",
            password:str|None="admin",
            host:str|None="127.0.0.1",
            port:int|None=5432,
            name:str|None="app_db"
        ):
        r"""
        Documentation here
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

        with open('./db_config.json', 'w') as json_file:

            json.dump(db_config, json_file)

    @logging_error_handler
    @validate_types(output=dict|None)
    def get_db_config(self):
        r"""
        Documentation here
        """
        try:

            with open('./db_config.json', 'r') as json_file:

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
    @validate_types(output=bool)
    def is_db_connected(self):
        r"""
        Documentation here
        """
        if self.db_manager.get_db():

            return True

        return False

    @logging_error_handler
    @validate_types(test=bool|type(None), output=None)
    def connect_to_db(self, test:bool=False):
        r"""
        Documentation here
        """
        if not test:
            db_config = self.get_db_config()
        else:
            db_config = {"dbtype": "sqlite", "dbfile": "test.db"}
            
        if db_config:
            dbtype = db_config.pop("dbtype")
            self.set_db(dbtype=dbtype, **db_config)
            self.db_manager.init_database()
            self.load_opcua_clients_from_db()
            self.load_db_to_cvt()
            self.load_db_to_alarm_manager()
            self.load_db_to_roles()
            self.load_db_to_users()
            self.load_db_tags_to_machine()

    @logging_error_handler
    @validate_types(output=None)
    def disconnect_to_db(self):
        r"""
        Documentation here
        """
        self.db_manager.stop_database()

    @logging_error_handler
    @validate_types(output=None)
    def load_db_to_cvt(self):
        r"""
        Documentation here
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
        Documentation here
        """
        if self.is_db_connected():

            alarms = self.db_manager.get_alarms()
            for alarm in alarms:

                    self.create_alarm(reload=True, **alarm)

    @logging_error_handler
    @validate_types(output=None)
    def load_db_to_roles(self):
        r"""
        Documentation here
        """
        if self.is_db_connected():

            Roles.fill_cvt_roles()

    @logging_error_handler
    @validate_types(output=None)
    def load_db_to_users(self):
        r"""
        Documentation here
        """
        if self.is_db_connected():

            Users.fill_cvt_users()
        
    @logging_error_handler
    @validate_types(output=None)
    def load_opcua_clients_from_db(self):
        r"""
        Documentation here
        """
        if self.is_db_connected():

            clients = self.db_manager.get_opcua_clients()

            for client in clients:

                self.add_opcua_client(**client)

    @logging_error_handler
    def load_db_tags_to_machine(self):

        machines = self.machine_manager.get_machines()
        for machine, _, _ in machines:

            if machine.classification.value.lower()!="data acquisition system":

                machine_name = machine.name.value
                machine_db = Machines.get_or_none(name=machine_name)

                if not machine_db:

                    return f"{machine_name} not found into DB", 404
                
                tags_machine = machine_db.get_tags()
                
                for tag_machine in tags_machine:

                    _tag = tag_machine.serialize()
                    tag_name = _tag["tag"]["name"]
                    tag = self.cvt.get_tag_by_name(name=tag_name)
                    machine.subscribe_to(tag=tag, default_tag_name=_tag["default_tag_name"])

    # ALARMS METHODS
    @logging_error_handler
    @validate_types(output=AlarmManager)
    def get_alarm_manager(self)->AlarmManager:
        r"""
        Documentation here
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
        Append alarm to the Alarm Manager

        **Paramters**

        * **alarm**: (Alarm Object)

        **Returns**

        * **None**
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
            reload=reload
        )

        if alarm:

            # Persist Tag on Database
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
        Documentation here
        """
        if self.is_db_connected():
            
            return self.alarms_engine.get_lasts(lasts=lasts)

    @logging_error_handler
    def filter_alarms_by(self, **fields):
        r"""
        Documentation here
        """
        if self.is_db_connected():

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
        Updates alarm attributes

        **Parameters**

        * **id** (int).
        * **name** (str)[Optional]:
        * **tag** (str)[Optional]:
        * **description** (str)[Optional]:
        * **alarm_type** (str)[Optional]:
        * **trigger** (float)[Optional]:

        **Returns**

        * **alarm** (dict) Alarm Object jsonable
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
        Gets alarm from the Alarm Manager by id

        **Paramters**

        * **id**: (int) Alarm ID

        **Returns**

        * **alarm** (Alarm Object)
        """
        return self.alarm_manager.get_alarm(id=id)

    @logging_error_handler
    @validate_types(output=list)
    def get_alarms(self)->list:
        r"""
        Gets all alarms

        **Returns**

        * **alarms**: (dict) Alarm objects
        """
        return self.alarm_manager.get_alarms()

    @logging_error_handler
    @validate_types(lasts=int|None, output=list)
    def get_lasts_active_alarms(self, lasts:int=None)->list:
        r"""
        Documentation here
        """
        return self.alarm_manager.get_lasts_active_alarms(lasts=lasts)

    @logging_error_handler
    @validate_types(name=str, output=Alarm)
    def get_alarm_by_name(self, name:str)->Alarm:
        r"""
        Gets alarm from the Alarm Manager by name

        **Paramters**

        * **name**: (str) Alarm name

        **Returns**

        * **alarm** (Alarm Object)
        """
        return self.alarm_manager.get_alarm_by_name(name=name)

    @logging_error_handler
    @validate_types(tag=str, output=list)
    def get_alarms_by_tag(self, tag:str)->list:
        r"""
        Gets all alarms associated to some tag

        **Parameters**

        * **tag**: (str) tag name binded to alarm

        **Returns**

        * **alarm** (dict) of alarm objects
        """
        return self.alarm_manager.get_alarms_by_tag(tag=tag)

    @logging_error_handler
    @validate_types(id=str, user=User, output=None)
    def delete_alarm(self, id:str, user:User=None):
        r"""
        Removes alarm

        **Paramters**

        * **id** (int): Alarm ID
        """
        self.alarm_manager.delete_alarm(id=id, user=user)
        if self.is_db_connected():

            self.alarms_engine.delete(id=id)

    # EVENTS METHODS
    @logging_error_handler
    @validate_types(lasts=int, output=list)
    def get_lasts_events(self, lasts:int=10)->list:
        r"""
        Documentation here
        """
        if self.is_db_connected():

            return self.events_engine.get_lasts(lasts=lasts)

    @logging_error_handler
    def filter_events_by(
            self,
            usernames:list[str]=None,
            priorities:list[int]=None,
            criticities:list[int]=None,
            greater_than_timestamp:datetime=None,
            less_than_timestamp:datetime=None)->list:
        r"""
        Documentation here
        """
        if self.is_db_connected():

            return self.events_engine.filter_by(
                usernames=usernames,
                priorities=priorities,
                criticities=criticities,
                greater_than_timestamp=greater_than_timestamp,
                less_than_timestamp=less_than_timestamp
            )
        
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
        )->list:
        r"""
        Documentation here
        """
        if self.is_db_connected():

            return self.logs_engine.create(
                message=message, 
                user=user, 
                description=description, 
                classification=classification,
                alarm_summary_id=alarm_summary_id,
                event_id=event_id,
                timestamp=timestamp
            )
        
    @logging_error_handler
    def filter_logs_by(
            self,
            usernames:list[str]=None,
            alarm_names:list[str]=None,
            event_ids:list[int]=None,
            classifications:list[str]=None,
            greater_than_timestamp:datetime=None,
            less_than_timestamp:datetime=None
        )->list:
        r"""
        Documentation here
        """
        if self.is_db_connected():

            return self.logs_engine.filter_by(
                usernames=usernames,
                alarm_names=alarm_names,
                event_ids=event_ids,
                classifications=classifications,
                greater_than_timestamp=greater_than_timestamp,
                less_than_timestamp=less_than_timestamp
            )
        
    @logging_error_handler
    @validate_types(lasts=int, output=list)
    def get_lasts_logs(self, lasts:int=10)->list:
        r"""
        Documentation here
        """
        if self.is_db_connected():

            return self.logs_engine.get_lasts(lasts=lasts)

    # INIT APP
    @logging_error_handler
    def run(self, debug:bool=False, test:bool=False, create_tables:bool=False, machines:tuple=None)->None:
        r"""
        Runs main app thread and all defined threads by decorators and State Machines besides this method starts app logger

        **Returns:** `None`
        """
        self.safe_start(test=test, create_tables=create_tables, machines=machines)

        if not test:
        
            if debug:

                self.dash_app.run(debug=debug, use_reloader=False)

    @logging_error_handler
    def safe_start(self, test:bool=False, create_tables:bool=True, machines:tuple=None):
        r"""
        Run the app without a main thread, only run the app with the threads and state machines define
        """
        self._create_tables = create_tables
        self.__start_logger()
        self.__start_workers(test=test, machines=machines)

    @logging_error_handler
    @validate_types(output=None)
    def safe_stop(self)->None:
        r"""
        Stops the app in safe way with the threads
        """
        self.__stop_workers()

    @logging_error_handler
    def state_machine_diagrams(self, folder_path:str):
        r"""
        Documentation here"""
        for machine, _, _ in self._manager.get_machines():
            # SAVE STATE DIAGRAM
            img_path = f"{folder_path}{machine.name.value}.png"
            machine._graph().write_png(img_path)

    # WORKERS
    @logging_error_handler
    def __start_workers(self, test:bool=False, machines:tuple=None)->None:
        r"""
        Starts all workers.

        * LoggerWorker
        * StateMachineWorker
        """
        self.machine.start(machines=machines)

        if self._create_tables:

            self.db_worker = LoggerWorker(self.db_manager)
            self.connect_to_db(test=test)
            self.db_worker.start()
    
        self.is_starting = False

    @logging_error_handler
    @validate_types(output=None)
    def __stop_workers(self)->None:
        r"""
        Safe stop workers execution
        """
        try:
            self.machine.stop()
            self.db_worker.stop()
        except Exception as e:
            message = "Error on wokers stop"
            log_detailed(e, message)

    @logging_error_handler
    @validate_types(output=None)
    def __start_logger(self)->None:
        r"""
        Starts logger in log file
        """
        log_format = "%(asctime)s:%(levelname)s:%(message)s"

        level = self._logging_level
        log_file = self._log_file

        if not log_file:
            logging.basicConfig(level=level, format=log_format)
            return

        logging.basicConfig(filename=log_file, level=level, format=log_format)
