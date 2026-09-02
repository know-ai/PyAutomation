import math
import secrets, logging, threading, time
from datetime import datetime
from ..signal_conditioning.quality import (
    BAD,
    GOOD,
    is_good_quality,
    is_good_sample,
    normalize_sample_quality,
    publication_quality_label,
)
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

DATETIME_FORMAT = "%m/%d/%Y, %H:%M:%S.%f"
_scope_audit_lock = threading.Lock()
_scope_audit_last = {}
_scope_audit_active = threading.local()


def _node_scope():
    """Local import keeps Tag independent while node_scope is being introduced."""
    try:
        from ..node_scope import get_node_scope

        return get_node_scope()
    except (ImportError, AttributeError):
        return None


def _scope_owns_tag(tag) -> bool:
    scope = _node_scope()
    if scope is None or not getattr(scope, "enabled", False):
        return True
    if not getattr(scope, "is_valid", False):
        return False
    try:
        return bool(scope.owns_tag(tag))
    except Exception:
        return False


def _audit_foreign_tag(tag) -> None:
    """Rate-limited, recursion-safe audit for a corrupt cross-edge update."""
    logger = logging.getLogger("pyautomation")
    tag_name = getattr(tag, "name", "") or "-"
    owner = getattr(tag, "owner_node", None)
    area = getattr(tag, "area", None)
    logger.error(
        "Rejected foreign tag sample tag=%s area=%s owner_node=%s",
        tag_name,
        area,
        owner,
    )
    if getattr(_scope_audit_active, "value", False):
        return
    now = time.monotonic()
    with _scope_audit_lock:
        if now - _scope_audit_last.get(tag_name, 0.0) < 60.0:
            return
        _scope_audit_last[tag_name] = now
    try:
        _scope_audit_active.value = True
        from ..utils.system_event_audit import persist_system_event

        persist_system_event(
            message="Foreign tag sample rejected",
            description=f"tag={tag_name} area={area or '-'} owner_node={owner or '-'}",
            classification="Security",
            priority=5,
            criticity=5,
        )
    except Exception:
        logger.debug("Foreign tag audit event skipped", exc_info=True)
    finally:
        _scope_audit_active.value = False

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
            area:str=None,
            owner_node:str=None
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
        self.quality = GOOD
        self.stale = False
        self.stale_timestamp = None
        self.opc_status_code = None
        self.quality_substatus = None
        self._bad_samples_dropped = 0
        self._last_quality = GOOD
        self.filter_enabled = filter_enabled
        self.filter_wavelet = filter_wavelet
        self.filter_level = filter_level
        self.filter_threshold_factor = filter_threshold_factor
        self.filter_persist = filter_persist
        self.outlier_detection = outlier_detection
        self.out_of_range_detection = out_of_range_detection
        self.frozen_data_detection = frozen_data_detection
        self.manufacturer = manufacturer
        self.segment = segment
        self.area = area
        self.owner_node = owner_node
        self.kp = kp
        self._observers = set()
        self._lock = threading.RLock()

    def set_name(self, name:str):
        r"""
        Sets the name of the tag.

        **Parameters:**

        * **name** (str): New tag name.
        """
        self.name = name

    @logging_error_handler
    def set_value(
        self,
        value: float | str | int | bool,
        timestamp: datetime = None,
        quality: float = GOOD,
        opc_code: int | None = None,
        substatus: str | None = None,
        *,
        notify_observers: bool = True,
    ):
        r"""
        Updates the value of the tag.

        This method handles:
        * Deadband filtering (only updates if change > dead_band).
        * Hold-last-good on Bad / NaN / Inf (quality and stale updated; PV frozen).
        * Updating internal value and timestamp buffers.
        * Notifying attached observers (unless ``notify_observers=False`` so
          CVT can emit ``on.tag`` to the HMI before SAF / machine observers).

        **Parameters:**

        * **value** (float|str|int|bool): New value.
        * **timestamp** (datetime, optional): Time of the value change. Defaults to now.
        * **quality** (float, optional): OPC-style quality (1.0=GOOD, 0.5=UNCERTAIN, 0= BAD).
        * **notify_observers** (bool): When False, caller must invoke ``notify()``.
        """
        q = normalize_sample_quality(value, quality)
        self._last_quality = q
        if opc_code is not None:
            self.opc_status_code = opc_code
        if substatus is not None:
            self.quality_substatus = substatus
        elif q >= 0.99:
            self.quality_substatus = None
        if isinstance(value, bool):
            bad_sample = not is_good_quality(q)
        elif isinstance(value, (int, float)):
            bad_sample = not is_good_sample(value, q)
        else:
            bad_sample = not is_good_quality(q)

        if not timestamp:
            timestamp = datetime.now()

        previous_degraded = bool(self.stale) or float(self.quality or GOOD) < 0.25

        if bad_sample:
            self._bad_samples_dropped += 1
            with self._lock:
                previous_quality = self.quality
                previous_stale = bool(self.stale)
                self.quality = q
                self.stale = True
                if self.stale_timestamp is None:
                    self.stale_timestamp = timestamp
                quality_changed = previous_quality != q or not previous_stale
            if quality_changed:
                held = None
                try:
                    held = self.value.value
                except Exception:
                    held = value
                self._ingest_wavelet_sample(held, timestamp, quality=q)
                if notify_observers:
                    self.notify()
                self._notify_quality_engine(previous_degraded, True)
                return True
            return False

        quality_refresh = False
        with self._lock:
            if self.dead_band and isinstance(value, (int, float)):
                try:
                    current_value = self.value.value
                    if abs(value - current_value) < self.dead_band:
                        if self.stale or self.quality != q:
                            self.quality = q
                            self.stale = False
                            self.stale_timestamp = None
                            self.timestamp = timestamp
                            quality_refresh = True
                        else:
                            return False
                except Exception as e:
                    logging.error(f"Error in deadband logic: {e}")

            if not quality_refresh:
                self.value.set_value(value=value, unit=self.display_unit)
                self.timestamp = timestamp
                self.quality = q
                self.stale = False
                self.stale_timestamp = None
                self.values(self.get_value())
                self.timestamps(timestamp.strftime(DATETIME_FORMAT))

        if not quality_refresh:
            self._ingest_wavelet_sample(value, timestamp, quality=q)
        if notify_observers:
            self.notify()
        self._notify_quality_engine(previous_degraded, False)
        return True

    def _notify_quality_engine(self, previous_degraded: bool, degraded: bool) -> None:
        if bool(previous_degraded) == bool(degraded):
            return
        try:
            from ..alarms.quality_gate import notify_quality_transition

            notify_quality_transition(self, degraded=bool(degraded))
        except Exception:
            logging.getLogger("pyautomation").debug(
                "Quality engine notify skipped tag=%s",
                getattr(self, "name", ""),
                exc_info=True,
            )

    def get_stale_age_ms(self, now: datetime | None = None) -> int | None:
        """Milliseconds since the PV became stale, or None when live."""
        if not self.stale or self.stale_timestamp is None:
            return None
        try:
            from datetime import timezone

            from ..timebase import ensure_utc

            stamp = ensure_utc(self.stale_timestamp)
            if now is None:
                ref = datetime.now(timezone.utc)
            else:
                ref = ensure_utc(now)
            age_ms = int((ref - stamp).total_seconds() * 1000)
            return max(0, age_ms)
        except Exception:
            return None

    def _ingest_wavelet_sample(self, value, timestamp: datetime, quality: float = GOOD) -> None:
        from ..signal_conditioning.filtered_tags import is_filtered_derivative_name, tag_filter_enabled

        if not tag_filter_enabled(self) or is_filtered_derivative_name(self.name):
            return
        if not isinstance(value, (int, float)):
            return
        try:
            from ..workers.wavelet_worker import get_wavelet_worker

            worker = get_wavelet_worker()
            if worker is None:
                return
            default_interval = 1.0
            scan_time = getattr(self, "scan_time", None)
            if scan_time:
                default_interval = max(0.05, float(scan_time) / 1000.0)
            worker.ensure_ingest(
                self.name,
                float(value),
                timestamp,
                quality=quality,
                default_interval=default_interval,
            )
        except Exception:
            logging.getLogger("pyautomation").debug(
                "Wavelet ingest skipped tag=%s", getattr(self, "name", ""), exc_info=True
            )

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
    
    def set_kp(self, kp:float|None):
        r"""
        Sets the KP (Kilometer Post) associated with the tag.

        **Parameters:**

        * **kp** (float|None): Kilometer post value.
        """
        self.kp = kp

    def get_kp(self)->float|None:
        r"""
        Gets the KP (Kilometer Post) associated with the tag.

        **Returns:**

        * **float|None**: Kilometer post value.
        """
        return self.kp

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
        if observer is None:
            return
        observer._subject = None
        release = getattr(observer, "release", None)
        if callable(release):
            release()
        self._observers.discard(observer)

    def detach_all_observers(self):
        r"""
        Detaches every observer. ``delete_tag`` owns this cleanup so no
        TagObserver / MachineObserver / alarm observer keeps the Tag alive.
        """
        for observer in list(self._observers):
            self.detach(observer)

    def detach_machine(self, machine) -> bool:
        r"""
        Detaches the ``MachineObserver`` bound to ``machine``, if any.

        **Returns:**

        * **bool**: True when an observer was removed.
        """
        for observer in list(self._observers):
            if isinstance(observer, MachineObserver) and observer.machine is machine:
                self.detach(observer)
                return True
        return False

    def notify(self):
        r"""
        Notifies all attached observers of a change.

        Observers (state machines, SAF, alarms) require an acquisition timestamp.
        A brand-new tag can receive a BAD/stale sample before any good PV (lab
        node, OPC down). Fan-out without a datetime would raise in
        ``StateMachineCore.notify`` / LDS ``notify``.
        """
        if self.get_timestamp() is None:
            return
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
            "area": self.area,
            "owner_node": self.owner_node,
            "kp": self.get_kp(),
            "manufacturer": self.manufacturer,
            "quality": self.quality,
            "quality_label": publication_quality_label(self.quality),
            "quality_substatus": getattr(self, "quality_substatus", None),
            "opc_status_code": getattr(self, "opc_status_code", None),
            "stale": bool(self.stale),
            "stale_timestamp": (
                self.stale_timestamp.strftime(DATETIME_FORMAT) if self.stale_timestamp else None
            ),
            "stale_age_ms": self.get_stale_age_ms(),
            "bad_samples_dropped": self._bad_samples_dropped,
            "filter_enabled": self.filter_enabled,
            "filter_wavelet": self.filter_wavelet,
            "filter_level": self.filter_level,
            "filter_threshold_factor": self.filter_threshold_factor,
            "filter_persist": self.filter_persist,
            "out_of_range_detection": self.out_of_range_detection,
            "frozen_data_detection": self.frozen_data_detection,
            "outlier_detection": self.outlier_detection
        }

    def serialize_socket(self):
        from ..timebase import iso_millis

        quality = getattr(self, "quality", GOOD)
        payload = {
            "name": self.name,
            "value": self.get_value(),
            "timestamp": iso_millis(self.get_timestamp()),
            "unit": self.get_display_unit(),
            "quality": quality,
            "quality_label": publication_quality_label(quality),
            "quality_substatus": getattr(self, "quality_substatus", None),
            "stale": bool(getattr(self, "stale", False)),
            "stale_age_ms": self.get_stale_age_ms(),
        }
        threshold = self._resolve_alarm_threshold_for_socket()
        if threshold is not None:
            payload["threshold"] = threshold
        return payload

    def _resolve_alarm_threshold_for_socket(self):
        """Umbral de máquina asociada al tag (PPA/NPW/LDS). None si no aplica o es 0."""
        try:
            from .. import PyAutomation

            tag_name = self.name
            if not tag_name:
                return None
            app = PyAutomation()
            for machine, _, _ in app.get_machines():
                thr = _machine_threshold_value(machine)
                if thr is None or thr == 0:
                    continue
                try:
                    subscribed = machine.get_subscribed_tags()
                except Exception:
                    subscribed = {}
                if tag_name in subscribed:
                    return thr
                machine_name = getattr(getattr(machine, "name", None), "value", None)
                if not machine_name:
                    machine_name = str(getattr(machine, "name", "") or "")
                if machine_name and (
                    tag_name == machine_name
                    or tag_name.startswith(f"{machine_name}.")
                    or tag_name.endswith(f".{machine_name}")
                    or f".{machine_name}." in tag_name
                ):
                    return thr
        except Exception:
            return None
        return None


def _machine_threshold_value(machine) -> float | None:
    """Extract the active threshold from a state machine (optional getter)."""
    getter = getattr(machine, "get_active_detection_threshold", None)
    if callable(getter):
        try:
            value = getter()
            if value is not None:
                numeric = float(value)
                if numeric != 0:
                    return numeric
        except Exception:
            pass
    threshold = getattr(machine, "threshold", None)
    if threshold is None:
        return None
    raw = getattr(threshold, "value", threshold)
    inner = getattr(raw, "value", raw)
    try:
        numeric = float(inner)
    except (TypeError, ValueError):
        return None
    return numeric if numeric != 0 else None


def _skip_historian_tag(tag) -> bool:
    """Diagnostic BOOL tags and samples without acquisition time are not TagValue history."""
    if getattr(tag, "timestamp", None) is None:
        return True
    name = (getattr(tag, "name", None) or "").upper()
    markers = (
        ".SYS.QUALITY.",
        "SYS.QUALITY.",
        ".SYS.OPCUA.",
        "SYS.OPCUA.",
        ".SYS.DB.",
        "SYS.DB.",
    )
    return any(name.startswith(marker) or marker in name for marker in markers)


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
        if self._subject is None:
            return
        if not _scope_owns_tag(self._subject):
            _audit_foreign_tag(self._subject)
            return
        if _skip_historian_tag(self._subject):
            return
        try:
            result = dict()
            result["tag"] = self._subject.name
            result["value"] = self._subject.value.convert(self._subject.get_display_unit())
            result["timestamp"] = self._subject.timestamp
            from ..persistence import get_persistence_gateway
            from ..persistence.records import PersistableRecord

            record = PersistableRecord.tag_sample(
                tag=result["tag"],
                value=result["value"],
                timestamp=result["timestamp"],
                area=getattr(self._subject, "area", None),
                owner_node=getattr(self._subject, "owner_node", None),
                quality=getattr(self._subject, "quality", None),
            )
            import logging
            logging.getLogger("pyautomation").debug(
                "SAF TagObserver payload=%s", dict(record.payload())
            )
            get_persistence_gateway().enqueue(record)
        except Exception:
            import logging

            logging.getLogger("pyautomation").critical(
                "SAF journal rejected a tag sample; history backpressure",
                exc_info=True,
            )


class MachineObserver(Observer):
    """
    Observer implementation that notifies a State Machine directly.
    """
    def __init__(self, machine):

        super(MachineObserver, self).__init__()
        self.machine = machine

    def release(self):
        r"""
        Drops the machine root so detach does not keep the SM alive.
        """
        self.machine = None

    def update(self):

        """
        Calls the `notify` method of the attached state machine with the new tag value.
        """
        if self._subject is None or self.machine is None:
            return
        timestamp = getattr(self._subject, "timestamp", None)
        if timestamp is None:
            return
        value = getattr(self._subject, "value", None)
        if value is None:
            return
        self.machine.notify(
            tag=self._subject.name,
            value=value,
            timestamp=timestamp,
        )
