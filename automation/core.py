
from .singleton import Singleton
import sys
from .utils import log_detailed
from .workers import StateMachineWorker, LoggerWorker
import logging
from .managers import StateMachineManager, DBManager, OPCUAClientManager, AlarmManager
from .tags import CVTEngine
from automation.pages.main import ConfigView
from automation.pages.callbacks import init_callbacks
import dash_bootstrap_components as dbc


class PyAutomation(Singleton):
    r"""
    Automation is a [singleton](https://en.wikipedia.org/wiki/Singleton_pattern) class to develop multi threads web application
    for general purposes .

    Usage:

    ```python
    >>> from pyautomation import PyAutomation
    >>> app = PyAutomation()
    ```
    """
    PORTS = 65535
    def __init__(self):

        self.machine_manager = StateMachineManager()
        self.db_manager = DBManager()
        self.cvt = CVTEngine()
        self.opcua_client_manager = OPCUAClientManager()
        self.alarm_manager = AlarmManager()

    def get_tags(self):
        r"""Documentation here

        # Parameters

        - 

        # Returns

        - 
        """

        return self.cvt.get_tags()
    
    def create_tag(self,
            name:str, 
            unit:str, 
            data_type:str='float', 
            description:str="", 
            display_name:str=None,
            opcua_address:str=None,
            node_namespace:str=None,
            scan_time:int=None,
            dead_band:float=None
        ):
        r"""Documentation here

        # Parameters

        - 

        # Returns

        - 
        """
        if not display_name:

            display_name = name

        self.cvt.set_tag(
            name=name,
            unit=unit,
            data_type=data_type,
            description=description,
            display_name=display_name,
            opcua_address=opcua_address,
            node_namespace=node_namespace,
            scan_time=scan_time,
            dead_band=dead_band
        )

    def delete_tag(self, id:str):
        r"""
        Documentation here
        """
        tag = self.cvt.get_tag(id=id)
        alarm = self.alarm_manager.get_alarm_by_tag(tag=tag.get_name())
        if alarm:

            return f"Tag {tag.get_name()} has an alarm associated"
        
        self.cvt.delete_tag(id=id)

    def delete_tag_by_name(self, name:str):
        r"""
        Documentation here
        """
        tag = self.cvt.get_tag_by_name(name=name)
        alarm = self.alarm_manager.get_alarm_by_tag(tag=tag.get_name())
        if alarm:

            return f"Tag {name} has an alarm associated: {alarm.name}, delete first it"

    def _start_logger(self):
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
            
            self.opcua_client_manager.add(client_name=client_name, endpoint_url=f"opc.tcp://{host}:{port}")
        
    def stop_db(self, db_worker:LoggerWorker):
        r"""
        Stops Database Worker
        """
        try:
            db_worker.stop()
        except Exception as e:
            message = "Error on db worker stop"
            log_detailed(e, message)

    def _start_workers(self):
        r"""
        Starts all workers.

        * LoggerWorker
        * AlarmWorker
        * StateMachineWorker
        """
        
        if self._create_tables:

            db_worker = LoggerWorker(self.db_manager)
            self.workers.append(db_worker)

        # if self._create_alarm_worker:
            # alarm_manager = self.get_alarm_manager()
            # alarm_worker = AlarmWorker(alarm_manager)
            # self.workers.append(alarm_worker)

        # StateMachine Worker
        state_manager = self.get_state_machine_manager()
        if state_manager.exist_machines():

            state_worker = StateMachineWorker(state_manager)
            self.workers.append(state_worker)

        try:

            for worker in self.workers:
                
                worker.daemon = True
                worker.start()

        except Exception as e:
            message = "Error on workers start-up"
            log_detailed(e, message)

    def _stop_workers(self):
        r"""
        Safe stop workers execution
        """
        for worker in self.workers:
            try:
                worker.stop()
            except Exception as e:
                message = "Error on wokers stop"
                log_detailed(e, message)

    def safe_start(self, create_tables:bool=True, alarm_worker:bool=False):
        r"""
        Run the app without a main thread, only run the app with the threads and state machines define
        """
        self._create_tables = create_tables
        self._create_alarm_worker = alarm_worker
        self._start_logger()
        self._start_workers()

        logging.info("PyAutomation started")
        logging.info(self.info())

    def safe_stop(self):
        r"""
        Stops the app in safe way with the threads
        """
        self._stop_workers()
        logging.info("Manual Shutting down")
        sys.exit()

    def startup_config_page(self, debug:str=False):
        r"""Documentation here

        # Parameters

        - 

        # Returns

        - 
        """
        self.dash_app = ConfigView(use_pages=True, external_stylesheets=[dbc.themes.BOOTSTRAP], prevent_initial_callbacks=True, pages_folder=".")
        self.dash_app.set_automation_app(self)
        init_callbacks(app=self.dash_app)
        self.dash_app.run(debug=debug)

    def run(self, debug:bool=False):
        r"""
        Runs main app thread and all defined threads by decorators and State Machines besides this method starts app logger

        **Returns:** `None`

        Usage

        ```python
        >>> app.run()
        ```
        """
        self.startup_config_page(debug=debug)