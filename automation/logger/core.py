import threading, logging
from ..singleton import Singleton
from ..dbmodels import (
    Variables, 
    Units,
    DataTypes
    )
from ..variables import VARIABLES, DATATYPES

class BaseLogger(Singleton):

    def __init__(self):

        self._db = None

    def set_db(self, db):
        r"""Documentation here
        """
        self._db = db

    def get_db(self):
        r"""
        Documentation here
        """
        return self._db
    
    def stop_db(self):
        r""""
        Documentation here
        """
        self._db = None

    def create_tables(self, tables):
        r"""
        Documentation here
        """
        if not self._db:
            
            return
        
        self._db.create_tables(tables, safe=True)
        self.__init_default_variables_schema()
        self.__init_default_datatypes_schema()

    def __init_default_variables_schema(self):
        r"""
        Documentation here
        """
        for variable, units in VARIABLES.items():
    
            if not Variables.name_exist(variable):
                
                Variables.create(name=variable)

            for name, unit in units.items():

                if not Units.name_exist(unit):

                    Units.create(name=name, unit=unit, variable=variable)

    def __init_default_datatypes_schema(self):
        r"""
        Documentation here
        """
        for datatype in DATATYPES:

            DataTypes.create(name=datatype["value"])

    def drop_tables(self, tables):
        r"""
        Documentation here
        """
        if not self._db:
            
            return

        self._db.drop_tables(tables, safe=True)

class BaseEngine(Singleton):
    r"""
    Alarms logger Engine class for Tag thread-safe database logging.
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
        self.logger.set_db(db)

    def stop_db(self):
        r"""
        Documentation here
        """
        self.logger.stop_db()

    def get_db(self):
        r"""
        Returns a DB object
        """
        return self.logger.get_db()

    def query(self, query:dict)->dict:
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
