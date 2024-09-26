import sys, logging, json, os
from math import ceil
from .utils import log_detailed
from .singleton import Singleton
from .workers import LoggerWorker, AlarmWorker
from .managers import DBManager, OPCUAClientManager, AlarmManager
from .tags import CVTEngine, Tag
from .logger import DataLoggerEngine
from .alarms import Alarm
from .state_machine import Machine, DAQ
from .opcua.subscription import DAS
from .buffer import Buffer
from peewee import SqliteDatabase, MySQLDatabase, PostgresqlDatabase
from datetime import datetime
# DASH APP CONFIGURATION PAGES IMPORTATION
from .pages.main import ConfigView
from .pages.callbacks import init_callbacks
import dash_bootstrap_components as dbc


class PyAutomation(Singleton):
    r"""
    Automation is a [singleton](https://en.wikipedia.org/wiki/Singleton_pattern) class to develop multi threads web application
    for general purposes.

    Usage:

    ```python
    >>> from pyautomation import PyAutomation
    >>> app = PyAutomation()
    >>> app.run()
    ```
    """
    PORTS = 65535
    def __init__(self):

        self.machine = Machine()
        self.machine_manager = self.machine.get_state_machine_manager()
        self.db_manager = DBManager()
        self.cvt = CVTEngine()
        self.logger_engine = DataLoggerEngine()
        self.opcua_client_manager = OPCUAClientManager()
        self.alarm_manager = AlarmManager()
        self.workers = list()
        self.set_log(level=logging.WARNING)
        self.das = DAS()
    
    def define_dash_app(self, **kwargs):
        r"""
        Documentation here
        """
        self.dash_app = ConfigView(use_pages=True, external_stylesheets=[dbc.themes.BOOTSTRAP], prevent_initial_callbacks=True, pages_folder=".", **kwargs)
        self.dash_app.set_automation_app(self)
        init_callbacks(app=self.dash_app)

    # MACHINES METHODS
    def append_machine(self, machine, interval:float=1.0, mode:str="async"):
        r"""
        Documentation here
        """
        self.machine.append_machine(machine=machine, interval=interval, mode=mode)

    def get_machine(self, name:str):
        r"""
        Documentation here
        """
        return self.machine_manager.get_machine(name=name)

    def get_machines(self):
        r"""
        Documentation here
        """
        return self.machine_manager.get_machines()

    def serialize_machines(self):
        r"""
        Documentation here
        """
        return self.machine_manager.serialize_machines()

    # TAGS METHODS
    def get_tags(self):
        r"""Documentation here

        # Parameters

        -

        # Returns

        -
        """

        return self.cvt.get_tags()

    def get_trends(self, start:str, stop:str, *tags):
        r"""
        Documentation here
        """
        return self.logger_engine.read_trends(start, stop, *tags)

    def create_tag(self,
            name:str,
            unit:str,
            display_unit:str,
            variable:str,
            data_type:str='float',
            description:str="",
            display_name:str=None,
            opcua_address:str=None,
            node_namespace:str=None,
            scan_time:int=None,
            dead_band:float=None,
            id:str=None
        ):
        r"""Documentation here

        # Parameters

        -

        # Returns

        -
        """
        if not display_name:

            display_name = name

        message = self.cvt.set_tag(
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
            id=id
        )

        # CREATE OPCUA SUBSCRIPTION
        if not message:

            # Persist Tag on Database
            if self.is_db_connected():

                tag = self.cvt.get_tag_by_name(name=name)
                self.logger_engine.set_tag(
                    id=tag.id,
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

            self.subscribe_opcua(tag=self.cvt.get_tag_by_name(name=name), opcua_address=opcua_address, node_namespace=node_namespace, scan_time=scan_time)

        return message

    def delete_tag(self, id:str):
        r"""
        Documentation here
        """
        tag = self.cvt.get_tag(id=id)
        tag_name = tag.get_name()
        alarm = self.alarm_manager.get_alarm_by_tag(tag=tag_name)
        if alarm:

            return f"Tag {tag_name} has an alarm associated"

        self.unsubscribe_opcua(tag=tag)
        self.das.buffer.pop(tag_name)

        # Persist Tag on Database
        if self.is_db_connected():

            self.logger_engine.delete_tag(id=id)

        self.cvt.delete_tag(id=id)

    def update_tag(self, id:str, **kwargs):
        r"""
        Documentation here
        """
        tag = self.cvt.get_tag(id=id)
        self.unsubscribe_opcua(tag)
        # Persist Tag on Database
        if self.is_db_connected():

            self.logger_engine.update_tag(id=id, **kwargs)

        result = self.cvt.update_tag(id=id, **kwargs)
        self.subscribe_opcua(tag, opcua_address=tag.get_opcua_address(), node_namespace=tag.get_node_namespace(), scan_time=tag.get_scan_time())
        return result

    def delete_tag_by_name(self, name:str):
        r"""
        Documentation here
        """
        tag = self.cvt.get_tag_by_name(name=name)
        alarm = self.alarm_manager.get_alarm_by_tag(tag=tag.get_name())
        if alarm:

            return f"Tag {name} has an alarm associated: {alarm.name}, delete first it"

    # OPCUA METHODS
    def find_opcua_servers(self, host:str='127.0.0.1', port:int=4840)->list[dict]:
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

    def get_opcua_clients(self):
        r"""
        Documentation here
        """

        return self.opcua_client_manager.serialize()

    def get_opcua_client(self, client_name:str):
        r"""
        Documentation here
        """
        return self.opcua_client_manager.get(client_name=client_name)

    def get_node_values(self, client_name:str, namespaces:list):
        r"""
        Documentation here
        """

        return self.opcua_client_manager.get_node_values(client_name=client_name, namespaces=namespaces)

    def get_node_attributes(self, client_name:str, namespaces:list):
        r"""
        Documentation here
        """

        return self.opcua_client_manager.get_node_attributes(client_name=client_name, namespaces=namespaces)

    def get_opcua_tree(self, client_name:str):
        r"""
        Documentation here
        """

        return self.opcua_client_manager.get_opcua_tree(client_name=client_name)

    def add_opcua_client(self, client_name:str, host:str="127.0.0.1", port:int=4840):
        r"""
        Documentation here
        """
        servers = self.find_opcua_servers(host=host, port=port)

        if servers:

            self.opcua_client_manager.add(client_name=client_name, host=host, port=port)

    def subscribe_opcua(self, tag:Tag, opcua_address:str, node_namespace:str, scan_time:float):
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

                self.subscribe_tag(tag_name=tag.get_name(), scan_time=scan_time)

        self.das.buffer[tag.get_name()].update({
            "unit": tag.get_display_unit()
        })

    def subscribe_tag(self, tag_name:str, scan_time:float):
        r"""
        Documentatio here
        """
        scan_time = float(scan_time)
        daq_name = f"DAQ-{int(scan_time / 1000)}"
        daq = self.machine_manager.get_machine(name=daq_name)
        tag = self.cvt.get_tag_by_name(name=tag_name)
        if not daq:

            daq = DAQ()
            daq.set_opcua_client_manager(manager=self.opcua_client_manager)
            self.machine.append_machine(machine=daq, interval=scan_time / 1000, mode="async")

        daq.subscribe_to(tag=tag)
        self.machine.stop()
        self.machine.start()

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

            self.machine_manager.unsubscribe_tag(tag=tag)
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

    # ERROR LOGS
    def set_log(self, level=logging.INFO, file:str="app.log"):
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

    def init_db(self)->LoggerWorker:
        r"""
        Initialize Logger Worker

        **Returns**

        * **db_worker**: (LoggerWorker Object)
        """
        db_worker = LoggerWorker(self.db_manager)
        db_worker.init_database()

        try:

            db_worker.daemon = True
            db_worker.start()

        except Exception as e:
            message = "Error on db worker start-up"
            log_detailed(e, message)

        return db_worker

    def stop_db(self, db_worker:LoggerWorker):
        r"""
        Stops Database Worker
        """
        try:
            db_worker.stop()
        except Exception as e:
            message = "Error on db worker stop"
            log_detailed(e, message)

    def set_db_config(
            self,
            dbtype:str="sqlite",
            dbfile:str="app.db",
            user:str="admin",
            password:str="admin",
            host:str="127.0.0.1",
            port:int=5432,
            name:str="app_db"
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

    def is_db_connected(self):
        r"""
        Documentation here
        """
        if self.db_manager.get_db():

            return True

        return False

    def connect_to_db(self):
        r"""
        Documentation here
        """
        db_config = self.get_db_config()
        if db_config:
            dbtype = db_config.pop("dbtype")
            self.set_db(dbtype=dbtype, **db_config)
            self.db_manager.init_database()
            self.load_opcua_clients_from_db()
            self.load_db_to_cvt()
            self.load_db_to_alarm_manager()

    def disconnect_to_db(self):
        r"""
        Documentation here
        """
        self.db_manager.stop_database()

    def load_db_to_cvt(self):
        r"""
        Documentation here
        """
        if self.is_db_connected():

            tags = self.db_manager.get_tags()

            for tag in tags:

                self.create_tag(**tag)

    def load_db_to_alarm_manager(self):
        r"""
        Documentation here
        """
        if self.is_db_connected():

            alarms = self.db_manager.get_alarms()

            for alarm in alarms:

                self.create_alarm(**alarm)

    def load_opcua_clients_from_db(self):
        r"""
        Documentation here
        """
        if self.is_db_connected():

            clients = self.db_manager.get_opcua_clients()

            for client in clients:

                self.add_opcua_client(**client)

    # ALARMS METHODS
    def get_alarm_manager(self)->AlarmManager:
        r"""
        Documentation here
        """
        return self.alarm_manager

    def create_alarm(
            self,
            name:str,
            tag:str,
            type:str="BOOL",
            trigger_value:bool|float=True,
            description:str="",
            identifier:str=None,
            tag_alarm:str=None,
            state:str="Normal",
            timestamp:str=None,
            acknowledged_timestamp:str=None
        )->dict:
        r"""
        Append alarm to the Alarm Manager

        **Paramters**

        * **alarm**: (Alarm Object)

        **Returns**

        * **None**
        """
        message = self.alarm_manager.append_alarm(
            name=name,
            tag=tag,
            type=type,
            trigger_value=trigger_value,
            description=description,
            identifier=identifier,
            tag_alarm=tag_alarm,
            state=state,
            timestamp=timestamp,
            acknowledged_timestamp=acknowledged_timestamp
        )

        if not message:

            # Persist Tag on Database
            if self.is_db_connected():

                alarm = self.alarm_manager.get_alarm_by_name(name=name)
                self.logger_engine.set_alarm(
                    id=alarm._id,
                    name=name,
                    tag=tag,
                    trigger_type=type,
                    trigger_value=trigger_value,
                    description=description,
                    tag_alarm=None
                )

        return message

    def get_lasts_alarms(self, lasts:int=10):
        r"""
        Documentation here
        """
        if self.is_db_connected():

            return self.logger_engine.get_lasts_alarms(lasts=lasts)

    def filter_alarms_by(self, **fields):
        r"""
        Documentation here
        """
        if self.is_db_connected():

            return self.logger_engine.filter_alarms_by(**fields)

    def update_alarm(self, id:str, **kwargs):
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

        return self.alarm_manager.update_alarm(id=id, **kwargs)

    def get_alarm(self, id:str)->Alarm:
        r"""
        Gets alarm from the Alarm Manager by id

        **Paramters**

        * **id**: (int) Alarm ID

        **Returns**

        * **alarm** (Alarm Object)
        """
        return self.alarm_manager.get_alarm(id=id)

    def get_alarms(self)->dict:
        r"""
        Gets all alarms

        **Returns**

        * **alarms**: (dict) Alarm objects
        """
        return self.alarm_manager.get_alarms()

    def get_lasts_active_alarms(self, lasts:int=None):
        r"""
        Documentation here
        """
        return self.alarm_manager.get_lasts_active_alarms(lasts=lasts)

    def get_alarm_by_name(self, name:str)->Alarm:
        r"""
        Gets alarm from the Alarm Manager by name

        **Paramters**

        * **name**: (str) Alarm name

        **Returns**

        * **alarm** (Alarm Object)
        """
        return self.alarm_manager.get_alarm_by_name(name=name)

    def get_alarms_by_tag(self, tag:str)->dict:
        r"""
        Gets all alarms associated to some tag

        **Parameters**

        * **tag**: (str) tag name binded to alarm

        **Returns**

        * **alarm** (dict) of alarm objects
        """
        return self.alarm_manager.get_alarm_by_tag(tag=tag)

    def delete_alarm(self, id:str):
        r"""
        Removes alarm

        **Paramters**

        * **id** (int): Alarm ID
        """
        self.alarm_manager.delete_alarm(id=id)

    # INIT APP
    def run(self, debug:bool=False, create_tables:bool=False, alarm_worker:bool=True, **kwargs):
        r"""
        Runs main app thread and all defined threads by decorators and State Machines besides this method starts app logger

        **Returns:** `None`

        Usage

        ```python
        >>> app.run()
        ```
        """
        self.startup_config_page(debug=debug, create_tables=create_tables, alarm_worker=alarm_worker, **kwargs)

    def startup_config_page(self, debug:bool=False, create_tables:bool=False, alarm_worker:bool=True, **kwargs):
        r"""Documentation here

        # Parameters

        -

        # Returns

        -
        """
        # self.dash_app = ConfigView(use_pages=True, external_stylesheets=[dbc.themes.BOOTSTRAP], prevent_initial_callbacks=True, pages_folder=".", **kwargs)
        # self.dash_app.set_automation_app(self)
        # init_callbacks(app=self.dash_app)
        self.safe_start(create_tables=create_tables, alarm_worker=alarm_worker)
        if debug:

            self.dash_app.run(debug=debug, use_reloader=False)

    def safe_start(self, create_tables:bool=True, alarm_worker:bool=False):
        r"""
        Run the app without a main thread, only run the app with the threads and state machines define
        """
        self._create_tables = create_tables
        self._create_alarm_worker = alarm_worker
        self.__start_logger()
        self.__start_workers()

    def safe_stop(self):
        r"""
        Stops the app in safe way with the threads
        """
        self.__stop_workers()
        logging.info("Manual Shutting down")
        sys.exit()

    # WORKERS
    def __start_workers(self):
        r"""
        Starts all workers.

        * LoggerWorker
        * AlarmWorker
        * StateMachineWorker
        """
        if self._create_tables:

            db_worker = LoggerWorker(self.db_manager)
            self.connect_to_db()
            db_worker.start_workers()
            # self.workers.append(db_worker)

        if self._create_alarm_worker:
            alarm_manager = self.get_alarm_manager()
            alarm_worker = AlarmWorker(alarm_manager)
            alarm_worker.daemon = True
            alarm_worker.start()

        self.machine.start()

    def __stop_workers(self):
        r"""
        Safe stop workers execution
        """
        for worker in self.workers:
            try:
                worker.stop()
            except Exception as e:
                message = "Error on wokers stop"
                log_detailed(e, message)

    def __start_logger(self):
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
