import threading, copy, logging
from datetime import datetime
from ..singleton import Singleton
from ..models import FloatType, StringType, IntegerType, BooleanType
from .tag import Tag
from ..modules.users.users import User

class CVT:
    """Current Value Table class for Tag based repository.

    This class is intended hold in memory tag based values and 
    observers for those required tags, this class is intended to be
    used by PyAutomation itself and not for other purposes

    Usage:
    
    ```python
    >>> from automation.tags import CVT
    >>> _cvt = CVT()
    ```
    """
    def __init__(self):

        self._tags = dict()
        self.data_types = ["float", "int", "bool", "str"]
        # from ..logger import EventsLoggerEngine
        # self.events_engine = EventsLoggerEngine()
    
    def set_tag(
        self, 
        name:str, 
        unit:str, 
        data_type:str, 
        description:str, 
        variable:str,
        display_name:str="",
        display_unit:str="",
        opcua_address:str="",
        node_namespace:str="",
        scan_time:int=None,
        dead_band:float=None,
        id:str=None
        )->None|str:
        """Initialize a new Tag object in the _tags dictionary.
        
        # Parameters
        name (str):
            Tag name.
        data_type (str): 
            Tag value type ("int", "float", "bool", "str")
        """
        if isinstance(data_type, str):
        
            if data_type in self.data_types:
                if data_type == "float":
                    value = 0.0
                elif data_type == "int":
                    value = 0
                elif data_type == "str":
                    value = ""
                else:
                    value = False
            
        elif isinstance(data_type, (FloatType, IntegerType, StringType, BooleanType)):

            value = data_type()
            data_type.set(name, value)
            data_type = data_type.__name__
            self.set_data_type(data_type)
        
        has_duplicates, message = self.has_duplicates(name=name, display_name=display_name, opcua_address=opcua_address, node_namespace=node_namespace)
        if has_duplicates:

            return message
        
        if not display_unit:

            display_unit = unit

        tag = Tag(
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
            id=id
        )
        self._tags[tag.id] = tag

    def update_tag(self, id:str, **kwargs)->None|str:
        r"""Documentation here

        # Parameters

        - 

        # Returns

        - 
        """
        has_duplicates, message = self.has_duplicates(**kwargs)
        if has_duplicates:

            return message
        
        tag = self._tags[id]
        tag.update(**kwargs)
        self._tags[id] = tag

    def delete_tag(self, id:str):
        r"""Documentation here

        # Parameters

        - 

        # Returns

        - 
        """
        self._tags.pop(id)

    def get_tag(self, id:str)->Tag|None:
        r"""Documentation here

        # Parameters

        - 

        # Returns

        - 
        """
        for _id, tag in self._tags.items():

            if _id==id:
                
                return tag

        return None
    
    def get_unit_by_tag(self, tag:str)->Tag|None:
        r"""Documentation here

        # Parameters

        - 

        # Returns

        - 
        """
        for _id, _tag in self._tags.items():

            if _tag.name==tag:
                
                return _tag.unit

        return None
    
    def get_display_unit_by_tag(self, tag:str)->Tag|None:
        r"""Documentation here

        # Parameters

        - 

        # Returns

        - 
        """
        for _id, _tag in self._tags.items():
            
            if _tag.name==tag:
                
                return _tag.display_unit

        return None

    def get_tags(self)->list:
        r"""
        Returns a list of the defined tags names.
        """

        return [value.serialize() for _, value in self._tags.items()]
    
    def get_tag_by_name(self, name:str)->Tag|None:
        r"""Documentation here

        # Parameters

        - 

        # Returns

        - 
        """
        for _, tag in self._tags.items():

            if tag.get_name()==name:
                
                return tag

        return None
    
    def get_tag_by_display_name(self, display_name:str)->Tag|None:
        r"""Documentation here

        # Parameters

        - 

        # Returns

        - 
        """
        for _, tag in self._tags.items():

            if tag.get_display_name()==display_name:
                
                return tag

        return None

    def get_tag_by_node_namespace(self, node_namespace:str)->Tag|None:
        r"""Documentation here

        # Parameters

        - 

        # Returns

        - 
        """
        for _, tag in self._tags.items():

            if tag.get_node_namespace()==node_namespace:
                
                return tag

        return None
    
    def get_value(self, id:str)->str|float|int|bool:
        r"""Documentation here

        # Parameters

        - 

        # Returns

        - 
        """
        tag = self._tags[id]        
        _new_object = copy.copy(tag.get_value())
        return _new_object
    
    def get_timestamp(self, id:str)->datetime:
        r"""
        Documentation here
        """
        tag = self._tags[id] 

        return tag.get_timestamp()
    
    def get_value_by_name(self, name:str)->str|float|int|bool:
        r"""Documentation here

        # Parameters

        - 

        # Returns

        - 
        """

        tag = self.get_tag_by_name(name=name)  

        return {
                "value": tag.get_value(),
                "unit": tag.get_unit(),
                "timestamp": tag.get_timestamp()
            }

    def get_values_by_name(self, names:list[str])->str|float|int|bool:
        r"""Documentation here

        # Parameters

        - 

        # Returns

        - 
        """
        data = dict()

        for name in names:

            tag = self.get_tag_by_name(name=name)  
            data[name] = {
                "value": tag.get_value(),
                "unit": tag.get_unit(),
                "timestamp": tag.get_timestamp()
            }
            
        return data
    
    def set_value(self, id:str, value, timestamp:datetime):
        """Sets a new value for a defined tag.
        
        # Parameters
        name (str):
            Tag name.
        value (float, int, bool): 
            Tag value ("int", "float", "bool")
        """
        self._tags[id].set_value(value=value, timestamp=timestamp)

    def set_data_type(self, data_type):
        r"""Documentation here

        # Parameters

        - 

        # Returns

        - 
        """
        self.data_types.append(data_type)
        self.data_types = list(set(self.data_types))
    
    def is_tag_defined(self, name:str)->bool:
        r"""Documentation here

        # Parameters

        - 

        # Returns

        - 
        """

        return name in self._tags
    
    def attach_observer(self, name, observer):
        r"""Attaches a new observer to a tag object defined by name.
        
        # Parameters
        name (str):
            Tag name.
        observer (TagObserver): 
            Tag observer object, will update once a tag object is changed.
        """
        tag = self.get_tag_by_name(name)
        if tag:
            
            self._tags[tag.id].attach(observer)
        
        else:
            
            logging.warning(f"{name} tag Not exists in CVT.attach_observer method")

    def detach_observer(self, name, observer):
        r"""
        Detaches an observer from a tag object defined by name.
        
        # Parameters
        name (str):
            Tag name.
        observer (TagObserver): 
            Tag observer object.
        """
        tag = self.get_tag_by_name(name)
        self._tags[tag.id].detach(observer)

    def has_duplicates(self, tag:Tag=None, name:str=None, display_name:str=None, node_namespace:str=None, opcua_address:str=None, **kwargs):
        r"""Documentation here

        # Parameters

        - 

        # Returns

        - 
        """

        for _, _tag in self._tags.items():

            if name:

                if _tag.get_name()==name:

                    return True, f"Duplicated Tag Name: {name}"
                
            if display_name:
            
                if _tag.get_display_name()==display_name:

                    return True, f"Duplicated Display Name: {display_name}"
                
            if node_namespace:
            
                if _tag.get_node_namespace()==node_namespace:
                    
                    if tag:
                    
                        if _tag.get_opcua_address()==tag.get_opcua_address():

                            return True, f"Duplicated Node Namespace: {node_namespace}"
                        
                    return True, f"Duplicated Node Namespace: {node_namespace}"
            
        return False, f"Valid Tag Name: {name} - Display Name: {display_name}"
    
    def __persist_on_event_logger(self, user:User, message:str, description:str, priority:int, criticity:int):

        if isinstance(user, User):

            self.events_engine.create(
                message=message,
                description=description,
                classification="Alarms",
                priority=priority,
                criticity=criticity,
                user=user
            )

    def serialize(self, id:str)->dict:
        r"""Returns a tag type defined by name.
        
        # Parameters
        name (str):
            Tag name.
        """
        return self._tags[id].serialize()
    
    def serialize_by_tag_name(self, name:str)->dict|None:
        r"""Documentation here

        # Parameters

        - 

        # Returns

        - 
        """
        tag = self.get_tag_by_name(name)

        if tag:

            return tag.serialize()


class CVTEngine(Singleton):
    """Current Value Table Engine class for Tag thread-safe based repository.

    This class is intended hold in memory tag based values and 
    observers for those required tags, it is implemented as a singleton
    so each sub-thread within the PyAutomation application can access tags
    in a thread-safe mechanism.

    Usage:
    
    ```python
    >>> from automation.tags import CVTEngine
    >>> tag_egine = CVTEngine()
    ```
    """

    def __init__(self):

        super(CVTEngine, self).__init__()
        self._cvt = CVT()
        self._request_lock = threading.Lock()
        self._response_lock = threading.Lock()
        self._config = None
        self._response = None
        self._response_lock.acquire()
        self.DATETIME_FORMAT = "%m/%d/%Y, %H:%M:%S.%f"

    def set_tag(
        self, 
        name:str, 
        unit:str, 
        data_type:str, 
        variable:str,
        description:str, 
        display_unit:str="",
        display_name:str="",
        opcua_address:str="",
        node_namespace:str="",
        scan_time:int=None,
        dead_band:float=None,
        id:str=None,
        ):
        r"""Documentation here

        # Parameters

        - 

        # Returns

        - 
        """
        _query = dict()
        _query["action"] = "set_tag"
        _query["parameters"] = dict()
        _query["parameters"]["name"] = name
        _query["parameters"]["unit"] = unit
        _query["parameters"]["data_type"] = data_type
        _query["parameters"]["variable"] = variable
        _query["parameters"]["description"] = description
        _query["parameters"]["display_unit"] = display_unit
        _query["parameters"]["display_name"] = display_name
        _query["parameters"]["opcua_address"] = opcua_address
        _query["parameters"]["node_namespace"] = node_namespace
        _query["parameters"]["scan_time"] = scan_time
        _query["parameters"]["dead_band"] = dead_band
        _query["parameters"]["id"] = id
        return self.__query(_query)
    
    def update_tag(self, id:str, **kwargs):
        r"""Documentation here

        # Parameters

        - 

        # Returns

        - 
        """
        _query = dict()
        _query["action"] = "update_tag"
        _query["parameters"] = dict()
        _query["parameters"]["id"] = id
        _query["parameters"].update(kwargs)
        return self.__query(_query)
    
    def delete_tag(self, id:str):
        r"""Documentation here

        # Parameters

        - 

        # Returns

        - 
        """
        _query = dict()
        _query["action"] = "delete_tag"
        _query["parameters"] = dict()
        _query["parameters"]["id"] = id
        return self.__query(_query)
    
    def get_tag(
        self,
        id:str=None
        )->Tag:
        r"""Documentation here

        # Parameters

        - 

        # Returns

        - 
        """
        _query = dict()
        _query["action"] = "get_tag"
        _query["parameters"] = dict()
        _query["parameters"]["id"] = id
        return self.__query(_query)

    def get_tags(self):
        r"""Documentation here

        # Parameters

        - 

        # Returns

        - 
        """
        _query = dict()
        _query["action"] = "get_tags"
        return self.__query(_query)
    
    def get_tag_by_name(self, name:str)->Tag|None:
        r"""Documentation here

        # Parameters

        - 

        # Returns

        - 
        """
        _query = dict()
        _query["action"] = "get_tag_by_name"
        _query["parameters"] = dict()
        _query["parameters"]["name"] = name
        return self.__query(_query)
    
    def get_tag_by_display_name(self, display_name:str)->Tag|None:
        r"""Documentation here

        # Parameters

        - 

        # Returns

        - 
        """
        _query = dict()
        _query["action"] = "get_tag_by_display_name"
        _query["parameters"] = dict()
        _query["parameters"]["display_name"] = display_name
        return self.__query(_query)

    def get_tag_by_node_namespace(self, node_namespace:str)->Tag|None:
        r"""Documentation here

        # Parameters

        - 

        # Returns

        - 
        """
        _query = dict()
        _query["action"] = "get_tag_by_node_namespace"
        _query["parameters"] = dict()
        _query["parameters"]["node_namespace"] = node_namespace
        return self.__query(_query)
    
    def get_value(self, id:str)->str|float|int|bool:
        r"""Documentation here

        # Parameters

        - 

        # Returns

        - 
        """
        _query = dict()
        _query["action"] = "get_value"
        _query["parameters"] = dict()
        _query["parameters"]["id"] = id
        return self.__query(_query)
    
    def get_value_by_name(self, tag_name:str)->dict:
        r"""Documentation here

        # Parameters

        - 

        # Returns

        - 
        """
        _query = dict()
        _query["action"] = "get_value_by_name"
        _query["parameters"] = dict()
        _query["parameters"]["name"] = tag_name
        return self.__query(_query)
    
    def get_values_by_name(self, tag_names:list[str])->str|float|int|bool:
        r"""Documentation here

        # Parameters

        - 

        # Returns

        - 
        """
        _query = dict()
        _query["action"] = "get_values_by_name"
        _query["parameters"] = dict()
        _query["parameters"]["names"] = tag_names
        return self.__query(_query)
    
    def get_scan_time(self, id:str)->str|float|int|bool:
        r"""Documentation here

        # Parameters

        - 

        # Returns

        - 
        """
        _query = dict()
        _query["action"] = "get_scan_time"
        _query["parameters"] = dict()
        _query["parameters"]["id"] = id
        return self.__query(_query)
    
    def get_dead_band(self, id:str)->str|float|int|bool:
        r"""Documentation here

        # Parameters

        - 

        # Returns

        - 
        """
        _query = dict()
        _query["action"] = "get_dead_band"
        _query["parameters"] = dict()
        _query["parameters"]["id"] = id
        return self.__query(_query)
    
    def get_display_unit_by_tag(self, tag:str)->str:
        r"""Documentation here

        # Parameters

        - 

        # Returns

        - 
        """
        _query = dict()
        _query["action"] = "get_display_unit_by_tag"
        _query["parameters"] = dict()
        _query["parameters"]["tag"] = tag
        return self.__query(_query)
    
    def set_value(self, id:str, value, timestamp:datetime):
        r"""Documentation here

        # Parameters

        - 

        # Returns

        - 
        """
        if not timestamp:
            timestamp = datetime.now()
        _query = dict()
        _query["action"] = "set_value"
        _query["parameters"] = dict()
        _query["parameters"]["id"] = id
        _query["parameters"]["value"] = value
        _query["parameters"]["timestamp"] = timestamp
        return self.__query(_query)
    
    def set_data_type(self, data_type):
        r"""Documentation here

        # Parameters

        - 

        # Returns

        - 
        """
        _query = dict()
        _query["action"] = "set_data_type"
        _query["parameters"] = dict()
        _query["parameters"]["data_type"] = data_type
        return self.__query(_query)
    
    def is_tag_defined(self, name:str)->bool:
        r"""Documentation here

        # Parameters

        - 

        # Returns

        - 
        """
        _query = dict()
        _query["action"] = "is_tag_defined"
        _query["parameters"] = dict()
        _query["parameters"]["name"] = name
        return self.__query(_query)

    def attach(self, name:str, observer):
        """
        Attaches an observer object to a Tag, observer gets notified when the Tag value changes.
        
        **Parameters:**

        * **name** (str): Tag name.
        * **observer** (str): TagObserver instance.
        """
        _query = dict()
        _query["action"] = "attach_observer"
        _query["parameters"] = dict()
        _query["parameters"]["name"] = name
        _query["parameters"]["observer"] = observer
        return self.__query(_query)

    def detach(self, name:str, observer):
        """
        Detaches an observer object from a Tag, observer no longer gets notified when the Tag value changes.
        
        **Parameters:**

        * **name** (str): Tag name.
        * **observer** (str): TagObserver instance.
        """
        
        _query = dict()
        _query["action"] = "detach_observer"

        _query["parameters"] = dict()
        _query["parameters"]["name"] = name
        _query["parameters"]["observer"] = observer

        self.request(_query)
        result = self.response()

        if result["result"]:
            return result["response"]

    def serialize(self, id:str)->dict:
        r"""Documentation here

        # Parameters

        - 

        # Returns

        - 
        """
        _query = dict()
        _query["action"] = "serialize"
        _query["parameters"] = dict()
        _query["parameters"]["id"] = id
        return self.__query(_query)

    def serialize_by_tag_name(self, name:str)->dict|None:
        r"""Documentation here

        # Parameters

        - 

        # Returns

        - 
        """
        _query = dict()
        _query["action"] = "serialize_by_tag_name"
        _query["parameters"] = dict()
        _query["parameters"]["name"] = name
        return self.__query(_query)

    def __query(self, query:dict)->dict:

        self.request(query)
        result = self.response()
        if result["result"]:
            return result["response"]

    def request(self, query:dict):
        r"""
        It does the request to the tags repository according query's structure, in a thread-safe mechanism

        **Parameters**

        * **query** (dict): Query to tags repository

        ## Query Structure

        ```python
        query = {
            "action": (str)
            "parameters": (dict)
        }
        ```
        ## Valid actions in query

        * set_tag
        * get_tags
        * get_value
        * get_data_type
        * get_unit
        * get_description
        * get_display_name
        * get_min_value
        * get_max_value
        * get_attributes
        * set_value
        * attach
        * detach

        ## Parameters strcuture in query

        ```python
        parameters = {
            "name": (str) tag name to do request
            "unit": (str)[Optional] Unit to get value
            "value": (float)[Optional] If you use *set_value* function, you must pass this parameter
            "observer": (TagObserver)[Optional] If you use *attach* and *detach* function, you must pass this parameter
        }
        ```

        """
        self._request_lock.acquire()
        action = query["action"]
        error_msg = f"Error in CVTEngine with action: {action}"

        try:

            if hasattr(self._cvt, action):

                method = getattr(self._cvt, action)
                
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

    def __true_response(self, resp):
        r"""
        Documentation here
        """
        self._response = {
            "result": True,
            "response": resp
        }

    def response(self)->dict:
        r"""
        Handles the python GIL to emit the request's response in a thread-safe mechanism.
        """
        self._response_lock.acquire()

        result = self._response

        self._request_lock.release()

        return result

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

    