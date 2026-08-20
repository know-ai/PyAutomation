import threading, copy, logging
from datetime import datetime
from ..singleton import Singleton
from ..models import FloatType, StringType, IntegerType, BooleanType
from ..modules.users.users import User
from ..modules.users.users import User
from ..utils.decorators import set_event, logging_error_handler
from ..utils.tag_audit import describe_tag_update
# from ..iad import iad_outlier, iad_frozen_data, iad_out_of_range
from .tag import Tag, _scope_owns_tag
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
        self._name_index = dict()
        self._namespace_index = dict()
        self.lock_contention = 0
        self.data_types = ["float", "int", "bool", "str"]
        self.sio:SocketIO|None = None

    def _index_tag(self, tag: Tag) -> None:
        if tag is None:
            return
        self._name_index[tag.name] = tag.id
        namespace = getattr(tag, "node_namespace", None)
        if namespace:
            self._namespace_index[namespace] = tag.id

    def _unindex_tag(self, tag: Tag) -> None:
        if tag is None:
            return
        if self._name_index.get(tag.name) == tag.id:
            self._name_index.pop(tag.name, None)
        namespace = getattr(tag, "node_namespace", None)
        if namespace and self._namespace_index.get(namespace) == tag.id:
            self._namespace_index.pop(namespace, None)

    @logging_error_handler
    def set_socketio(self, sio:SocketIO):
        r"""
        Sets the SocketIO instance for real-time updates.

        **Parameters:**

        * **sio** (SocketIO): The SocketIO server instance.
        """
        self.sio:SocketIO = sio

    @set_event(message="Tag created", classification="Configuration", priority=1, criticity=1)
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
        filter_enabled:bool=False,
        filter_wavelet:str="db4",
        filter_level:int=4,
        filter_threshold_factor:float=3.0,
        filter_persist:bool=False,
        outlier_detection:bool=False,
        out_of_range_detection:bool=False,
        frozen_data_detection:bool=False,
        manufacturer:str="",
        segment:str="",
        kp:float=None,
        id:str=None,
        user:User=None,
        area:str=None,
        owner_node:str=None
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

        
        try:
            from ..node_scope import get_node_scope

            scope = get_node_scope()
        except (ImportError, AttributeError):
            scope = None
        if scope is not None and getattr(scope, "enabled", False):
            if not getattr(scope, "is_valid", False):
                return None, "Invalid node scope"
            area = area or getattr(scope, "area", None)
            owner_node = owner_node or getattr(scope, "node_id", None)
            owns_area = getattr(scope, "owns_area", None)
            area_owned = (
                bool(owns_area(area))
                if callable(owns_area)
                else area == getattr(scope, "area", None)
            )
            try:
                owner_owned = bool(scope.owns_node(owner_node))
            except Exception:
                owner_owned = False
            if not area_owned or not owner_owned:
                return None, "Tag is not owned by this node scope"

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
            filter_enabled=filter_enabled,
            filter_wavelet=filter_wavelet,
            filter_level=filter_level,
            filter_threshold_factor=filter_threshold_factor,
            filter_persist=filter_persist,
            outlier_detection=outlier_detection,
            out_of_range_detection=out_of_range_detection,
            frozen_data_detection=frozen_data_detection,
            manufacturer=manufacturer,
            segment=segment,
            kp=kp,
            id=id,
            area=area,
            owner_node=owner_node,
        )
        self._tags[tag.id] = tag
        self._index_tag(tag)

        return tag, message

    @set_event(message="Tag updated", classification="Configuration", priority=1, criticity=3)
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
        change_description = describe_tag_update(tag, kwargs)
        self._unindex_tag(tag)
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
        if "area" in kwargs:
            tag.area = kwargs["area"]
        if "owner_node" in kwargs:
            tag.owner_node = kwargs["owner_node"]
        if "kp" in kwargs:
            tag.set_kp(kp=kwargs["kp"])
        if "filter_enabled" in kwargs:
            value = kwargs["filter_enabled"]
            if isinstance(value, str):
                tag.filter_enabled = value.strip().lower() in ("1", "true", "yes", "on")
            else:
                tag.filter_enabled = bool(value)
        if "filter_wavelet" in kwargs:
            tag.filter_wavelet = kwargs["filter_wavelet"]
        if "filter_level" in kwargs:
            tag.filter_level = int(kwargs["filter_level"])
        if "filter_threshold_factor" in kwargs:
            tag.filter_threshold_factor = float(kwargs["filter_threshold_factor"])
        if "filter_persist" in kwargs:
            value = kwargs["filter_persist"]
            if isinstance(value, str):
                tag.filter_persist = value.strip().lower() in ("1", "true", "yes", "on")
            else:
                tag.filter_persist = bool(value)
        
        self._tags[id] = tag
        self._index_tag(tag)

        return tag, change_description

    @set_event(message="Tag deleted", classification="Configuration", priority=1, criticity=5)
    def delete_tag(self, id:str, user:User):
        r"""
        Removes a tag from the CVT.

        **Parameters:**

        * **id** (str): Tag ID.
        * **user** (User): User performing the deletion.

        **Returns:**

        * **tuple**: (Deleted Tag object, Status message).
        """
        tag = self._tags.get(id)
        if tag is None:
            return None, f"Tag {id} not found"
        tag.detach_all_observers()
        tag = self._tags.pop(id)
        self._unindex_tag(tag)
        return tag, f"Tag: {tag.name}"

    def observer_counts(self)->dict:
        r"""
        Snapshot of live observers. A tag may hold more than one observer
        (SAF TagObserver, MachineObserver, alarm). Counts must stay stable
        when the catalogue is fixed; they are not capped by tag count.
        """
        from .tag import MachineObserver

        total = 0
        machines = 0
        for tag in self._tags.values():
            observers = getattr(tag, "_observers", None) or ()
            total += len(observers)
            for observer in observers:
                if isinstance(observer, MachineObserver):
                    machines += 1
        return {
            "TAG_OBSERVER_COUNT": total,
            "MACHINE_OBSERVER_COUNT": machines,
        }

    def prune_not_owned(self, scope) -> list[str]:
        """Drop foreign runtime objects without mutating the shared catalog."""
        removed = []
        for tag_id, tag in list(self._tags.items()):
            if scope.owns_tag(tag):
                continue
            tag.detach_all_observers()
            self._tags.pop(tag_id, None)
            self._unindex_tag(tag)
            removed.append(tag.name)
        return removed

    @logging_error_handler
    def get_tag(self, id:str)->Tag|None:
        r"""
        Retrieves a tag by its ID.

        **Parameters:**

        * **id** (str): Tag ID.

        **Returns:**

        * **Tag**: The Tag object if found, else None.
        """
        return self._tags.get(id)
    
    @logging_error_handler
    def get_unit_by_tag(self, tag:str)->Tag|None:
        r"""
        Gets the base unit of a tag by name.

        **Parameters:**

        * **tag** (str): Tag name.

        **Returns:**

        * **str**: Unit symbol or None.
        """
        tag = self.get_tag_by_name(tag)
        if tag is None:
            return None
        return tag.unit
    
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
    def get_tags_filtered(self, manufacturer:str=None, segment:str=None)->list:
        r"""
        Returns a list of tags with only name, display_unit, variable, display_name,
        optionally filtered by manufacturer and/or segment.

        **Parameters:**

        * **manufacturer** (str, optional): Filter by manufacturer.
        * **segment** (str, optional): Filter by segment.

        **Returns:**

        * **list**: List of tag dicts with keys: name, display_unit, variable, display_name.
        """
        if not self._tags:
            return list()
        result = []
        for _, tag in self._tags.items():
            if manufacturer is not None and manufacturer != "" and tag.manufacturer != manufacturer:
                continue
            if segment is not None and segment != "" and tag.segment != segment:
                continue
            result.append({
                "name": tag.name,
                "display_unit": tag.get_display_unit(),
                "variable": tag.get_variable(),
                "display_name": tag.get_display_name(),
            })
        return result

    @logging_error_handler
    def get_tags_by_kp_range(self, kp_min:float, kp_max:float, segment:str=None)->list:
        r"""
        Returns a list of serialized tags whose KP is between kp_min and kp_max (inclusive).

        **Parameters:**

        * **kp_min** (float): Lower bound for KP.
        * **kp_max** (float): Upper bound for KP.
        * **segment** (str): Optional segment name to filter by.

        **Returns:**

        * **list**: List of tag dictionaries.
        """
        if not self._tags:
            return list()
        lower = min(kp_min, kp_max)
        upper = max(kp_min, kp_max)
        return [
            tag.serialize()
            for _, tag in self._tags.items()
            if tag.get_kp() is not None and lower <= tag.get_kp() <= upper
            and (segment is None or tag.segment == segment)
        ]

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
        tag_id = self._name_index.get(name)
        if tag_id is None:
            return None
        return self._tags.get(tag_id)
    
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
        tag_id = self._namespace_index.get(node_namespace)
        if tag_id is None:
            return None
        return self._tags.get(tag_id)
    
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
    # @iad_frozen_data
    # @iad_out_of_range
    # @iad_outlier
    def set_value(self, id:str, value, timestamp:datetime, quality:float=1.0):
        """
        Sets a new value for a tag.

        This method applies filters (like deadband) and emits a socket event if configured.

        **Parameters:**

        * **id** (str): Tag ID.
        * **value**: New value.
        * **timestamp** (datetime): Timestamp of the value.
        * **quality** (float, optional): OPC-style quality code.

        **Returns:**

        * **value**: The value that was set (or filtered).
        """
        tag = self._tags.get(id)
        if tag is None:
            return None
        if not _scope_owns_tag(tag):
            logging.getLogger("pyautomation").error(
                "CVT rejected foreign write tag=%s area=%s owner_node=%s",
                getattr(tag, "name", id),
                getattr(tag, "area", None),
                getattr(tag, "owner_node", None),
            )
            return None

        payload = None
        try:
            locked = getattr(tag._lock, "locked", None)
            if callable(locked) and locked():
                self.lock_contention += 1
        except Exception:
            pass
        applied = tag.set_value(value=value, timestamp=timestamp, quality=quality)
        if applied is False:
            return value
        if self.sio:
            payload = tag.serialize_socket()

        if payload is not None and self.sio:
            self.sio.emit("on.tag", data=payload)

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

        return name in self._name_index
    
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
        filter_enabled:bool=False,
        filter_wavelet:str="db4",
        filter_level:int=4,
        filter_threshold_factor:float=3.0,
        filter_persist:bool=False,
        outlier_detection:bool=False,
        out_of_range_detection:bool=False,
        frozen_data_detection:bool=False,
        manufacturer:str="",
        segment:str="",
        kp:float=None,
        id:str="",
        user:User|None=None,
        area:str|None=None,
        owner_node:str|None=None
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
        _query["parameters"]["filter_enabled"] = filter_enabled
        _query["parameters"]["filter_wavelet"] = filter_wavelet
        _query["parameters"]["filter_level"] = filter_level
        _query["parameters"]["filter_threshold_factor"] = filter_threshold_factor
        _query["parameters"]["filter_persist"] = filter_persist
        _query["parameters"]["outlier_detection"] = outlier_detection
        _query["parameters"]["out_of_range_detection"] = out_of_range_detection
        _query["parameters"]["frozen_data_detection"] = frozen_data_detection
        _query["parameters"]["manufacturer"] = manufacturer
        _query["parameters"]["segment"] = segment
        _query["parameters"]["kp"] = kp
        _query["parameters"]["id"] = id
        _query["parameters"]["user"] = user
        _query["parameters"]["area"] = area
        _query["parameters"]["owner_node"] = owner_node
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

    def prune_not_owned(self, scope) -> list[str]:
        """Thread-safe local-only pruning used at reconnect boundaries."""
        with self._request_lock:
            return self._cvt.prune_not_owned(scope)
    
    @logging_error_handler
    def get_tag(
        self,
        id:str=None
        )->Tag:
        r"""
        O(1) lookup by tag id. Bypasses the administrative request/response queue.
        """
        return self._cvt.get_tag(id)

    @logging_error_handler
    def tag_count(self)->int:
        return len(self._cvt._tags)

    def lock_contention(self)->int:
        return int(getattr(self._cvt, "lock_contention", 0) or 0)

    def observer_counts(self)->dict:
        r"""
        Snapshot of live observers across the CVT (soak / health).

        ``TAG_OBSERVER_COUNT`` is the sum of observers per tag (a tag may
        have TagObserver + MachineObserver + alarm observers). It is **not**
        bounded by ``CVT_TAG_COUNT``. With a fixed catalogue both counts
        must be stable.
        """
        return self._cvt.observer_counts()

    @logging_error_handler
    def iter_tags(self)->list:
        return list(self._cvt._tags.values())

    @logging_error_handler
    def iter_tags_for_opcua_client(self, client_name:str, server_url:str|None=None)->list:
        matched = []
        client_key = (client_name or "").lower()
        for tag in self._cvt._tags.values():
            tag_client = (getattr(tag, "opcua_client_name", None) or "").lower()
            if tag_client and tag_client == client_key:
                matched.append(tag)
                continue
            try:
                address = tag.get_opcua_address()
            except Exception:
                address = None
            if server_url and address == server_url:
                matched.append(tag)
        return matched

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
    def get_tags_filtered(self, manufacturer:str=None, segment:str=None):
        r"""
        Thread-safe method to get tags filtered by manufacturer and/or segment.
        Returns list of dicts with name, display_unit, variable, display_name.
        """
        _query = dict()
        _query["action"] = "get_tags_filtered"
        _query["parameters"] = dict()
        _query["parameters"]["manufacturer"] = manufacturer
        _query["parameters"]["segment"] = segment
        return self.__query(_query)

    @logging_error_handler
    def get_tags_by_kp_range(self, kp_min:float, kp_max:float, segment:str=None):
        r"""
        Thread-safe method to get tags whose KP is within a given range.
        """
        _query = dict()
        _query["action"] = "get_tags_by_kp_range"
        _query["parameters"] = dict()
        _query["parameters"]["kp_min"] = kp_min
        _query["parameters"]["kp_max"] = kp_max
        _query["parameters"]["segment"] = segment
        return self.__query(_query)

    @logging_error_handler
    def get_tag_by_name(self, name:str)->Tag|None:
        r"""
        O(1) lookup by name. Bypasses the administrative request/response queue.
        """
        return self._cvt.get_tag_by_name(name)
    
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
        O(1) lookup by OPC UA namespace. Bypasses the administrative request/response queue.
        """
        return self._cvt.get_tag_by_node_namespace(node_namespace)
    
    @logging_error_handler
    def get_value(self, id:str)->str|float|int|bool:
        r"""
        O(1) value read. Bypasses the administrative request/response queue.
        """
        return self._cvt.get_value(id)
    
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
    def set_value_fast(self, id:str, value, timestamp:datetime, quality:float=1.0):
        r"""
        Hot-path write: dict lookup O(1) + per-tag lock. Does not use the
        administrative request/response queue.
        """
        if timestamp is None:
            raise ValueError("set_value requires a timestamp from the producer")
        return self._cvt.set_value(id=id, value=value, timestamp=timestamp, quality=quality)

    @logging_error_handler
    def set_value(self, id:str, value, timestamp:datetime, quality:float=1.0):
        r"""
        Tag value write. Acquisition uses the fast path; CRUD stays on __query.
        """
        return self.set_value_fast(id, value, timestamp)
    
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
        O(1) name check. Bypasses the administrative request/response queue.
        """
        return self._cvt.is_tag_defined(name)

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
