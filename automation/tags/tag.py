from ..utils import Observer
import secrets


class Tag:

    def __init__(
            self,
            name:str,
            unit:str,
            data_type:str,
            display_name:str=None,
            description:str="",
            opcua_address:str=None,
            node_namespace:str=None,
            scan_time:int=None,
            dead_band:float=None,
            id:str=None
    ):
        self.id = secrets.token_hex(4)
        if id:
            self.id = id
        self.name = name
        self.value = None
        self.data_type = data_type
        self.description = description
        self.display_name = name
        if display_name:
            self.display_name = display_name
        self.unit=unit
        self.opcua_address = opcua_address
        self.node_namespace = node_namespace
        self.scan_time = scan_time
        self.dead_band = dead_band
        self.variable = None
        self._observers = set()

    def set_value(self, value:float|str|int|bool):

        self.value = value
        self.notify()

    def get_value(self):

        return self.value

    def set_display_name(self, value:str):
        r"""
        Documentation here
        """

        self.display_name = value

    def set_variable(self, value:str):
        r"""
        Documentation here
        """

        self.variable = value

    def set_opcua_address(self, opcua_address:str):

        self.opcua_address = opcua_address

    def set_node_namespace(self, node_namespace:str):

        self.node_namespace = node_namespace

    def get_scan_time(self):

        return self.scan_time
    
    def get_dead_band(self):

        return self.dead_band

    def get_data_type(self):
        
        return self.data_type

    def get_unit(self):

        return self.unit

    def get_description(self):

        return self.description
    
    def get_display_name(self)->str:
        r"""
        Documentation here
        """

        return self.display_name
    
    def get_variable(self)->str:
        r"""
        Documentation here
        """

        return self.variable
    
    def get_id(self)->str:
        r"""
        Documentation here
        """

        return self.id
    
    def get_name(self)->str:
        r"""
        Documentation here
        """

        return self.name

    def get_opcua_address(self):
        
        return self.opcua_address

    def get_node_namespace(self):

        return self.node_namespace
    
    def attach(self, observer:Observer):

        observer._subject = self
        self._observers.add(observer)

    def detach(self, observer:Observer):

        observer._subject = None
        self._observers.discard(observer)

    def notify(self):

        for observer in self._observers:

            observer.update()
        
    def parser(self):
        r"""
        Documentation here
        """
        return (
            self.name,
            self.get_unit(),
            self.get_data_type(),
            self.get_description(),
            self.get_display_name(),
            self.get_opcua_address(),
            self.get_node_namespace(),
            self.get_scan_time(),
            self.get_dead_band()
        )
    
    def update(self, **kwargs):
        r"""
        Documentation here
        """
        for key, value in kwargs.items():

            if hasattr(self, key):

                setattr(self, key, value)

    def serialize(self):

        return {
            "id": self.get_id(),
            "value": self.get_value(),
            "name": self.name,
            "unit": self.get_unit(),
            "data_type": self.get_data_type(),
            "variable": self.get_variable(),
            "description": self.get_description(),
            "display_name": self.get_display_name(),
            "opcua_address": self.get_opcua_address(),
            "node_namespace": self.get_node_namespace(),
            "scan_time": self.get_scan_time(),
            "dead_band": self.get_dead_band()
        }


class TagObserver(Observer):
    """
    Implement the Observer updating interface to keep its state
    consistent with the subject's.
    Store state that should stay consistent with the subject's.
    """
    def __init__(self, tag_queue):

        super(TagObserver, self).__init__()
        self._tag_queue = tag_queue

    def update(self):

        """
        This methods inserts the changing Tag into a 
        Producer-Consumer Queue Design Pattern
        """
        
        result = dict()

        result["tag"] = self._subject.name
        result["value"] = self._subject.value
        self._tag_queue.put(result)