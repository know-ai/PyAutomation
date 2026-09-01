import logging
import os

from flask import request
from flask_restx import Namespace, Resource, fields
from .... import PyAutomation
from ....extensions.api import api
from ....extensions import _api as Api
from ....models import StringType, FloatType, IntegerType
from ....variables import Percentage, compatible_field_variables, variable_for_unit
from ....domain_config import (
    audit_domain_config_change,
    domain_files_upload_payload,
    supports_domain_config,
    supports_domain_files,
    unknown_generic_attribute_keys,
)
from ....state_machine_timing import MachineConfigError, validate_temporal_config

logger = logging.getLogger(__name__)

ns = Namespace('Machines', description='State Machine Management Resources')
app = PyAutomation()


def _machine_scope_error(machine_name: str | None = None, machine=None):
    scope = app._refresh_node_scope()
    if scope.enabled and not scope.is_valid:
        return {"message": "Multi-edge node identity is not configured"}, 503
    target = machine
    if target is None and machine_name:
        target = app.machine_manager.get_machine(name=StringType(machine_name))
        if target is None:
            return None
    if target is not None and not app._machine_in_scope(target):
        return {"message": "Machine belongs to another edge node"}, 403
    return None


def _tag_opcua_mapped(tag) -> bool:
    if tag is None:
        return False
    address = tag.get_opcua_address() if hasattr(tag, "get_opcua_address") else getattr(tag, "opcua_address", None)
    node = tag.get_node_namespace() if hasattr(tag, "get_node_namespace") else getattr(tag, "node_namespace", None)
    return bool(address) and bool(node)


def _field_tag_info(tag, *, name: str | None = None) -> dict:
    tag_name = name or (getattr(tag, "name", None) if tag is not None else None) or ""
    variable = ""
    unit = ""
    client = ""
    if tag is not None:
        if hasattr(tag, "get_variable"):
            variable = tag.get_variable() or ""
        else:
            variable = getattr(tag, "variable", None) or ""
        if hasattr(tag, "get_unit"):
            unit = tag.get_unit() or ""
        else:
            unit = getattr(tag, "unit", None) or ""
        if hasattr(tag, "get_opcua_client_name"):
            client = tag.get_opcua_client_name() or ""
        else:
            client = getattr(tag, "opcua_client_name", None) or ""
    return {
        "name": tag_name,
        "variable": variable,
        "unit": unit,
        "opcua_mapped": _tag_opcua_mapped(tag),
        "opcua_client_name": client,
    }


def _subscription_type_error(process_type, field_tag, *, internal_tag_name: str, field_tag_name: str):
    internal_var = variable_for_unit(getattr(process_type, "unit", None))
    if hasattr(field_tag, "get_variable"):
        tag_var = field_tag.get_variable()
    else:
        tag_var = getattr(field_tag, "variable", None)
    if not internal_var or not tag_var:
        return None
    allowed = compatible_field_variables(internal_var)
    if tag_var in allowed:
        return None
    return (
        f"El tag de campo '{field_tag_name}' ({tag_var}) no es compatible "
        f"con '{internal_tag_name}' ({internal_var})."
    )


def _apply_temporal_update(machine, new_execution, new_sample, overrides, user, persist: bool):
    resolved_execution = new_execution if new_execution is not None else machine.get_interval()
    resolved_sample = new_sample if new_sample is not Ellipsis else machine.get_sample_interval()
    resolved_overrides = overrides if overrides is not None else (machine.sample_overrides or {})
    validate_temporal_config(
        machine,
        new_execution=resolved_execution,
        new_sample=resolved_sample,
        overrides=resolved_overrides,
    )
    if new_execution is not None:
        machine.machine_interval = FloatType(new_execution)
    if new_sample is not Ellipsis:
        machine._sample_interval = None if new_sample is None else float(new_sample)
    if overrides is not None:
        machine.sample_overrides = {
            name: float(value)
            for name, value in overrides.items()
            if value is not None
        }
    machine.ensure_sample_buffers()
    machine._reconfigure_temporal_schedulers()
    if persist:
        sample_set = new_sample is not Ellipsis
        app.machines_engine.put(
            name=StringType(machine.name.value),
            machine_interval=IntegerType(int(machine.get_interval())) if new_execution is not None else None,
            execution_interval=float(machine.get_interval()) if new_execution is not None else None,
            sample_interval=machine.get_sample_interval() if sample_set else None,
            sample_interval_set=sample_set,
        )
        if overrides is not None:
            for tag_name, value in overrides.items():
                tag = app.cvt.get_tag_by_name(name=tag_name)
                if tag is None:
                    continue
                app.machines_engine.put_sample_override(
                    tag=tag,
                    machine=machine,
                    sample_override=value,
                )
    return machine


# Models
update_interval_model = api.model("update_interval_model", {
    'interval': fields.Float(required=True, description='Execution interval in seconds'),
})

transition_model = api.model("transition_model", {
    'to': fields.String(required=True, description='Target state name for transition'),
})

subscribe_model = api.model("subscribe_model", {
    'field_tag': fields.String(required=True, description='Nombre del tag de campo a suscribir'),
    'internal_tag': fields.String(required=True, description='Nombre de la variable interna (default_tag_name) a asociar'),
})

unsubscribe_model = api.model("unsubscribe_model", {
    'tag_name': fields.String(required=True, description='Nombre del tag suscrito a desuscribir'),
})

update_attributes_model = api.model("update_attributes_model", {
    'threshold': fields.Float(required=False, description='Threshold value to update'),
    'interval': fields.Float(required=False, description='Machine execution interval in seconds'),
    'execution_interval': fields.Float(required=False, description='Alias of interval (seconds)'),
    'sample_interval': fields.Float(required=False, description='Independent sample interval in seconds; null = legacy mode'),
    'sample_overrides': fields.Raw(required=False, description='Map of tag name → sample_override seconds'),
    'signal_modes': fields.Raw(
        required=False,
        description="Map of source tag name → 'raw' | 'filtered'",
    ),
    'buffer_size': fields.Integer(required=False, description='Buffer size for input variables'),
    'on_delay': fields.Integer(required=False, description='Delay before starting the machine'),
})


@ns.route('/')
class MachinesResource(Resource):

    @api.doc(security='apikey', description="Retrieves all registered state machines with their serialized state and configuration.")
    @api.response(200, "Success")
    @api.response(500, "Internal server error")
    @Api.token_required(auth=True)
    def get(self):
        r"""
        Get all state machines.

        Retrieves all registered state machines from the State Machine Manager
        and returns their serialized state and configuration.

        Returns a list of dictionaries containing:
        - state: Current state of the machine
        - actions: List of allowed actions/transitions
        - manufacturer: Manufacturer identifier
        - segment: Segment identifier
        - name: Machine name
        - identifier: Unique machine identifier
        - description: Machine description
        - classification: Machine classification
        - interval: Execution interval
        - has_domain_config: Whether the machine implements DomainConfigurable
        - And other machine-specific attributes
        """
        try:
            machines = app.serialize_machines()
            return {
                "data": machines
            }, 200
        except Exception as e:
            return {
                "message": f"Failed to retrieve state machines: {str(e)}"
            }, 500


@ns.route('/<machine_name>')
class MachineByNameResource(Resource):

    @api.doc(security='apikey', description="Retrieves detailed information about a specific state machine by name.")
    @api.response(200, "Success")
    @api.response(404, "Machine not found")
    @api.response(500, "Internal server error")
    @Api.token_required(auth=True)
    def get(self, machine_name: str):
        r"""
        Get detailed information about a specific state machine.

        Retrieves a state machine by name from the State Machine Manager
        and returns detailed information including:
        - process_variables: All ProcessType variables (serialized)
        - subscribed_tags: Tags that the machine is subscribed to (serialized)
        - not_subscribed_tags: ProcessType variables waiting for tag subscription (serialized)
        - internal_process_variables: Internal state variables (not read-only, serialized)
        - read_only_process_type_variables: Read-only input variables (serialized)
        - serialization: Complete machine serialization

        **Parameters:**

        * **machine_name** (str): The name of the state machine to retrieve.

        **Returns:**

        * **dict**: Detailed machine information with all process variables and subscriptions.
        """
        try:
            # Get machine by name using machine_manager
            violation = _machine_scope_error(machine_name=machine_name)
            if violation:
                return violation
            machine = app.get_machine(StringType(machine_name))
            
            if not machine:
                return {
                    "message": f"Machine '{machine_name}' not found"
                }, 404
            
            # Get all required information
            process_variables = machine.get_process_variables()
            
            # Serialize subscribed tags (ProcessType objects)
            subscribed_tags_dict = machine.get_subscribed_tags()
            subscribed_tags = {}
            for tag_name, process_type in subscribed_tags_dict.items():
                payload = process_type.serialize()
                tag = getattr(process_type, "tag", None)
                scan_time = None
                if tag is not None:
                    getter = getattr(tag, "get_scan_time", None)
                    scan_time = getter() if callable(getter) else getattr(tag, "scan_time", None)
                payload["scan_time"] = scan_time
                payload["sample_override"] = (machine.sample_overrides or {}).get(tag_name)
                payload["effective_sample_interval"] = machine._get_effective_sample_interval(tag_name) if machine.get_sample_interval() is not None else None
                source = None
                try:
                    source = machine._wavelet_source_tag(tag) if tag is not None else None
                except Exception:
                    source = None
                source_name = getattr(source, "name", None) if source is not None else tag_name
                payload["source_name"] = source_name
                from ....signal_conditioning.filtered_tags import tag_filter_enabled

                filter_on = bool(source is not None and tag_filter_enabled(source))
                payload["filter_enabled"] = filter_on
                if filter_on:
                    mode = None
                    getter = getattr(machine, "get_signal_mode_for_tag", None)
                    if callable(getter):
                        mode = getter(tag)
                    payload["signal_mode"] = mode or (machine.signal_modes or {}).get(
                        source_name, "filtered"
                    )
                else:
                    payload["signal_mode"] = None
                subscribed_tags[tag_name] = payload

            # Serialize not subscribed tags (ProcessType objects)
            not_subscribed_tags_dict = machine.get_not_subscribed_tags()
            not_subscribed_tags = {
                var_name: process_type.serialize() 
                for var_name, process_type in not_subscribed_tags_dict.items()
            }
            
            # Serialize internal process variables (ProcessType objects)
            internal_process_variables_dict = machine.get_internal_process_type_variables()
            internal_process_variables = {
                var_name: process_type.serialize() 
                for var_name, process_type in internal_process_variables_dict.items()
            }
            
            # Serialize read-only process type variables (ProcessType objects)
            read_only_process_type_variables_dict = machine.get_read_only_process_type_variables()
            read_only_process_type_variables = {
                var_name: process_type.serialize() 
                for var_name, process_type in read_only_process_type_variables_dict.items()
            }
            
            # Get complete serialization
            serialization = machine.serialize()

            # Tags de Campo: solo raw aún libres en ESTA máquina
            # (misma regla que el HMI Dash: quitar los ya suscritos; nunca listar .f).
            from ....signal_conditioning.filtered_tags import is_filtered_derivative_name

            all_field_tags = [
                name
                for name in (app.cvt._cvt.get_field_tags_names() or [])
                if not is_filtered_derivative_name(name)
            ]
            field_tags = machine.get_available_field_tags(all_field_tags)
            field_tags_info = []
            for tag_name in field_tags:
                tag = app.cvt._cvt.get_tag_by_name(name=tag_name)
                info = _field_tag_info(tag, name=tag_name)
                if tag is None:
                    info["opcua_mapped"] = True
                field_tags_info.append(info)
            
            return {
                "data": {
                    "process_variables": process_variables,
                    "subscribed_tags": subscribed_tags,
                    "not_subscribed_tags": not_subscribed_tags,
                    "internal_process_variables": internal_process_variables,
                    "field_tags": field_tags,
                    "field_tags_info": field_tags_info,
                    "read_only_process_type_variables": read_only_process_type_variables,
                    "serialization": serialization
                }
            }, 200
        except Exception as e:
            return {
                "message": f"Failed to retrieve machine details: {str(e)}"
            }, 500

    @api.doc(security='apikey', description="Updates the execution interval of a specific state machine.")
    @api.response(200, "Interval updated successfully")
    @api.response(400, "Invalid request or parameters")
    @api.response(404, "Machine not found")
    @api.response(500, "Internal server error")
    @Api.token_required(auth=True)
    @ns.expect(update_interval_model)
    def put(self, machine_name: str):
        r"""
        Update machine execution interval.

        Updates the execution interval for a specific state machine.

        **Parameters:**

        * **machine_name** (str): The name of the state machine.

        **Request body:**

        * **interval** (float): New execution interval in seconds.

        **Returns:**

        * **dict**: Success message and updated machine data.
        """
        if not request.is_json:
            return {
                "message": "Request must be JSON"
            }, 400
        
        data = request.json
        interval = data.get('interval')
        
        if interval is None:
            return {
                "message": "interval parameter is required"
            }, 400
        
        try:
            interval_value = float(interval)
            if interval_value <= 0:
                return {
                    "message": "interval must be greater than 0"
                }, 400
        except (ValueError, TypeError):
            return {
                "message": "interval must be a valid number"
            }, 400
        
        try:
            # Get machine by name using machine_manager
            violation = _machine_scope_error(machine_name=machine_name)
            if violation:
                return violation
            machine = app.get_machine(StringType(machine_name))
            
            if not machine:
                return {
                    "message": f"Machine '{machine_name}' not found"
                }, 404
            
            try:
                _apply_temporal_update(
                    machine,
                    new_execution=interval_value,
                    new_sample=Ellipsis,
                    overrides=None,
                    user=Api.get_current_user(),
                    persist=True,
                )
            except MachineConfigError as err:
                return {"message": str(err)}, 400
            
            # Return updated machine serialization
            return {
                "message": f"Interval updated successfully to {interval_value} seconds",
                "data": machine.serialize()
            }, 200
        except Exception as e:
            return {
                "message": f"Failed to update machine interval: {str(e)}"
            }, 500


@ns.route('/<machine_name>/transition')
class MachineTransitionResource(Resource):

    @api.doc(security='apikey', description="Executes a state transition for a specific state machine.")
    @api.response(200, "Transition executed successfully")
    @api.response(400, "Invalid request or parameters")
    @api.response(404, "Machine not found")
    @api.response(500, "Internal server error")
    @Api.token_required(auth=True)
    @ns.expect(transition_model)
    def put(self, machine_name: str):
        r"""
        Execute machine state transition.

        Executes a manual transition to a target state for a specific state machine.

        **Parameters:**

        * **machine_name** (str): The name of the state machine.

        **Request body:**

        * **to** (str): Target state name for the transition.

        **Returns:**

        * **dict**: Success message and updated machine data, or error message if transition is not allowed.
        """
        if not request.is_json:
            return {
                "message": "Request must be JSON"
            }, 400
        
        data = request.json
        to_state = data.get('to')
        
        if not to_state:
            return {
                "message": "to parameter is required"
            }, 400
        
        if not isinstance(to_state, str):
            return {
                "message": "to parameter must be a string"
            }, 400
        
        try:
            # Get machine by name using machine_manager
            violation = _machine_scope_error(machine_name=machine_name)
            if violation:
                return violation
            machine = app.get_machine(StringType(machine_name))
            
            if not machine:
                return {
                    "message": f"Machine '{machine_name}' not found"
                }, 404
            
            # Execute transition
            result, message = machine.transition(
                to=to_state,
                user=Api.get_current_user(),
            )
            
            if result is None:
                return {
                    "message": message
                }, 400
            
            # Return updated machine serialization
            return {
                "message": message,
                "data": machine.serialize()
            }, 200
        except Exception as e:
            return {
                "message": f"Failed to execute transition: {str(e)}"
            }, 500


@ns.route('/<machine_name>/subscribe')
class MachineSubscribeResource(Resource):

    @api.doc(
        security='apikey',
        description="Suscribe un tag de campo a una variable interna de una máquina de estado."
    )
    @api.response(200, "Tag suscrito correctamente")
    @api.response(400, "Solicitud inválida o parámetros incorrectos")
    @api.response(404, "Máquina o tag no encontrado")
    @api.response(500, "Error interno del servidor")
    @Api.token_required(auth=True)
    @ns.expect(subscribe_model)
    def post(self, machine_name: str):
        r"""
        Suscribir un tag de campo (`field_tag`) a una variable interna (`internal_tag`)
        de una máquina de estado.

        Equivalente a `machine.subscribe_to(tag=field_tag, default_tag_name=internal_tag)`.
        """
        if not request.is_json:
            return {
                "message": "Request must be JSON"
            }, 400

        data = request.json or {}
        field_tag_name = data.get("field_tag")
        internal_tag_name = data.get("internal_tag")

        if not field_tag_name or not internal_tag_name:
            return {
                "message": "Both 'field_tag' and 'internal_tag' are required"
            }, 400

        try:
            # Obtener máquina
            violation = _machine_scope_error(machine_name=machine_name)
            if violation:
                return violation
            machine = app.get_machine(StringType(machine_name))
            if not machine:
                return {
                    "message": f"Machine '{machine_name}' not found"
                }, 404

            # Obtener tag de campo desde el CVT (mismo que en callbacks Dash)
            field_tag = app.cvt._cvt.get_tag_by_name(name=field_tag_name)
            if not field_tag:
                return {
                    "message": f"Field tag '{field_tag_name}' not found"
                }, 404

            if not _tag_opcua_mapped(field_tag):
                return {
                    "message": (
                        f"El tag de campo '{field_tag_name}' no está mapeado a un cliente OPC UA."
                    )
                }, 400

            if machine.process_type_exists(name=internal_tag_name):
                process_type = getattr(machine, internal_tag_name)
                type_error = _subscription_type_error(
                    process_type,
                    field_tag,
                    internal_tag_name=internal_tag_name,
                    field_tag_name=field_tag_name,
                )
                if type_error:
                    return {"message": type_error}, 400

            subscribed, message = machine.subscribe_to(
                tag=field_tag,
                default_tag_name=internal_tag_name
            )

            if not subscribed:
                return {
                    "message": message or "Subscription failed"
                }, 400

            payload = {
                "message": message or "Tag subscribed successfully",
                "data": machine.serialize(),
            }
            followup = getattr(machine, "subscription_followup", None)
            if callable(followup):
                extra = followup(internal_tag_name, field_tag) or {}
                hint = extra.get("message")
                if hint:
                    payload["hint"] = hint
                    payload["hint_level"] = extra.get("level") or "info"
            return payload, 200
        except ValueError as e:
            return {
                "message": str(e)
            }, 400
        except Exception as e:
            return {
                "message": f"Failed to subscribe tag: {str(e)}"
            }, 500


@ns.route('/<machine_name>/unsubscribe')
class MachineUnsubscribeResource(Resource):

    @api.doc(
        security='apikey',
        description="Desuscribe un tag previamente suscrito de una máquina de estado."
    )
    @api.response(200, "Tag desuscrito correctamente")
    @api.response(400, "Solicitud inválida o parámetros incorrectos")
    @api.response(404, "Máquina o tag no encontrado")
    @api.response(500, "Error interno del servidor")
    @Api.token_required(auth=True)
    @ns.expect(unsubscribe_model)
    def post(self, machine_name: str):
        r"""
        Desuscribir un tag previamente suscrito de una máquina de estado.

        Equivalente a `machine.unsubscribe_to(tag=tag)`.
        """
        if not request.is_json:
            return {
                "message": "Request must be JSON"
            }, 400

        data = request.json or {}
        tag_name = data.get("tag_name")

        if not tag_name:
            return {
                "message": "'tag_name' is required"
            }, 400

        try:
            # Obtener máquina
            violation = _machine_scope_error(machine_name=machine_name)
            if violation:
                return violation
            machine = app.get_machine(StringType(machine_name))
            if not machine:
                return {
                    "message": f"Machine '{machine_name}' not found"
                }, 404

            # Obtener tag por nombre usando PyAutomation (mismo que en callbacks Dash)
            tag = app.get_tag_by_name(name=tag_name)
            if not tag:
                return {
                    "message": f"Tag '{tag_name}' not found"
                }, 404

            if not machine.unsubscribe_to(tag=tag):
                return {
                    "message": "Unsubscription failed"
                }, 400

            return {
                "message": "Tag unsubscribed successfully",
                "data": machine.serialize()
            }, 200
        except Exception as e:
            return {
                "message": f"Failed to unsubscribe tag: {str(e)}"
            }, 500


@ns.route('/<machine_name>/attributes')
class MachineAttributesResource(Resource):

    @api.doc(
        security='apikey',
        description="Actualiza atributos específicos de una máquina de estado (threshold, interval, buffer_size, on_delay)."
    )
    @api.response(200, "Atributos actualizados correctamente")
    @api.response(400, "Solicitud inválida o parámetros incorrectos")
    @api.response(404, "Máquina no encontrada")
    @api.response(500, "Error interno del servidor")
    @Api.token_required(auth=True)
    @ns.expect(update_attributes_model)
    def put(self, machine_name: str):
        r"""
        Actualizar atributos genéricos de una máquina de estado.

        Permite actualizar únicamente:
        - threshold: Valor del umbral (float)
        - interval / execution_interval: Intervalo de ejecución en segundos (float)
        - sample_interval: Intervalo de muestreo independiente (float o null)
        - sample_overrides: Mapa tag → segundos
        - signal_modes: Mapa source tag → 'raw' | 'filtered'
        - buffer_size: Tamaño del buffer (int)
        - on_delay: Retraso antes de iniciar (int)

        Cualquier otro campo se rechaza con 400. La configuración de dominio
        usa ``PUT /machines/<name>/domain-config``.

        **Parámetros:**

        * **machine_name** (str): Nombre de la máquina de estado.

        **Returns:**

        * **dict**: Mensaje de éxito y datos actualizados de la máquina.
        """
        if not request.is_json:
            return {
                "message": "Request must be JSON"
            }, 400

        data = request.json or {}
        unknown = unknown_generic_attribute_keys(data)
        if unknown:
            return {
                "message": (
                    "Unsupported attribute(s) for generic configuration: "
                    f"{', '.join(unknown)}. Use /domain-config for domain fields."
                )
            }, 400

        threshold = data.get("threshold")
        interval = data.get("execution_interval", data.get("interval"))
        sample_interval_provided = "sample_interval" in data
        sample_interval = data.get("sample_interval") if sample_interval_provided else Ellipsis
        sample_overrides = data.get("sample_overrides")
        signal_modes = data.get("signal_modes")
        buffer_size = data.get("buffer_size")
        on_delay = data.get("on_delay")
        user = Api.get_current_user()

        if (
            threshold is None
            and interval is None
            and not sample_interval_provided
            and sample_overrides is None
            and signal_modes is None
            and buffer_size is None
            and on_delay is None
        ):
            return {
                "message": (
                    "At least one attribute (threshold, interval, sample_interval, "
                    "sample_overrides, signal_modes, buffer_size, on_delay) must be provided"
                )
            }, 400

        try:
            # Obtener máquina
            violation = _machine_scope_error(machine_name=machine_name)
            if violation:
                return violation
            machine = app.get_machine(StringType(machine_name))
            if not machine:
                return {
                    "message": f"Machine '{machine_name}' not found"
                }, 404

            updated_attributes = []
            yaml_persist = {}

            # Actualizar threshold
            if threshold is not None:
                try:
                    threshold_value = float(threshold)
                    threshold_unit = machine.threshold.unit or "%"
                    if machine.threshold.value and hasattr(machine.threshold.value, "__class__"):
                        class_name = machine.threshold.value.__class__.__name__
                        if class_name == "Percentage":
                            new_percentage = Percentage(threshold_value, unit=threshold_unit)
                            machine.threshold.set_value(
                                value=new_percentage,
                                machine=machine,
                                name="threshold",
                                user=user,
                            )
                        else:
                            machine.threshold.value.value = threshold_value
                            if machine.threshold.tag:
                                machine.threshold.set_value(
                                    value=machine.threshold.value,
                                    machine=machine,
                                    name="threshold",
                                    user=user,
                                )
                    else:
                        new_percentage = Percentage(threshold_value, unit=threshold_unit)
                        machine.threshold.set_value(
                            value=new_percentage,
                            machine=machine,
                            name="threshold",
                            user=user,
                        )

                    app.machines_engine.put(
                        name=StringType(machine_name),
                        threshold=FloatType(threshold_value)
                    )

                    yaml_persist["threshold"] = threshold_value
                    updated_attributes.append(f"threshold to {threshold_value}")
                except (ValueError, TypeError) as e:
                    return {
                        "message": f"Invalid threshold value: {str(e)}"
                    }, 400

            # Actualizar interval / sample_interval
            if interval is not None or sample_interval_provided or sample_overrides is not None:
                try:
                    interval_value = float(interval) if interval is not None else None
                    if interval_value is not None and interval_value <= 0:
                        return {
                            "message": "interval must be greater than 0"
                        }, 400
                    if sample_overrides is not None and not isinstance(sample_overrides, dict):
                        return {
                            "message": "sample_overrides must be an object of tag_name → seconds"
                        }, 400
                    _apply_temporal_update(
                        machine,
                        new_execution=interval_value,
                        new_sample=sample_interval,
                        overrides=sample_overrides,
                        user=user,
                        persist=True,
                    )
                    if interval_value is not None:
                        updated_attributes.append(f"interval to {interval_value}")
                    if sample_interval_provided:
                        updated_attributes.append(f"sample_interval to {sample_interval}")
                    if sample_overrides is not None:
                        updated_attributes.append("sample_overrides")
                except MachineConfigError as e:
                    return {
                        "message": str(e)
                    }, 400
                except (ValueError, TypeError) as e:
                    return {
                        "message": f"Invalid interval value: {str(e)}"
                    }, 400

            # Actualizar signal_modes (raw vs filtrado por suscripción)
            if signal_modes is not None:
                if not isinstance(signal_modes, dict):
                    return {
                        "message": "signal_modes must be an object of tag_name → 'raw'|'filtered'"
                    }, 400
                try:
                    machine.set_signal_modes(signal_modes, user=user)
                    updated_attributes.append("signal_modes")
                except (ValueError, TypeError) as e:
                    return {
                        "message": f"Invalid signal_modes: {str(e)}"
                    }, 400

            # Actualizar buffer_size
            if buffer_size is not None:
                try:
                    buffer_size_value = int(buffer_size)
                    if buffer_size_value <= 0:
                        return {
                            "message": "buffer_size must be greater than 0"
                        }, 400

                    # Persistir YAML ANTES del restart (while_starting relee configs).
                    yaml_persist["buffer_size"] = buffer_size_value
                    if hasattr(machine, "persist_ui_config_attributes"):
                        try:
                            machine.persist_ui_config_attributes(
                                buffer_size=buffer_size_value
                            )
                        except Exception as persist_err:
                            return {
                                "message": (
                                    f"Failed to persist buffer_size to config: {persist_err}"
                                )
                            }, 500
                        yaml_persist.pop("buffer_size", None)

                    # Actualizar buffer_size y reiniciar la máquina
                    machine.set_buffer_size(size=buffer_size_value)
                    machine.transition(to="restart", user=user)
                    
                    app.machines_engine.put(
                        name=StringType(machine_name),
                        buffer_size=IntegerType(buffer_size_value)
                    )
                    
                    # Volver al estado wait
                    machine.transition(to="wait", user=user)
                    
                    updated_attributes.append(f"buffer_size to {buffer_size_value}")
                except (ValueError, TypeError) as e:
                    return {
                        "message": f"Invalid buffer_size value: {str(e)}"
                    }, 400

            # Actualizar on_delay
            if on_delay is not None:
                try:
                    on_delay_value = int(on_delay)
                    if on_delay_value < 0:
                        return {
                            "message": "on_delay must be greater than or equal to 0"
                        }, 400
                    
                    previous_on_delay = getattr(getattr(machine, "on_delay", None), "value", None)
                    machine.on_delay.value = on_delay_value
                    if hasattr(machine, "_on_delay_from_plant_config"):
                        machine._on_delay_from_plant_config = True
                    yaml_persist["on_delay"] = on_delay_value
                    
                    app.machines_engine.put(
                        name=StringType(machine_name),
                        on_delay=IntegerType(on_delay_value)
                    )
                    
                    updated_attributes.append(f"on_delay to {on_delay_value}")
                    if user is not None:
                        try:
                            from ....utils.system_event_audit import clip, persist_system_event

                            persist_system_event(
                                message="Machine on_delay updated",
                                description=clip(
                                    f"machine={machine_name} from={previous_on_delay} to={on_delay_value}",
                                    256,
                                ),
                                classification="Configuration",
                                priority=2,
                                criticity=3,
                                user=user,
                            )
                        except Exception:
                            pass
                except (ValueError, TypeError) as e:
                    return {
                        "message": f"Invalid on_delay value: {str(e)}"
                    }, 400

            # Persistencia de atributos genéricos (threshold, on_delay, etc.)
            if yaml_persist and hasattr(machine, "persist_ui_config_attributes"):
                try:
                    machine.persist_ui_config_attributes(**yaml_persist)
                except Exception as persist_err:
                    return {
                        "message": f"Failed to persist attributes to config: {persist_err}"
                    }, 500

            # Construir mensaje de éxito
            message = f"Successfully updated: {', '.join(updated_attributes)}"

            return {
                "message": message,
                "data": machine.serialize()
            }, 200

        except Exception as e:
            return {
                "message": f"Failed to update machine attributes: {str(e)}"
            }, 500


def _resolve_domain_machine(machine_name: str):
    violation = _machine_scope_error(machine_name=machine_name)
    if violation:
        return None, violation
    machine = app.get_machine(StringType(machine_name))
    if not machine:
        return None, ({"message": f"Machine '{machine_name}' not found"}, 404)
    if not supports_domain_config(machine):
        return None, ({"message": f"Machine '{machine_name}' has no domain configuration"}, 404)
    return machine, None


@ns.route('/<machine_name>/domain-config')
class MachineDomainConfigResource(Resource):

    @api.doc(
        security='apikey',
        description="Returns the domain UI schema and current configuration for a DomainConfigurable machine.",
    )
    @api.response(200, "Success")
    @api.response(404, "Machine not found or does not implement DomainConfigurable")
    @api.response(500, "Internal server error")
    @Api.token_required(auth=True)
    def get(self, machine_name: str):
        machine, error = _resolve_domain_machine(machine_name)
        if error:
            return error
        try:
            schema = machine.get_ui_schema() or {}
            config = machine.get_config() or {}
            if not isinstance(schema, dict) or not isinstance(config, dict):
                return {
                    "message": "Domain configuration methods must return objects"
                }, 500
            return {
                "schema": schema,
                "config": config,
            }, 200
        except Exception as e:
            return {
                "message": f"Failed to retrieve domain configuration: {str(e)}"
            }, 500

    @api.doc(
        security='apikey',
        description="Updates domain configuration via put_config on a DomainConfigurable machine.",
    )
    @api.response(200, "Configuration updated")
    @api.response(400, "Validation error")
    @api.response(404, "Machine not found or does not implement DomainConfigurable")
    @api.response(500, "Internal server error")
    @Api.token_required(auth=True)
    def put(self, machine_name: str):
        if not request.is_json:
            return {
                "message": "Request must be JSON"
            }, 400
        machine, error = _resolve_domain_machine(machine_name)
        if error:
            return error
        payload = request.json or {}
        if not isinstance(payload, dict):
            return {
                "message": "Payload must be a JSON object"
            }, 400
        try:
            before = machine.get_config() or {}
        except Exception:
            before = {}
        try:
            schema = machine.get_ui_schema() or {}
        except Exception:
            schema = {}
        try:
            config = machine.put_config(payload)
            if not isinstance(config, dict):
                config = machine.get_config() or {}
            try:
                audit_domain_config_change(
                    machine_name=machine_name,
                    payload=payload,
                    before=before,
                    after=config,
                    schema=schema,
                    user=Api.get_current_user(),
                )
            except Exception:
                pass
            return {
                "status": "success",
                "config": config,
            }, 200
        except (ValueError, TypeError) as e:
            return {
                "message": str(e)
            }, 400
        except Exception as e:
            return {
                "message": f"Failed to update domain configuration: {str(e)}"
            }, 500


@ns.route('/<machine_name>/domain-config/files')
class MachineDomainConfigFilesResource(Resource):

    @api.doc(
        security='apikey',
        description=(
            "Uploads domain artifact files for one schema field. "
            "The machine must implement put_domain_files(field_key, files)."
        ),
    )
    @api.response(200, "Files stored")
    @api.response(400, "Validation error")
    @api.response(404, "Machine not found or does not accept domain files")
    @api.response(500, "Internal server error")
    @Api.token_required(auth=True)
    def post(self, machine_name: str):
        machine, error = _resolve_domain_machine(machine_name)
        if error:
            return error
        if not supports_domain_files(machine):
            return {
                "message": f"Machine '{machine_name}' does not accept domain file uploads"
            }, 404
        field_key = str(request.form.get("field") or "").strip()
        if not field_key:
            return {"message": "Missing form field 'field'"}, 400
        storages = request.files.getlist("files")
        if not storages:
            return {"message": "Missing files"}, 400
        uploads = []
        for storage in storages:
            filename = os.path.basename(str(getattr(storage, "filename", "") or "")).strip()
            if not filename or filename in {".", ".."}:
                return {"message": "Each file must have a name"}, 400
            if os.path.sep in filename or "/" in filename or "\\" in filename:
                return {"message": f"Invalid file name: {filename}"}, 400
            payload = storage.read()
            uploads.append((filename, payload))
        try:
            before = machine.get_config() or {}
        except Exception:
            before = {}
        try:
            schema = machine.get_ui_schema() or {}
        except Exception:
            schema = {}
        try:
            config = machine.put_domain_files(field_key, uploads)
            if not isinstance(config, dict):
                config = machine.get_config() or {}
            payload = domain_files_upload_payload(
                config, field_key=field_key, uploads=uploads
            )
            try:
                audit_domain_config_change(
                    machine_name=machine_name,
                    payload={"_files": field_key},
                    before=before,
                    after=payload.get("config") or config,
                    schema=schema,
                    user=Api.get_current_user(),
                )
            except Exception:
                pass
            return payload, 200
        except (ValueError, TypeError) as e:
            return {"message": str(e)}, 400
        except Exception:
            logger.exception(
                "Failed to store domain files for machine %s field %s",
                machine_name,
                field_key,
            )
            return {"message": "Failed to store domain files"}, 500
