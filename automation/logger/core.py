import threading, logging
from ..singleton import Singleton
from ..dbmodels import (
    Variables, 
    Units,
    DataTypes
    )
from ..variables import VARIABLES, DATATYPES

class BaseLogger(Singleton):
    r"""
    Base class for all Logger implementations.

    It handles the underlying database connection, table creation, and schema initialization.
    """

    def __init__(self):

        self._db = None
        self.is_history_logged = True

    def set_db(self, db):
        r"""
        Sets the database instance to be used by the logger.

        **Parameters:**

        * **db**: The Peewee database instance.
        """
        self._db = db

    def get_db(self):
        r"""
        Retrieves the current database instance.

        **Returns:**

        * **Database**: The Peewee database object.
        """
        return self._db
    
    def check_connectivity(self):
        r"""
        Checks if the database connection is active.

        **Returns:**

        * **bool**: True if connected, False otherwise.
        """

        try: 
            
            if self._db:
                
                self._db.execute_sql('SELECT 1;')
                
                return True
            
            return False
        
        except: 
            
            return False
    
    def set_is_history_logged(self, value:bool=False):
        r"""
        Enables or disables historical data logging.

        **Parameters:**

        * **value** (bool): True to enable logging, False to disable.
        """
        self.is_history_logged = value
    
    def stop_db(self):
        r""""
        Closes the database connection.
        """
        try:
            if self._db:
                self._db.close()
                self._db = None
        except:

            pass

    def create_tables(self, tables):
        r"""
        Creates tables in the database if they do not exist.
        Also initializes default schema data (Variables, Units, DataTypes, Roles).

        **Parameters:**

        * **tables** (list): List of Peewee models to create tables for.
        """
        if not self._db:
            
            return
        
        self._db.create_tables(tables, safe=True)
        self.__init_default_variables_schema()
        self.__init_default_datatypes_schema()
        self.__init_default_roles_schema()

    def __init_default_roles_schema(self):
        r"""
        Initializes default user roles in the database.
        """
        from ..dbmodels import Roles
        for role in Roles.__defaults__:

            if not Roles.name_exist(name=role['name']):

                Roles.create(**role)

    def __init_default_variables_schema(self):
        r"""
        Initializes default physical variables and units in the database.
        """
        for variable, units in VARIABLES.items():
    
            if not Variables.name_exist(variable):
                
                Variables.create(name=variable)

            for name, unit in units.items():

                if not Units.name_exist(unit):

                    Units.create(name=name, unit=unit, variable=variable)

    def __init_default_datatypes_schema(self):
        r"""
        Initializes default data types in the database.
        """
        for datatype in DATATYPES:

            DataTypes.create(name=datatype["value"])

    def drop_tables(self, tables):
        r"""
        Drops the specified tables from the database.

        **Parameters:**

        * **tables** (list): List of Peewee models to drop.
        """
        if not self._db:
            
            return

        self._db.drop_tables(tables, safe=True)

class BaseEngine(Singleton):
    r"""
    Base class for Thread-Safe Logger Engines.

    It implements a request-response mechanism using locks to ensure thread safety
    when accessing the underlying Logger instance (which interacts with the database).
    """
    logger = BaseLogger()

    def __init__(self):

        super(BaseEngine, self).__init__()
        self._request_lock = threading.Lock()
        self._response_lock = threading.Lock()
        self._response = None
        self._response_lock.acquire()

    def set_db(self, db):
        r"""
        Sets the database for the underlying logger.

        **Parameters:**

        * **db**: The Peewee database instance.
        """
        self.logger.set_db(db)

    def stop_db(self):
        r"""
        Closes the database connection safely.
        """
        self.logger.stop_db()

    def get_db(self):
        r"""
        Retrieves the database instance.
        """
        return self.logger.get_db()

    def query(self, query:dict)->dict:
        r"""
        Executes a query against the logger in a thread-safe manner.

        **Parameters:**

        * **query** (dict): A dictionary containing the action and parameters.
          e.g., `{"action": "method_name", "parameters": {...}}`

        **Returns:**

        * **dict**: The result of the operation.
        """
        self.request(query)
        result = self.response()
        if result["result"]:
            return result["response"]

    def request(self, query:dict):
        r"""
        Internal method to process a request.
        Acquires the request lock, executes the method on the logger, and stores the response.

        **Parameters:**

        * **query** (dict): The query dictionary.
        """
        self._request_lock.acquire()
        action = query["action"]
        error_msg = f"Error in BaseEngine: {action}"

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
        Logs an error to the application logger and sets a failure response.
        """
        logger = logging.getLogger("pyautomation")
        logger.error(f"{e} Message: {msg}")
        self._response = {
            "result": False,
            "response": None
        }

    def response(self):
        r"""
        Waits for and retrieves the response from the last request.

        **Returns:**

        * **dict**: The response dictionary `{"result": bool, "response": Any}`.
        """
        self._response_lock.acquire()
        result = self._response
        self._request_lock.release()
        return result
    
    def __true_response(self, resp):
        r"""
        Sets a successful response.
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
