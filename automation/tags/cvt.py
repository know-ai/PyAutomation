import threading
import copy, logging
from ..singleton import Singleton
from ..models import FloatType, StringType, IntegerType, BooleanType
from .tag import Tag

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

    def is_tag_defined(self, name:str)->bool:

        return name in self._tags
    
    def set_data_type(self, data_type):

        self.data_types.append(data_type)
        self.data_types = list(set(self.data_types))
    
    def set_tag(
        self, 
        id:str,
        name:str, 
        unit:str, 
        data_type:str, 
        description:str, 
        display_name:str="",
        opcua_address:str="",
        node_namespace:str=""
        ):
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

        tag = Tag(
            id=id,
            name=name,
            unit=unit,
            data_type=data_type,
            description=description,
            display_name=display_name,
            opcua_address=opcua_address,
            node_namespace=node_namespace
        )

        self._tags[tag.id] = tag

    def update_tag(self, id:str, **kwargs):
        tag = self._tags[id]
        tag.update(**kwargs)
        self._tags[id] = tag

    def delete_tag(self, id:str):
        
        self._tags.pop(id)

    def get_tags(self)->list:
        """Returns a list of the defined tags names.
        """

        return [value.serialize() for _, value in self._tags.items()]
    
    def get_tag_by_name(self, name:str)->Tag|None:
        r"""
        Documentation here
        """
        for _, tag in self._tags.items():

            if tag.get_name()==name:
                
                return tag

        return None
    
    def get_tag(self, id:str)->Tag|None:
        r"""
        Documentation here
        """
        for _id, tag in self._tags.items():

            if _id==id:
                
                return tag

        return None
    
    def get_tag_by_display_name(self, display_name:str)->Tag|None:
        r"""
        Documentation here
        """
        for _, tag in self._tags.items():

            if tag.get_display_name()==display_name:
                
                return tag

        return None

    def get_tag_by_node_namespace(self, node_namespace:str)->Tag|None:
        r"""
        Documentation here
        """
        for _, tag in self._tags.items():

            if tag.get_node_namespace()==node_namespace:
                
                return tag

        return None
    
    def set_value(self, id:str, value):
        """Sets a new value for a defined tag.
        
        # Parameters
        name (str):
            Tag name.
        value (float, int, bool): 
            Tag value ("int", "float", "bool")
        """
        self._tags[id].set_value(value)

    def get_value(self, id:str)->str|float|int|bool:
        tag = self._tags[id]        
        _new_object = copy.copy(tag.get_value())
        return _new_object
    
    def attach_observer(self, name, observer):
        """Attaches a new observer to a tag object defined by name.
        
        # Parameters
        name (str):
            Tag name.
        observer (TagObserver): 
            Tag observer object, will update once a tag object is changed.
        """
        tag = self.get_tag_by_name(name)
        if tag:
            self._tags[tag.id].attach(observer)

    def detach_observer(self, name, observer):
        """Detaches an observer from a tag object defined by name.
        
        # Parameters
        name (str):
            Tag name.
        observer (TagObserver): 
            Tag observer object.
        """
        tag = self.get_tag_by_name(name)
        self._tags[tag.id].detach(observer)
    
    def serialize(self, id:str)->dict:
        """Returns a tag type defined by name.
        
        # Parameters
        name (str):
            Tag name.
        """
        return self._tags[id].serialize()
    
    def serialize_by_tag_name(self, name:str)->dict|None:
        r"""
        Documentation here
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

    def is_tag_defined(self, name:str)->bool:
        _query = dict()
        _query["action"] = "is_tag_defined"
        _query["parameters"] = dict()
        _query["parameters"]["name"] = name
        return self.__query(_query)
    
    def set_data_type(self, data_type):
        _query = dict()
        _query["action"] = "set_data_type"
        _query["parameters"] = dict()
        _query["parameters"]["data_type"] = data_type
        return self.__query(_query)
    
    def get_tag(
        self,
        id:str=None
        ):
        _query = dict()
        _query["action"] = "get_tag"
        _query["parameters"] = dict()
        _query["parameters"]["id"] = id
        return self.__query(_query)

    def set_tag(
        self, 
        name:str, 
        unit:str, 
        data_type:str, 
        description:str, 
        display_name:str="",
        opcua_address:str="",
        node_namespace:str="",
        id:str=None
        ):
        _query = dict()
        _query["action"] = "set_tag"
        _query["parameters"] = dict()
        _query["parameters"]["name"] = name
        _query["parameters"]["unit"] = unit
        _query["parameters"]["data_type"] = data_type
        _query["parameters"]["description"] = description
        _query["parameters"]["display_name"] = display_name
        _query["parameters"]["opcua_address"] = opcua_address
        _query["parameters"]["node_namespace"] = node_namespace
        _query["parameters"]["id"] = id
        return self.__query(_query)
    
    def update_tag(self, id:str, **kwargs):
        _query = dict()
        _query["action"] = "update_tag"
        _query["parameters"] = dict()
        _query["parameters"]["id"] = id
        _query["parameters"].update(kwargs)
        return self.__query(_query)
    
    def delete_tag(self, id:str):
        _query = dict()
        _query["action"] = "delete_tag"
        _query["parameters"] = dict()
        _query["parameters"]["id"] = id
        return self.__query(_query)

    def get_tags(self):
        _query = dict()
        _query["action"] = "get_tags"
        return self.__query(_query)
    
    def get_tag_by_name(self, name:str)->Tag|None:
        _query = dict()
        _query["action"] = "get_tag_by_name"
        _query["parameters"] = dict()
        _query["parameters"]["name"] = name
        return self.__query(_query)
    
    def get_tag_by_display_name(self, display_name:str)->Tag|None:
        _query = dict()
        _query["action"] = "get_tag_by_display_name"
        _query["parameters"] = dict()
        _query["parameters"]["display_name"] = display_name
        return self.__query(_query)

    def get_tag_by_node_namespace(self, node_namespace:str)->Tag|None:
        _query = dict()
        _query["action"] = "get_tag_by_node_namespace"
        _query["parameters"] = dict()
        _query["parameters"]["node_namespace"] = node_namespace
        return self.__query(_query)
    
    def set_value(self, id:str, value):
        _query = dict()
        _query["action"] = "set_value"
        _query["parameters"] = dict()
        _query["parameters"]["id"] = id
        _query["parameters"]["value"] = value
        return self.__query(_query)

    def get_value(self, id:str)->str|float|int|bool:
        _query = dict()
        _query["action"] = "get_value"
        _query["parameters"] = dict()
        _query["parameters"]["id"] = id
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
        _query = dict()
        _query["action"] = "serialize"
        _query["parameters"] = dict()
        _query["parameters"]["id"] = id
        return self.__query(_query)

    def serialize_by_tag_name(self, name:str)->dict|None:
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