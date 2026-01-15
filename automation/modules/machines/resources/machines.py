from flask import request
from flask_restx import Namespace, Resource, fields
from .... import PyAutomation
from ....extensions.api import api
from ....extensions import _api as Api
from ....models import StringType, FloatType, IntegerType
from ....variables import Percentage


ns = Namespace('Machines', description='State Machine Management Resources')
app = PyAutomation()

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
            machine = app.machine_manager.get_machine(name=StringType(machine_name))
            
            if not machine:
                return {
                    "message": f"Machine '{machine_name}' not found"
                }, 404
            
            # Get all required information
            process_variables = machine.get_process_variables()
            
            # Serialize subscribed tags (ProcessType objects)
            subscribed_tags_dict = machine.get_subscribed_tags()
            subscribed_tags = {
                tag_name: process_type.serialize() 
                for tag_name, process_type in subscribed_tags_dict.items()
            }
            
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

            # Field tags
            field_tags = app.cvt._cvt.get_field_tags_names()
            
            return {
                "data": {
                    "process_variables": process_variables,
                    "subscribed_tags": subscribed_tags,
                    "not_subscribed_tags": not_subscribed_tags,
                    "internal_process_variables": internal_process_variables,
                    "field_tags": field_tags,
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
            machine = app.machine_manager.get_machine(name=StringType(machine_name))
            
            if not machine:
                return {
                    "message": f"Machine '{machine_name}' not found"
                }, 404
            
            # Update interval
            machine.set_interval(interval=FloatType(interval_value))
            
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
            machine = app.machine_manager.get_machine(name=StringType(machine_name))
            
            if not machine:
                return {
                    "message": f"Machine '{machine_name}' not found"
                }, 404
            
            # Execute transition
            result, message = machine.transition(to=to_state)
            
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
            machine = app.machine_manager.get_machine(name=StringType(machine_name))
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

            subscribed, message = machine.subscribe_to(
                tag=field_tag,
                default_tag_name=internal_tag_name
            )

            if not subscribed:
                return {
                    "message": message or "Subscription failed"
                }, 400

            # Devolvemos la serialización actualizada de la máquina
            return {
                "message": message or "Tag subscribed successfully",
                "data": machine.serialize()
            }, 200
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
            machine = app.machine_manager.get_machine(name=StringType(machine_name))
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
        Actualizar atributos específicos de una máquina de estado.

        Permite actualizar los siguientes atributos:
        - threshold: Valor del umbral (float)
        - interval: Intervalo de ejecución en segundos (float)
        - buffer_size: Tamaño del buffer (int)
        - on_delay: Retraso antes de iniciar (int)

        **Parámetros:**

        * **machine_name** (str): Nombre de la máquina de estado.

        **Request body:**

        * **threshold** (float, opcional): Nuevo valor del threshold.
        * **interval** (float, opcional): Nuevo intervalo de ejecución.
        * **buffer_size** (int, opcional): Nuevo tamaño del buffer.
        * **on_delay** (int, opcional): Nuevo valor de on_delay.

        **Notas:**

        * Para máquinas de tipo "leak detection" con nombre "npw", el threshold se limita entre 0 y 100.
        * Al actualizar buffer_size, la máquina se reinicia automáticamente.
        * Los cambios se persisten en la base de datos si está conectada.

        **Returns:**

        * **dict**: Mensaje de éxito y datos actualizados de la máquina.
        """
        if not request.is_json:
            return {
                "message": "Request must be JSON"
            }, 400

        data = request.json or {}
        threshold = data.get("threshold")
        interval = data.get("interval")
        buffer_size = data.get("buffer_size")
        on_delay = data.get("on_delay")

        # Validar que al menos un atributo esté presente
        if threshold is None and interval is None and buffer_size is None and on_delay is None:
            return {
                "message": "At least one attribute (threshold, interval, buffer_size, on_delay) must be provided"
            }, 400

        try:
            # Obtener máquina
            machine = app.machine_manager.get_machine(name=StringType(machine_name))
            if not machine:
                return {
                    "message": f"Machine '{machine_name}' not found"
                }, 404

            updated_attributes = []

            # Actualizar threshold
            if threshold is not None:
                try:
                    threshold_value = float(threshold)
                    
                    # Validación especial para máquinas de leak detection tipo NPW
                    if "leak detection" in machine.classification.value.lower():
                        if machine_name.lower() == "npw":
                            if threshold_value > 100:
                                threshold_value = 100
                            elif threshold_value < 0:
                                threshold_value = 0
                            # Actualizar threshold_iqr si existe el atributo wavelet
                            if hasattr(machine, "wavelet"):
                                machine.wavelet.threshold_iqr = threshold_value
                    
                    # Actualizar el threshold de la máquina
                    # Crear un nuevo objeto Percentage con el nuevo valor (similar a como se carga desde config)
                    threshold_unit = machine.threshold.unit or "%"
                    if machine.threshold.value and hasattr(machine.threshold.value, "__class__"):
                        # Obtener la clase del objeto actual (Percentage, FloatType, etc.)
                        class_name = machine.threshold.value.__class__.__name__
                        if class_name == "Percentage":
                            # Crear un nuevo objeto Percentage con el nuevo valor
                            new_percentage = Percentage(threshold_value, unit=threshold_unit)
                            # Usar set_value para actualizar tanto el ProcessType como el tag asociado
                            machine.threshold.set_value(value=new_percentage, machine=machine, name="threshold")
                        else:
                            # Si no es Percentage, actualizar directamente el valor y usar set_value
                            machine.threshold.value.value = threshold_value
                            # Si tiene tag, actualizarlo también usando set_value
                            if machine.threshold.tag:
                                machine.threshold.set_value(value=machine.threshold.value, machine=machine, name="threshold")
                    else:
                        # Si no hay valor inicial, crear un nuevo Percentage y usar set_value
                        new_percentage = Percentage(threshold_value, unit=threshold_unit)
                        machine.threshold.set_value(value=new_percentage, machine=machine, name="threshold")
                    
                    # Actualizar en la base de datos si está conectada
                    if app.is_db_connected():
                        app.machines_engine.put(
                            name=StringType(machine_name),
                            threshold=FloatType(threshold_value)
                        )
                    
                    updated_attributes.append(f"threshold to {threshold_value}")
                except (ValueError, TypeError) as e:
                    return {
                        "message": f"Invalid threshold value: {str(e)}"
                    }, 400

            # Actualizar interval
            if interval is not None:
                try:
                    interval_value = float(interval)
                    if interval_value <= 0:
                        return {
                            "message": "interval must be greater than 0"
                        }, 400
                    
                    machine.set_interval(interval=FloatType(interval_value))
                    
                    # Actualizar en la base de datos si está conectada
                    if app.is_db_connected():
                        app.machines_engine.put(
                            name=StringType(machine_name),
                            machine_interval=IntegerType(int(interval_value))
                        )
                    
                    updated_attributes.append(f"interval to {interval_value}")
                except (ValueError, TypeError) as e:
                    return {
                        "message": f"Invalid interval value: {str(e)}"
                    }, 400

            # Actualizar buffer_size
            if buffer_size is not None:
                try:
                    buffer_size_value = int(buffer_size)
                    if buffer_size_value <= 0:
                        return {
                            "message": "buffer_size must be greater than 0"
                        }, 400
                    
                    # Actualizar buffer_size y reiniciar la máquina
                    machine.set_buffer_size(size=buffer_size_value)
                    machine.transition(to="restart")
                    
                    # Actualizar en la base de datos si está conectada
                    if app.is_db_connected():
                        app.machines_engine.put(
                            name=StringType(machine_name),
                            buffer_size=IntegerType(buffer_size_value)
                        )
                    
                    # Volver al estado wait
                    machine.transition(to="wait")
                    
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
                    
                    machine.on_delay.value = on_delay_value
                    
                    # Actualizar en la base de datos si está conectada
                    if app.is_db_connected():
                        app.machines_engine.put(
                            name=StringType(machine_name),
                            on_delay=IntegerType(on_delay_value)
                        )
                    
                    updated_attributes.append(f"on_delay to {on_delay_value}")
                except (ValueError, TypeError) as e:
                    return {
                        "message": f"Invalid on_delay value: {str(e)}"
                    }, 400

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
