import secrets, logging
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
    r"""
    Represents a process variable (Tag) in the automation system.

    A Tag holds the current value, timestamp, quality, and metadata of a variable.
    It supports unit conversion, deadband filtering, and notifying observers upon value changes.
    """

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
            gaussian_filter_threshold:float=1.0,
            gaussian_filter_r_value:float=0.0,
            outlier_detection:bool=False,
            out_of_range_detection:bool=False,
            frozen_data_detection:bool=False,
            manufacturer:str="",
            segment:str="",
            id:str=None
    ):
        r"""
        Initializes a new Tag instance.

        **Parameters:**

        * **name** (str): Unique name of the tag.
        * **unit** (str): Base unit of measurement.
        * **variable** (str): Physical variable type (e.g., 'Temperature', 'Pressure').
        * **data_type** (str): Data type of the value ('float', 'int', 'bool', 'str').
        * **display_name** (str, optional): Human-readable name for UI.
        * **display_unit** (str, optional): Unit to display in UI.
        * **description** (str, optional): Description of the tag.
        * **opcua_address** (str, optional): OPC UA Server URL.
        * **node_namespace** (str, optional): OPC UA Node ID.
        * **scan_time** (int, optional): Polling interval in milliseconds.
        * **dead_band** (float, optional): Minimum change required to update value.
        * **timestamp** (datetime, optional): Initial timestamp.
        * **process_filter** (bool, optional): Enable process value filtering.
        * **gaussian_filter** (bool, optional): Enable Gaussian (Kalman) filtering.
        * **gaussian_filter_threshold** (float, optional): Threshold for filter adaptation.
        * **gaussian_filter_r_value** (float, optional): R value for Kalman filter.
        * **outlier_detection** (bool, optional): Enable outlier detection.
        * **out_of_range_detection** (bool, optional): Enable out-of-range detection.
        * **frozen_data_detection** (bool, optional): Enable frozen data detection.
        * **manufacturer** (str, optional): Manufacturer metadata.
        * **segment** (str, optional): Segment metadata.
        * **id** (str, optional): Unique ID. If not provided, one is generated.
        """
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
        # opcua_client_name almacena el nombre del cliente OPC UA
        # Si opcua_address es una URL, se intentará resolver el nombre del cliente
        # Si opcua_address es un nombre de cliente, se usará directamente
        self.opcua_client_name = None
        self._opcua_address = opcua_address  # Mantener para compatibilidad temporal
        # Resolver opcua_client_name si se proporciona opcua_address
        if opcua_address:
            # Si opcua_address parece ser una URL (contiene "opc.tcp://"), intentar resolver el cliente
            if "opc.tcp://" in opcua_address:
                # Se resolverá dinámicamente cuando se necesite
                self._opcua_address = opcua_address
            else:
                # Si no es una URL, asumir que es un nombre de cliente
                self.opcua_client_name = opcua_address
                self._opcua_address = None
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
        Sets the name of the tag.

        **Parameters:**

        * **name** (str): New tag name.
        """
        self.name = name

    @logging_error_handler
    def set_value(self, value:float|str|int|bool, timestamp:datetime=None):
        r"""
        Updates the value of the tag.

        This method handles:
        * Deadband filtering (only updates if change > dead_band).
        * Updating internal value and timestamp buffers.
        * Notifying attached observers.

        **Parameters:**

        * **value** (float|str|int|bool): New value.
        * **timestamp** (datetime, optional): Time of the value change. Defaults to now.
        """
        if self.dead_band and isinstance(value, (int, float)):
            try:
                current_value = self.value.value
                if abs(value - current_value) < self.dead_band:
                    
                    return
            except Exception as e:
                logging.error(f"Error in deadband logic: {e}")

        if not timestamp:
            timestamp = datetime.now()
        self.value.set_value(value=value, unit=self.display_unit)
        self.timestamp = timestamp
        self.values(self.get_value())
        self.timestamps(timestamp.strftime(DATETIME_FORMAT))
        self.notify()

    def set_display_name(self, name:str):
        r"""
        Sets the display name of the tag.

        **Parameters:**

        * **name** (str): New display name.
        """

        self.display_name = name

    def set_data_type(self, data_type:str):
        r"""
        Sets the data type of the tag.

        **Parameters:**

        * **data_type** (str): 'float', 'int', 'bool', or 'str'.
        """
        self.data_type = data_type

    def set_variable(self, variable:str):
        r"""
        Sets the physical variable type and initializes the corresponding value object.

        **Parameters:**

        * **variable** (str): Variable type (e.g., 'Temperature').
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
        Sets the OPC UA server address associated with this tag.
        
        Si opcua_address es una URL (contiene "opc.tcp://"), se almacena en _opcua_address.
        Si opcua_address es un nombre de cliente, se guarda en opcua_client_name y se intenta
        resolver la URL desde el cliente (requiere acceso al manager).

        **Parameters:**

        * **opcua_address** (str): Server URL o nombre del cliente OPC UA.
        """
        if opcua_address:
            if "opc.tcp://" in opcua_address:
                # Es una URL, almacenarla directamente
                self._opcua_address = opcua_address
                # No limpiar opcua_client_name aquí, puede estar establecido por separado
            else:
                # No es una URL, asumir que es un nombre de cliente
                # La URL se resolverá cuando se establezca el nombre del cliente
                self.opcua_client_name = opcua_address
                # No limpiar _opcua_address aquí, mantener la URL actual si existe
        else:
            self._opcua_address = None
            self.opcua_client_name = None
    
    def set_opcua_client_name(self, client_name:str, opcua_address:str=None):
        r"""
        Sets the OPC UA client name associated with this tag.

        **Parameters:**

        * **client_name** (str): Nombre del cliente OPC UA.
        * **opcua_address** (str, optional): URL del cliente OPC UA. Si se proporciona, se almacena.
        """
        self.opcua_client_name = client_name
        # Si se proporciona la URL, almacenarla para mantener compatibilidad con suscripciones
        if opcua_address:
            self._opcua_address = opcua_address
        # Si no se proporciona URL pero hay nombre, mantener _opcua_address si ya existe
        # (se actualizará cuando se resuelva desde el manager)
    
    def get_opcua_client_name(self):
        r"""
        Gets the OPC UA client name associated with this tag.

        **Returns:**

        * **str**: Nombre del cliente OPC UA o None.
        """
        return self.opcua_client_name

    def set_unit(self, unit:str):
        r"""
        Sets the base unit of the tag.

        **Parameters:**

        * **unit** (str): Unit symbol.
        """
        self.unit = unit

    def set_display_unit(self, unit:str): 
        r"""
        Sets the display unit of the tag (for UI).

        **Parameters:**

        * **unit** (str): Unit symbol.
        """
        self.display_unit = unit

    def set_node_namespace(self, node_namespace:str):
        r"""
        Sets the OPC UA node namespace/ID.

        **Parameters:**

        * **node_namespace** (str): Node ID string.
        """
        self.node_namespace = node_namespace

    def get_value(self):
        r"""
        Gets the current value of the tag, converted to the display unit.

        **Returns:**

        * Value rounded to 3 decimal places.
        """            
        return round(self.value.convert(to_unit=self.display_unit), 3)
    
    def set_description(self, description:str):
        r"""
        Sets the description of the tag.

        **Parameters:**

        * **description** (str): Description text.
        """
        self.description = description
    
    def set_scan_time(self, scan_time:int):
        r"""
        Sets the scan time (polling interval).

        **Parameters:**

        * **scan_time** (int): Time in milliseconds.
        """
        self.scan_time = scan_time

    def set_dead_band(self, dead_band:float):
        r"""
        Sets the deadband value.

        **Parameters:**

        * **dead_band** (float): Minimum change threshold.
        """
        self.dead_band = dead_band

    def get_timestamp(self):
        r"""
        Gets the timestamp of the last value update.

        **Returns:**

        * **datetime**: Timestamp.
        """
        return self.timestamp

    def get_scan_time(self):
        r"""
        Gets the configured scan time.

        **Returns:**

        * **int**: Scan time in milliseconds.
        """
        return self.scan_time
    
    def get_dead_band(self):
        r"""
        Gets the configured deadband.

        **Returns:**

        * **float**: Deadband value.
        """
        return self.dead_band

    def get_data_type(self):
        r"""
        Gets the data type of the tag.

        **Returns:**

        * **str**: Data type string.
        """
        return self.data_type

    def get_unit(self):
        r"""
        Gets the base unit of the tag.

        **Returns:**

        * **str**: Unit symbol.
        """
        return self.unit
    
    def get_display_unit(self):
        r"""
        Gets the display unit of the tag.

        **Returns:**

        * **str**: Display unit symbol.
        """
        return self.display_unit

    def get_description(self):
        r"""
        Gets the description of the tag.

        **Returns:**

        * **str**: Description text.
        """
        return self.description
    
    def get_display_name(self)->str:
        r"""
        Gets the display name of the tag.

        **Returns:**

        * **str**: Display name.
        """

        return self.display_name
    
    def get_variable(self)->str:
        r"""
        Gets the physical variable type.

        **Returns:**

        * **str**: Variable type (e.g., 'Temperature').
        """

        return self.variable
    
    def get_id(self)->str:
        r"""
        Gets the unique ID of the tag.

        **Returns:**

        * **str**: Unique ID.
        """

        return self.id
    
    def get_name(self)->str:
        r"""
        Gets the unique name of the tag.

        **Returns:**

        * **str**: Tag name.
        """

        return self.name

    def get_opcua_address(self):
        r"""
        Gets the OPC UA server address.
        
        Retorna la URL almacenada en _opcua_address. Esta URL debe mantenerse
        actualizada cuando cambia la configuración del cliente OPC UA.

        **Returns:**

        * **str**: OPC UA address (URL) o None.
        """
        # Retornar la URL almacenada (debe estar actualizada cuando hay opcua_client_name)
        return self._opcua_address
    
    @property
    def opcua_address(self):
        r"""
        Property para acceder a opcua_address de manera compatible.
        
        **Returns:**
        
        * **str**: OPC UA address (URL) o None.
        """
        return self.get_opcua_address()

    def get_node_namespace(self):
        r"""
        Gets the OPC UA node namespace.

        **Returns:**

        * **str**: Node Namespace.
        """
        return self.node_namespace
    
    def attach(self, observer:Observer):
        r"""
        Attaches an observer to this tag.

        **Parameters:**

        * **observer** (Observer): The observer instance to attach.
        """
        observer._subject = self
        self._observers.add(observer)

    def detach(self, observer:Observer):
        r"""
        Detaches an observer from this tag.

        **Parameters:**

        * **observer** (Observer): The observer instance to detach.
        """
        observer._subject = None
        self._observers.discard(observer)

    def notify(self):
        r"""
        Notifies all attached observers of a change.
        """
        for observer in self._observers:
            
            observer.update()

    def serialize(self):
        r"""
        Serializes the tag object to a dictionary.

        **Returns:**

        * **dict**: Dictionary representation of the tag.
        """

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
            "opcua_client_name": self.get_opcua_client_name(),
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
    Observer implementation that pushes tag updates to a queue.
    
    Useful for asynchronous processing of tag changes.
    """
    def __init__(self, tag_queue):

        super(TagObserver, self).__init__()
        self._tag_queue = tag_queue

    def update(self):

        """
        Puts the updated tag data (name, value, timestamp) into the queue.
        """
        result = dict()
        result["tag"] = self._subject.name
        result["value"] = self._subject.value.convert(self._subject.get_display_unit())
        result["timestamp"] = self._subject.timestamp
        self._tag_queue.put(result, block=False)


class MachineObserver(Observer):
    """
    Observer implementation that notifies a State Machine directly.
    """
    def __init__(self, machine):

        super(MachineObserver, self).__init__()
        self.machine = machine

    def update(self):

        """
        Calls the `notify` method of the attached state machine with the new tag value.
        """
        self.machine.notify(tag=self._subject.name, value=self._subject.value, timestamp=self._subject.timestamp)
