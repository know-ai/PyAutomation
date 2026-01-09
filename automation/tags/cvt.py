import threading, copy, logging
from datetime import datetime
from ..singleton import Singleton
from ..models import FloatType, StringType, IntegerType, BooleanType
from ..modules.users.users import User
from ..modules.users.users import User
from ..utils.decorators import set_event, logging_error_handler
from ..filter import filter
# from ..iad import iad_outlier, iad_frozen_data, iad_out_of_range
from .tag import Tag
from flask_socketio import SocketIO

class CVT:
    """
    Current Value Table (CVT) class for a tag-based repository.

    This class is designed to hold in-memory tag-based values and manage observers for the required tags. It is intended to be used exclusively by PyAutomation and should not be used for other purposes.

    **Usage Example**:

    .. code-block:: python

        >>> from automation.tags import CVT
        >>> _cvt = CVT()

    """

    def __init__(self):
        
        self._tags = dict()
        self.data_types = ["float", "int", "bool", "str"]
        self.sio:SocketIO|None = None

    @logging_error_handler
    def set_socketio(self, sio:SocketIO):
        r"""
        Sets the SocketIO instance for real-time updates.

        **Parameters:**

        * **sio** (SocketIO): The SocketIO server instance.
        """
        self.sio:SocketIO = sio

    @set_event(message=f"Created", classification="Tag", priority=1, criticity=1)
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
        process_filter:bool=False,
        gaussian_filter:bool=False,
        gaussian_filter_threshold:float=1.0,
        gaussian_filter_r_value:float=0.0,
        outlier_detection:bool=False,
        out_of_range_detection:bool=False,
        frozen_data_detection:bool=False,
        manufacturer:str="",
        segment:str="",
        id:str=None,
        user:User=None
        )->tuple[Tag, str]:
        """
        Creates and registers a new Tag in the CVT.

        **Parameters:**

        * **name** (str): Unique tag name.
        * **unit** (str): Base unit.
        * **data_type** (str): Data type ('float', 'int', 'bool', 'str').
        * **description** (str): Tag description.
        * **variable** (str): Physical variable type.
        * **display_name** (str, optional): UI display name.
        * **display_unit** (str, optional): UI display unit.
        * **opcua_address** (str, optional): OPC UA server address.
        * **node_namespace** (str, optional): OPC UA node ID.
        * **scan_time** (int, optional): Polling interval.
        * **dead_band** (float, optional): Deadband value.
        * **user** (User, optional): User creating the tag.

        **Returns:**

        * **tuple**: (Tag object, Success message or Error message).
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

            return None, message
        
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
            process_filter=process_filter,
            gaussian_filter=gaussian_filter,
            gaussian_filter_threshold=gaussian_filter_threshold,
            gaussian_filter_r_value=gaussian_filter_r_value,
            outlier_detection=outlier_detection,
            out_of_range_detection=out_of_range_detection,
            frozen_data_detection=frozen_data_detection,
            manufacturer=manufacturer,
            segment=segment,
            id=id
        )
        self._tags[tag.id] = tag

        return tag, message

    @set_event(message=f"Updated", classification="Tag", priority=1, criticity=3)
    def update_tag(
        self, 
        id:str,  
        user:User=None, 
        **kwargs
        )->tuple[Tag|None, str]:
        r"""
        Updates an existing Tag's properties.

        **Parameters:**

        * **id** (str): Tag ID.
        * **user** (User, optional): User performing the update.
        * **kwargs**: Tag properties to update (e.g., name, unit, scan_time).

        **Returns:**

        * **tuple**: (Updated Tag object, Status message).
        """
        check = dict()
        if "name" in kwargs:
            check["name"] = kwargs["name"]
        if "display_name" in kwargs:
            check["display_name"] = kwargs["display_name"]
        if "node_namespace" in kwargs:
            check["node_namespace"] = kwargs["node_namespace"]
        if "opcua_address" in kwargs:
            check["opcua_address"] = kwargs["opcua_address"]
        has_duplicates, message = self.has_duplicates(**check)
        if has_duplicates:

            return None, message
        
        tag = self._tags[id]
        if "name" in kwargs:
            tag.set_name(name=kwargs["name"])
        if "unit" in kwargs:
            tag.set_unit(unit=kwargs["unit"])
        if "data_type" in kwargs:
            tag.set_data_type(data_type=kwargs["data_type"])
        if "description" in kwargs:
            tag.set_description(description=kwargs["description"])
        if "variable" in kwargs:
            tag.set_variable(variable=kwargs["variable"])
        if "display_name" in kwargs:
            tag.set_display_name(name=kwargs["display_name"])
        if "display_unit" in kwargs:
            tag.set_display_unit(unit=kwargs["display_unit"])
        if "opcua_address" in kwargs:
            tag.set_opcua_address(opcua_address=kwargs["opcua_address"])
        if "opcua_client_name" in kwargs:
            # Si se actualiza opcua_client_name, también actualizar opcua_address si se proporciona
            opcua_client_name = kwargs["opcua_client_name"]
            opcua_address = kwargs.get("opcua_address")  # Puede venir junto con opcua_client_name
            if hasattr(tag, 'set_opcua_client_name'):
                tag.set_opcua_client_name(opcua_client_name, opcua_address=opcua_address)
        if "node_namespace" in kwargs:
            tag.set_node_namespace(node_namespace=kwargs["node_namespace"])
        if "scan_time" in kwargs:
            if isinstance(kwargs["scan_time"], int):
                tag.set_scan_time(scan_time=kwargs["scan_time"])
        if "dead_band" in kwargs:
            tag.set_dead_band(dead_band=kwargs["dead_band"])
        if "segment" in kwargs:
            tag.segment = kwargs["segment"]
        if "manufacturer" in kwargs:
            tag.manufacturer = kwargs["manufacturer"]
        if "gaussian_filter" in kwargs:
            
            if kwargs['gaussian_filter'].lower() in ('1', 'true'):

                tag.gaussian_filter = True

            else:

                tag.gaussian_filter = False

        if "gaussian_filter_r_value" in kwargs:

            tag.gaussian_filter_r_value = kwargs['gaussian_filter_r_value']

        if "gaussian_filter_threshold" in kwargs:

            tag.gaussian_filter_threshold = kwargs['gaussian_filter_threshold']
        
        self._tags[id] = tag

        return tag, f"Tag: {tag.name}"

    @set_event(message=f"Updated", classification="Tag", priority=1, criticity=5)
    def delete_tag(self, id:str, user:User):
        r"""
        Removes a tag from the CVT.

        **Parameters:**

        * **id** (str): Tag ID.
        * **user** (User): User performing the deletion.

        **Returns:**

        * **tuple**: (Deleted Tag object, Status message).
        """
        tag = self._tags.pop(id)
        return tag, f"Tag: {tag.name}"

    @logging_error_handler
    def get_tag(self, id:str)->Tag|None:
        r"""
        Retrieves a tag by its ID.

        **Parameters:**

        * **id** (str): Tag ID.

        **Returns:**

        * **Tag**: The Tag object if found, else None.
        """
        for _id, tag in self._tags.items():

            if _id==id:
                
                return tag

        return None
    
    @logging_error_handler
    def get_unit_by_tag(self, tag:str)->Tag|None:
        r"""
        Gets the base unit of a tag by name.

        **Parameters:**

        * **tag** (str): Tag name.

        **Returns:**

        * **str**: Unit symbol or None.
        """
        for _id, _tag in self._tags.items():

            if _tag.name==tag:
                
                return _tag.unit

        return None
    
    @logging_error_handler
    def get_display_unit_by_tag(self, tag:str)->Tag|None:
        r"""
        Gets the display unit of a tag by name.

        **Parameters:**

        * **tag** (str): Tag name.

        **Returns:**

        * **str**: Display unit symbol or None.
        """
        for _id, _tag in self._tags.items():
            
            if _tag.name==tag:
                
                return _tag.display_unit

        return None

    @logging_error_handler
    def get_tags(self)->list:
        r"""
        Returns a list of all tags (serialized).

        **Returns:**

        * **list**: List of tag dictionaries.
        """
        if self._tags:

            return [tag.serialize() for _, tag in self._tags.items()]
        
        return list()
    
    @logging_error_handler
    def get_tags_by_names(self, names:list)->list:
        r"""
        Returns a list of serialized tags filtering by name.

        **Parameters:**

        * **names** (list): List of tag names.

        **Returns:**

        * **list**: List of tag dictionaries.
        """
        if self._tags:

            return [tag.serialize() for _, tag in self._tags.items() if tag.name in names]
        
        return list()
    
    @logging_error_handler
    def get_field_tags_names(self)->list:
        r"""
        Returns names of tags that are connected to field devices (have OPC UA address and namespace).

        **Returns:**

        * **list**: List of tag names.
        """
        if self._tags:

            return [tag.name for _, tag in self._tags.items() if tag.opcua_address and tag.node_namespace]
        
        return list()
    
    @logging_error_handler
    def get_cuasi_field_tags_names(self)->list:
        r"""
        Returns names of tags that have an OPC UA address (potentially field tags).

        **Returns:**

        * **list**: List of tag names.
        """
        if self._tags:

            return [tag.name for _, tag in self._tags.items() if tag.opcua_address]
        
        return list()
    
    @logging_error_handler
    def get_tag_by_name(self, name:str)->Tag|None:
        r"""
        Retrieves a tag object by its name.

        **Parameters:**

        * **name** (str): Tag name.

        **Returns:**

        * **Tag**: Tag object or None.
        """
        for _, tag in self._tags.items():
            
            if tag.get_name()==name:
                
                return tag

        return None
    
    @logging_error_handler
    def get_tag_by_display_name(self, display_name:str)->Tag|None:
        r"""
        Retrieves a tag object by its display name.

        **Parameters:**

        * **display_name** (str): Tag display name.

        **Returns:**

        * **Tag**: Tag object or None.
        """
        for _, tag in self._tags.items():

            if tag.get_display_name()==display_name:
                
                return tag

        return None

    @logging_error_handler
    def get_tag_by_node_namespace(self, node_namespace:str)->Tag|None:
        r"""
        Retrieves a tag object by its OPC UA node namespace.

        **Parameters:**

        * **node_namespace** (str): Node Namespace ID.

        **Returns:**

        * **Tag**: Tag object or None.
        """
        for _, tag in self._tags.items():

            if tag.get_node_namespace()==node_namespace:
                
                return tag

        return None
    
    @logging_error_handler
    def get_value(self, id:str)->str|float|int|bool:
        r"""
        Gets the current value of a tag by ID.

        **Parameters:**

        * **id** (str): Tag ID.

        **Returns:**

        * **value**: The current value.
        """
        tag = self._tags[id]        
        _new_object = copy.copy(tag.get_value())
        return _new_object
    
    @logging_error_handler
    def get_timestamp(self, id:str)->datetime:
        r"""
        Gets the timestamp of a tag by ID.

        **Parameters:**

        * **id** (str): Tag ID.

        **Returns:**

        * **datetime**: Last update timestamp.
        """
        tag = self._tags[id] 

        return tag.get_timestamp()
    
    @logging_error_handler
    def get_value_by_name(self, name:str)->str|float|int|bool:
        r"""
        Gets the value, unit, and timestamp of a tag by name.

        **Parameters:**

        * **name** (str): Tag name.

        **Returns:**

        * **dict**: Dictionary with 'value', 'unit', and 'timestamp'.
        """

        tag = self.get_tag_by_name(name=name)  

        return {
                "value": tag.get_value(),
                "unit": tag.get_unit(),
                "timestamp": tag.get_timestamp()
            }

    @logging_error_handler
    def get_values_by_name(self, names:list[str])->str|float|int|bool:
        r"""
        Gets values for multiple tags by name.

        **Parameters:**

        * **names** (list): List of tag names.

        **Returns:**

        * **dict**: Dictionary mapping tag names to their values and metadata.
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
    
    @logging_error_handler
    @filter
    # @iad_frozen_data
    # @iad_out_of_range
    # @iad_outlier
    def set_value(self, id:str, value, timestamp:datetime):
        """
        Sets a new value for a tag.

        This method applies filters (like deadband) and emits a socket event if configured.

        **Parameters:**

        * **id** (str): Tag ID.
        * **value**: New value.
        * **timestamp** (datetime): Timestamp of the value.

        **Returns:**

        * **value**: The value that was set (or filtered).
        """
        from .. import TIMEZONE
        tag = self._tags[id]
        
        # Deadband Logic Wrapper for CVT
        

        if tag.dead_band and isinstance(value, (int, float)):
            try:
                current_value = tag.value.value
                if abs(value - current_value) < tag.dead_band:
                    return value
            except Exception as e:
                logging.error(f"Error in deadband logic: {e}")

        tag.set_value(value=value, timestamp=timestamp)
        if self.sio:
            timestamp = timestamp.astimezone(TIMEZONE)
            self._tags[id].timestamp = timestamp
            self.sio.emit("on.tag", data=self._tags[id].serialize())

        return value

    @logging_error_handler
    def set_data_type(self, data_type):
        r"""
        Registers a new data type in the allowed types list.

        **Parameters:**

        * **data_type**: Data type definition.
        """
        self.data_types.append(data_type)
        self.data_types = list(set(self.data_types))
    
    @logging_error_handler
    def is_tag_defined(self, name:str)->bool:
        r"""
        Checks if a tag is defined in the CVT.

        **Parameters:**

        * **name** (str): Tag name.

        **Returns:**

        * **bool**: True if defined, False otherwise.
        """

        return name in self._tags
    
    @logging_error_handler
    def attach_observer(self, name, observer):
        r"""
        Attaches a new observer to a tag object defined by name.
        
        **Parameters:**

        * **name** (str): Tag name.
        * **observer** (TagObserver): Observer object.
        """
        tag = self.get_tag_by_name(name)
        if tag:
            
            self._tags[tag.id].attach(observer)
        
        else:
            logger = logging.getLogger("pyautomation")
            logger.warning(f"{name} tag Not exists in CVT.attach_observer method")

    @logging_error_handler
    def detach_observer(self, name, observer):
        r"""
        Detaches an observer from a tag object defined by name.
        
        **Parameters:**

        * **name** (str): Tag name.
        * **observer** (TagObserver): Observer object.
        """
        tag = self.get_tag_by_name(name)
        self._tags[tag.id].detach(observer)

    @logging_error_handler
    def has_duplicates(self, tag:Tag=None, name:str=None, display_name:str=None, node_namespace:str=None, opcua_address:str=None):
        r"""
        Checks for duplicate tag definitions.

        **Parameters:**

        * **tag** (Tag, optional): Existing tag object to compare against.
        * **name** (str, optional): Name to check.
        * **display_name** (str, optional): Display name to check.
        * **node_namespace** (str, optional): Node namespace to check.
        * **opcua_address** (str, optional): OPC UA address to check.

        **Returns:**

        * **tuple**: (Has Duplicates bool, Message str).
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

    @logging_error_handler
    def serialize(self, id:str)->dict:
        r"""
        Serializes a tag by ID.

        **Parameters:**

        * **id** (str): Tag ID.

        **Returns:**

        * **dict**: Serialized tag.
        """
        return self._tags[id].serialize()
    
    @logging_error_handler
    def serialize_by_tag_name(self, name:str)->dict|None:
        r"""
        Serializes a tag by Name.

        **Parameters:**

        * **name** (str): Tag name.

        **Returns:**

        * **dict**: Serialized tag.
        """
        tag = self.get_tag_by_name(name)

        if tag:

            return tag.serialize()


class CVTEngine(Singleton):
    """
    Current Value Table (CVT) Engine class for a tag-based, thread-safe repository.

    This class is designed to hold in-memory tag-based values and manage observers for the required tags. It is implemented as a singleton, ensuring that each sub-thread within the PyAutomation application can access and modify tags in a thread-safe manner.

    It acts as a thread-safe wrapper around the `CVT` class, using a query-based mechanism (`request`/`response`) to handle operations.

    **Usage Example**:

    .. code-block:: python

        >>> from automation.tags import CVTEngine
        >>> tag_engine = CVTEngine()
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

    @logging_error_handler
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
        scan_time:int=0,
        dead_band:float=0.0,
        process_filter:bool=False,
        gaussian_filter:bool=False,
        gaussian_filter_threshold:float=1.0,
        gaussian_filter_r_value:float=0.0,
        outlier_detection:bool=False,
        out_of_range_detection:bool=False,
        frozen_data_detection:bool=False,
        manufacturer:str="",
        segment:str="",
        id:str="",
        user:User|None=None
        )->tuple[Tag, str]:
        r"""
        Thread-safe method to create a new tag.

        See `CVT.set_tag` for parameters.
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
        _query["parameters"]["process_filter"] = process_filter
        _query["parameters"]["gaussian_filter"] = gaussian_filter
        _query["parameters"]["gaussian_filter_threshold"] = gaussian_filter_threshold
        _query["parameters"]["gaussian_filter_r_value"] = gaussian_filter_r_value
        _query["parameters"]["outlier_detection"] = outlier_detection
        _query["parameters"]["out_of_range_detection"] = out_of_range_detection
        _query["parameters"]["frozen_data_detection"] = frozen_data_detection
        _query["parameters"]["manufacturer"] = manufacturer
        _query["parameters"]["segment"] = segment
        _query["parameters"]["id"] = id
        _query["parameters"]["user"] = user
        return self.__query(_query)
    
    @logging_error_handler
    def update_tag(
            self, 
            id:str,  
            user:User=None, 
            **kwargs
        ):
        r"""
        Thread-safe method to update a tag.

        See `CVT.update_tag` for parameters.
        """
        _query = dict()
        _query["action"] = "update_tag"
        _query["parameters"] = dict()
        _query["parameters"]["id"] = id
        _query["parameters"]["user"] = user
        for key, value in kwargs.items():

            _query["parameters"][key] = value
        return self.__query(_query)
    
    @logging_error_handler
    def delete_tag(self, id:str, user:User|None=None):
        r"""
        Thread-safe method to delete a tag.

        See `CVT.delete_tag` for parameters.
        """
        _query = dict()
        _query["action"] = "delete_tag"
        _query["parameters"] = dict()
        _query["parameters"]["id"] = id
        _query["parameters"]["user"] = user
        return self.__query(_query)
    
    @logging_error_handler
    def get_tag(
        self,
        id:str=None
        )->Tag:
        r"""
        Thread-safe method to get a tag object.
        """
        _query = dict()
        _query["action"] = "get_tag"
        _query["parameters"] = dict()
        _query["parameters"]["id"] = id
        return self.__query(_query)

    @logging_error_handler
    def get_tags(self):
        r"""
        Thread-safe method to get all tags.
        """
        _query = dict()
        _query["action"] = "get_tags"
        return self.__query(_query)

    @logging_error_handler
    def get_tags_by_names(self, names:list[str]):
        r"""
        Thread-safe method to get tags by names.
        """
        _query = dict()
        _query["action"] = "get_tags_by_names"
        _query["parameters"] = dict()
        _query["parameters"]["names"] = names
        return self.__query(_query)
    
    @logging_error_handler
    def get_tag_by_name(self, name:str)->Tag|None:
        r"""
        Thread-safe method to get a tag by name.
        """
        _query = dict()
        _query["action"] = "get_tag_by_name"
        _query["parameters"] = dict()
        _query["parameters"]["name"] = name
        return self.__query(_query)
    
    @logging_error_handler
    def get_tag_by_display_name(self, display_name:str)->Tag|None:
        r"""
        Thread-safe method to get a tag by display name.
        """
        _query = dict()
        _query["action"] = "get_tag_by_display_name"
        _query["parameters"] = dict()
        _query["parameters"]["display_name"] = display_name
        return self.__query(_query)

    @logging_error_handler
    def get_tag_by_node_namespace(self, node_namespace:str)->Tag|None:
        r"""
        Thread-safe method to get a tag by node namespace.
        """
        _query = dict()
        _query["action"] = "get_tag_by_node_namespace"
        _query["parameters"] = dict()
        _query["parameters"]["node_namespace"] = node_namespace
        return self.__query(_query)
    
    @logging_error_handler
    def get_value(self, id:str)->str|float|int|bool:
        r"""
        Thread-safe method to get a tag value by ID.
        """
        _query = dict()
        _query["action"] = "get_value"
        _query["parameters"] = dict()
        _query["parameters"]["id"] = id
        return self.__query(_query)
    
    @logging_error_handler
    def get_value_by_name(self, tag_name:str)->dict:
        r"""
        Thread-safe method to get a tag value by name.
        """
        _query = dict()
        _query["action"] = "get_value_by_name"
        _query["parameters"] = dict()
        _query["parameters"]["name"] = tag_name
        return self.__query(_query)
    
    @logging_error_handler
    def get_values_by_name(self, tag_names:list[str])->str|float|int|bool:
        r"""
        Thread-safe method to get multiple tag values.
        """
        _query = dict()
        _query["action"] = "get_values_by_name"
        _query["parameters"] = dict()
        _query["parameters"]["names"] = tag_names
        return self.__query(_query)
    
    @logging_error_handler
    def get_scan_time(self, id:str)->str|float|int|bool:
        r"""
        Thread-safe method to get scan time.
        """
        _query = dict()
        _query["action"] = "get_scan_time"
        _query["parameters"] = dict()
        _query["parameters"]["id"] = id
        return self.__query(_query)
    
    @logging_error_handler
    def get_dead_band(self, id:str)->str|float|int|bool:
        r"""
        Thread-safe method to get deadband.
        """
        _query = dict()
        _query["action"] = "get_dead_band"
        _query["parameters"] = dict()
        _query["parameters"]["id"] = id
        return self.__query(_query)
    
    @logging_error_handler
    def get_display_unit_by_tag(self, tag:str)->str:
        r"""
        Thread-safe method to get display unit.
        """
        _query = dict()
        _query["action"] = "get_display_unit_by_tag"
        _query["parameters"] = dict()
        _query["parameters"]["tag"] = tag
        return self.__query(_query)
    
    @logging_error_handler
    def set_value(self, id:str, value, timestamp:datetime):
        r"""
        Thread-safe method to set a tag value.
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
    
    @logging_error_handler
    def set_data_type(self, data_type):
        r"""
        Thread-safe method to set data type.
        """
        _query = dict()
        _query["action"] = "set_data_type"
        _query["parameters"] = dict()
        _query["parameters"]["data_type"] = data_type
        return self.__query(_query)
    
    @logging_error_handler
    def is_tag_defined(self, name:str)->bool:
        r"""
        Thread-safe method to check if tag is defined.
        """
        _query = dict()
        _query["action"] = "is_tag_defined"
        _query["parameters"] = dict()
        _query["parameters"]["name"] = name
        return self.__query(_query)

    @logging_error_handler
    def attach(self, name:str, observer):
        """
        Attaches an observer to a Tag in a thread-safe way.
        """
        _query = dict()
        _query["action"] = "attach_observer"
        _query["parameters"] = dict()
        _query["parameters"]["name"] = name
        _query["parameters"]["observer"] = observer
        return self.__query(_query)

    @logging_error_handler
    def detach(self, name:str, observer):
        """
        Detaches an observer from a Tag in a thread-safe way.
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

    @logging_error_handler
    def serialize(self, id:str)->dict:
        r"""
        Thread-safe serialization by ID.
        """
        _query = dict()
        _query["action"] = "serialize"
        _query["parameters"] = dict()
        _query["parameters"]["id"] = id
        return self.__query(_query)
    
    @logging_error_handler
    def serialize_by_tag_name(self, name:str)->dict|None:
        r"""
        Thread-safe serialization by name.
        """
        _query = dict()
        _query["action"] = "serialize_by_tag_name"
        _query["parameters"] = dict()
        _query["parameters"]["name"] = name
        return self.__query(_query)

    @logging_error_handler
    def __query(self, query:dict)->dict:

        self.request(query)
        result = self.response()
        if result["result"]:
            return result["response"]

    @logging_error_handler
    def request(self, query:dict):
        r"""
        Executes a request to the CVT in a thread-safe mechanism using locks.

        **Parameters:**

        * **query** (dict): Dictionary defining the action and parameters.
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

    @logging_error_handler
    def __log_error(self, e:Exception, msg:str):
        r"""
        Logs error and sets error response.
        """
        logging.error(f"{e} Message: {msg}")
        self._response = {
            "result": False,
            "response": None
        }

    @logging_error_handler
    def __true_response(self, resp):
        r"""
        Sets success response.
        """
        self._response = {
            "result": True,
            "response": resp
        }

    @logging_error_handler
    def response(self)->dict:
        r"""
        Retrieves the response from the last request, handling thread synchronization.
        """
        self._response_lock.acquire()

        result = self._response

        self._request_lock.release()

        return result

    @logging_error_handler
    def __getstate__(self):

        self._response_lock.release()
        state = self.__dict__.copy()
        del state['_request_lock']
        del state['_response_lock']
        return state

    @logging_error_handler
    def __setstate__(self, state):
        
        self.__dict__.update(state)
        self._request_lock = threading.Lock()
        self._response_lock = threading.Lock()
        self._response_lock.acquire()
