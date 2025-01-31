import secrets
from datetime import datetime
from ..utils import Observer
from ..utils.decorators import logging_error_handler
from ..buffer import Buffer
from ..variables import (
    Temperature,
    Length,
    Current,
    Time,
    Pressure,
    Mass,
    Force,
    Power,
    VolumetricFlow,
    MassFlow,
    Density,
    Percentage,
    Adimentional,
    Volume
)
from .filter import GaussianFilter

DATETIME_FORMAT = "%m/%d/%Y, %H:%M:%S.%f"

class Tag:

    def __init__(
            self,
            name:str,
            unit:str,
            variable:str,
            data_type:str,
            display_name:str=None,
            display_unit:str=None,
            description:str="",
            opcua_address:str=None,
            node_namespace:str=None,
            scan_time:int=None,
            dead_band:float=None,
            timestamp:datetime=None,
            process_filter:bool=False,
            gaussian_filter:bool=False,
            outlier_detection:bool=False,
            out_of_range_detection:bool=False,
            frozen_data_detection:bool=False,
            manufacturer:str="",
            segment:str="",
            id:str=None,
            gaussian_filter_threshold:float=100,
            gaussian_filter_r_value:float=0.5
    ):
        self.id = secrets.token_hex(4)
        if id:
            self.id = id
        self.name = name
        self.data_type = data_type
        self.description = description
        self.variable = variable
        self.display_name = name
        if display_name:
            self.display_name = display_name
        self.display_unit = unit
        if display_unit:
            self.display_unit = display_unit
        self.unit=unit
        if variable.lower()=="temperature":
            self.value = Temperature(value=0.0, unit=self.unit)
        elif variable.lower()=="length":
            self.value = Length(value=0.0, unit=self.unit)
        elif variable.lower()=="time":
            self.value = Time(value=0.0, unit=self.unit)
        elif variable.lower()=="pressure":
            self.value = Pressure(value=0.0, unit=self.unit)
        elif variable.lower()=="mass":
            self.value = Mass(value=0.0, unit=self.unit)
        elif variable.lower()=="force":
            self.value = Force(value=0.0, unit=self.unit)
        elif variable.lower()=="power":
            self.value = Power(value=0.0, unit=self.unit)
        elif variable.lower()=="current":
            self.value = Current(value=0.0, unit=self.unit)
        elif variable.lower()=="volumetricflow":
            self.value = VolumetricFlow(value=0.0, unit=self.unit)
        elif variable.lower()=="massflow":
            self.value = MassFlow(value=0.0, unit=self.unit)
        elif variable.lower()=="density":
            self.value = Density(value=0.0, unit=self.unit)
        elif variable.lower()=="percentage":
            self.value = Percentage(value=0.0, unit=self.unit)
        elif variable.lower()=="adimentional":
            self.value = Adimentional(value=0.0, unit=self.unit)
        elif variable.lower()=="volume":
            self.value = Volume(value=0.0, unit=self.unit)

        self.values = Buffer()
        self.timestamps = Buffer()
        self.opcua_address = opcua_address
        self.node_namespace = node_namespace
        self.scan_time = scan_time
        self.dead_band = dead_band
        self.timestamp = timestamp
        self.process_filter = process_filter
        self.gaussian_filter = gaussian_filter
        self.gaussian_filter_threshold = gaussian_filter_threshold
        self.gaussian_filter_r_value = gaussian_filter_r_value
        self.outlier_detection = outlier_detection
        self.out_of_range_detection = out_of_range_detection
        self.frozen_data_detection = frozen_data_detection
        self.manufacturer = manufacturer
        self.segment = segment
        self.filter = GaussianFilter()
        self._observers = set()

    def set_name(self, name:str):
        r"""
        Documentation here
        """
        self.name = name

    @logging_error_handler
    def set_value(self, value:float|str|int|bool, timestamp:datetime=None):
        r"""
        Documentation here
        """
        if not timestamp:
            timestamp = datetime.now()
        self.value.set_value(value=value, unit=self.display_unit)
        self.timestamp = timestamp
        self.values(self.get_value())
        self.timestamps(timestamp.strftime(DATETIME_FORMAT))
        self.notify()

    def set_display_name(self, name:str):
        r"""
        Documentation here
        """

        self.display_name = name

    def set_data_type(self, data_type:str):
        r"""
        Documentation here
        """
        self.data_type = data_type

    def set_variable(self, variable:str):
        r"""
        Documentation here
        """

        self.variable = variable
        if variable.lower()=="temperature":
            self.value = Temperature(value=0.0, unit=self.unit)
        elif variable.lower()=="length":
            self.value = Length(value=0.0, unit=self.unit)
        elif variable.lower()=="time":
            self.value = Time(value=0.0, unit=self.unit)
        elif variable.lower()=="pressure":
            self.value = Pressure(value=0.0, unit=self.unit)
        elif variable.lower()=="mass":
            self.value = Mass(value=0.0, unit=self.unit)
        elif variable.lower()=="force":
            self.value = Force(value=0.0, unit=self.unit)
        elif variable.lower()=="power":
            self.value = Power(value=0.0, unit=self.unit)
        elif variable.lower()=="current":
            self.value = Current(value=0.0, unit=self.unit)
        elif variable.lower()=="volumetricflow":
            self.value = VolumetricFlow(value=0.0, unit=self.unit)
        elif variable.lower()=="massflow":
            self.value = MassFlow(value=0.0, unit=self.unit)
        elif variable.lower()=="density":
            self.value = Density(value=0.0, unit=self.unit)
        elif variable.lower()=="percentage":
            self.value = Percentage(value=0.0, unit=self.unit)
        elif variable.lower()=="adimentional":
            self.value = Adimentional(value=0.0, unit=self.unit)
        elif variable.lower()=="volume":
            self.value = Volume(value=0.0, unit=self.unit)

    def set_opcua_address(self, opcua_address:str):
        r"""
        Documentation here
        """
        self.opcua_address = opcua_address

    def set_unit(self, unit:str):
        r"""
        Documentation here
        """
        self.unit = unit

    def set_display_unit(self, unit:str): 
        r"""
        Documentation here
        """
        self.display_unit = unit

    def set_node_namespace(self, node_namespace:str):
        r"""
        Documentation here
        """
        self.node_namespace = node_namespace

    def get_value(self):
        r"""
        Documentation here
        """            
        return round(self.value.convert(to_unit=self.display_unit), 3)
    
    def set_description(self, description:str):
        r"""
        Documentation here
        """
        self.description = description
    
    def set_scan_time(self, scan_time:int):
        r"""
        Documentation here
        """
        self.scan_time = scan_time

    def set_dead_band(self, dead_band:float):
        r"""
        Documentation here
        """
        self.dead_band = dead_band

    def get_timestamp(self):
        r"""
        Documentation here
        """
        return self.timestamp

    def get_scan_time(self):
        r"""
        Documentation here
        """
        return self.scan_time
    
    def get_dead_band(self):
        r"""
        Documentation here
        """
        return self.dead_band

    def get_data_type(self):
        r"""
        Documentation here
        """
        return self.data_type

    def get_unit(self):
        r"""
        Documentation here
        """
        return self.unit
    
    def get_display_unit(self):
        r"""
        Documentation here
        """
        return self.display_unit

    def get_description(self):
        r"""
        Documentation here
        """
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
        r"""
        Documentation here
        """
        return self.opcua_address

    def get_node_namespace(self):
        r"""
        Documentation here
        """
        return self.node_namespace
    
    def attach(self, observer:Observer):
        r"""
        Documentation here
        """
        observer._subject = self
        self._observers.add(observer)

    def detach(self, observer:Observer):
        r"""
        Documentation here
        """
        observer._subject = None
        self._observers.discard(observer)

    def notify(self):
        r"""
        Documentation here
        """
        for observer in self._observers:
            
            observer.update()

    def serialize(self):

        timestamp = self.get_timestamp()
        if timestamp:

            timestamp = timestamp.strftime(DATETIME_FORMAT)

        return {
            "id": self.get_id(),
            "value": self.get_value(),
            "timestamp": timestamp,
            "values": list(self.values),
            "timestamps": list(self.timestamps),
            "name": self.name,
            "unit": self.get_unit(),
            "display_unit": self.get_display_unit(),
            "data_type": self.get_data_type(),
            "variable": self.get_variable(),
            "description": self.get_description(),
            "display_name": self.get_display_name(),
            "opcua_address": self.get_opcua_address(),
            "node_namespace": self.get_node_namespace(),
            "scan_time": self.get_scan_time(),
            "dead_band": self.get_dead_band(),
            "segment": self.segment,
            "manufacturer": self.manufacturer,
            "process_filter": self.process_filter,
            "gaussian_filter": self.gaussian_filter,
            "out_of_range_detection": self.out_of_range_detection,
            "frozen_data_detection": self.frozen_data_detection,
            "outlier_detection": self.outlier_detection
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
        result["value"] = self._subject.value.convert(self._subject.get_display_unit())
        result["timestamp"] = self._subject.timestamp
        self._tag_queue.put(result, block=False)


class MachineObserver(Observer):
    """
    Implement the Observer updating interface to keep its state
    consistent with the subject's.
    Store state that should stay consistent with the subject's.
    """
    def __init__(self, machine):

        super(MachineObserver, self).__init__()
        self.machine = machine

    def update(self):

        """
        This methods inserts the changing Tag into a 
        Producer-Consumer Queue Design Pattern
        """
        self.machine.notify(tag=self._subject.name, value=self._subject.value, timestamp=self._subject.timestamp)
