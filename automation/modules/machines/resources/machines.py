from flask import request
from flask_restx import Namespace, Resource, fields
from .... import PyAutomation
from ....extensions.api import api
from ....extensions import _api as Api
from ....models import StringType, FloatType, IntegerType


ns = Namespace('Machines', description='State Machine Management Resources')
app = PyAutomation()

# Models
update_interval_model = api.model("update_interval_model", {
    'interval': fields.Float(required=True, description='Execution interval in seconds'),
})

transition_model = api.model("transition_model", {
    'to': fields.String(required=True, description='Target state name for transition'),
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
            
            return {
                "data": {
                    "process_variables": process_variables,
                    "subscribed_tags": subscribed_tags,
                    "not_subscribed_tags": not_subscribed_tags,
                    "internal_process_variables": internal_process_variables,
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

