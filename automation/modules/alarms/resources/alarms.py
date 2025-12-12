from flask_restx import Namespace, Resource, fields, reqparse
from .... import PyAutomation
from automation.alarms import AlarmState
from ....extensions.api import api
from ....extensions import _api as Api


ns = Namespace('Alarms', description='Alarm Management Resources')
app = PyAutomation()

# Models
shelve_alarm_resource_by_name_model = api.model("shelve_alarm_resource_by_name_model",{
    'seconds': fields.Integer(required=False, description='Shelve duration in seconds'),
    'minutes': fields.Integer(required=False, description='Shelve duration in minutes'),
    'hours': fields.Integer(required=False, description='Shelve duration in hours'),
    'days': fields.Integer(required=False, description='Shelve duration in days'),
    'weeks': fields.Integer(required=False, description='Shelve duration in weeks')
})

append_alarm_resource_model = api.model("append_alarm_resource_model",{
    'name': fields.String(required=True, description='Unique Alarm Name'),
    'tag': fields.String(required=True, description='Tag name to associate with the alarm'),
    'description': fields.String(required=False, description='Alarm description'),
    'type': fields.String(required=True, description='Alarm Type. Allowed values: ["HIGH-HIGH", "HIGH", "BOOL", "LOW", "LOW-LOW"]'),
    'trigger_value': fields.Float(required=True, description="Value that triggers the alarm")
})

create_alarm_model = api.model("create_alarm_model", {
    'name': fields.String(required=True, description='Unique alarm name'),
    'tag': fields.String(required=True, description='Tag name to monitor'),
    'alarm_type': fields.String(required=False, description='Alarm type (BOOL, HIGH, LOW, HIGH-HIGH, LOW-LOW)', default='BOOL'),
    'trigger_value': fields.Raw(required=False, description='Value that triggers the alarm (bool, float, or int)', default=True),
    'description': fields.String(required=False, description='Alarm description', default='')
})

update_alarm_model = api.model("update_alarm_model", {
    'id': fields.String(required=True, description='Alarm ID'),
    'name': fields.String(required=False, description='Alarm name'),
    'tag': fields.String(required=False, description='Tag name to monitor'),
    'description': fields.String(required=False, description='Alarm description'),
    'alarm_type': fields.String(required=False, description='Alarm type (BOOL, HIGH, LOW, HIGH-HIGH, LOW-LOW)'),
    'trigger_value': fields.Raw(required=False, description='Value that triggers the alarm (int or float)')
})

# Parsers
shelve_alarm_parser = reqparse.RequestParser()
shelve_alarm_parser.add_argument("seconds", type=int, required=False, help='Shelve time in seconds', default=0)
shelve_alarm_parser.add_argument("minutes", type=int, required=False, help='Shelve time in minutes', default=0)
shelve_alarm_parser.add_argument("hours", type=int, required=False, help='Shelve time in hours', default=0)
shelve_alarm_parser.add_argument("days", type=int, required=False, help='Shelve time in days', default=0)
shelve_alarm_parser.add_argument("weeks", type=int, required=False, help='Shelve time in weeks', default=0)

append_alarm_parser = reqparse.RequestParser()
append_alarm_parser.add_argument('name', type=str, required=True, help='Alarm Name')
append_alarm_parser.add_argument('tag', type=str, required=True, help='Tag to whom the alarm will be subscribed')
append_alarm_parser.add_argument('description', type=str, required=False, help='Alarm description', default="")
append_alarm_parser.add_argument('type', type=str, required=True, help='Alarm Type', choices=["HIGH-HIGH", "HIGH", "BOOL", "LOW", "LOW-LOW"])
append_alarm_parser.add_argument('trigger_value', type=float, required=True, help="Alarm trigger value")


@ns.route('/')
class AlarmsCollection(Resource):

    parser = reqparse.RequestParser()
    parser.add_argument('page', type=int, location='args', help='Page number', default=1)
    parser.add_argument('limit', type=int, location='args', help='Items per page', default=20)

    @api.doc(security='apikey', description="Retrieves a list of all configured alarms with pagination support.")
    @api.response(200, "Success")
    @ns.expect(parser)
    @Api.token_required(auth=True)
    def get(self):
        """
        Get all alarms.

        Retrieves a paginated list of all alarms currently defined in the system.
        Supports pagination via query parameters: page (default: 1) and limit (default: 20).
        """
        args = self.parser.parse_args()
        page = args.get('page', 1)
        limit = args.get('limit', 20)
        
        # Validate pagination parameters
        if page < 1:
            return {'message': 'Page number must be greater than 0'}, 400
        if limit < 1:
            return {'message': 'Limit must be greater than 0'}, 400
        
        # Get all alarms
        all_alarms = app.alarm_manager.serialize()
        total = len(all_alarms)
        
        # Calculate pagination
        start_idx = (page - 1) * limit
        end_idx = start_idx + limit
        paginated_alarms = all_alarms[start_idx:end_idx]
        
        return {
            'data': paginated_alarms,
            'pagination': {
                'page': page,
                'limit': limit,
                'total': total,
                'pages': (total + limit - 1) // limit if total > 0 else 0
            }
        }, 200
    
@ns.route('/active_alarms')
class ActiveAlarmsCollection(Resource):

    @api.doc(security='apikey', description="Checks if there are any active alarms.")
    @api.response(200, "Success", model=fields.Boolean)
    @Api.token_required(auth=True)
    def get(self):
        """
        Check for active alarms.

        Returns True if there is at least one alarm in an active state, False otherwise.
        """
        if app.alarm_manager.get_lasts_active_alarms(lasts=1):
            
            return True, 200
        
        return False, 200

    
@ns.route('/<id>')
@api.param('id', 'The alarm identifier')
class AlarmResource(Resource):

    @api.doc(security='apikey', description="Retrieves an alarm by its ID.")
    @api.response(200, "Success")
    @api.response(400, "Alarm not found")
    @Api.token_required(auth=True)
    def get(self, id):
        """
        Get alarm by ID.

        Retrieves detailed information about a specific alarm using its unique identifier.
        """
        alarm = app.get_alarm(id)

        if alarm:
        
            return alarm.serialize(), 200

        return {'message': f"Alarm ID {id} does not exist"}, 400
    

@ns.route('/name/<alarm_name>')
@api.param('alarm_name', 'The alarm name')
class AlarmByNameResource(Resource):

    @api.doc(security='apikey', description="Retrieves an alarm by its name.")
    @api.response(200, "Success")
    @api.response(400, "Alarm not found")
    @Api.token_required(auth=True)
    def get(self, alarm_name):
        """
        Get alarm by name.

        Retrieves detailed information about a specific alarm using its name.
        """
        alarm = app.alarm_manager.get_alarm_by_name(alarm_name)

        if alarm:

            return alarm.serialize(), 200 
        
        return {'message': f"Alarm Name {alarm_name} does not exist"}, 400
    
    
@ns.route('/acknowledge/<alarm_name>')
@api.param('alarm_name', 'The alarm name')
class AckAlarmByNameResource(Resource):
    
    @api.doc(security='apikey', description="Acknowledges an active alarm.")
    @api.response(200, "Alarm acknowledged successfully")
    @api.response(400, "Alarm not found or not in a state to be acknowledged")
    @Api.token_required(auth=True)
    def post(self, alarm_name:str):
        """
        Acknowledge alarm.

        Acknowledges an alarm that is in an Unacknowledged or Return to Normal Unacknowledged state.
        """
        result = dict()
        alarm = app.alarm_manager.get_alarm_by_name(alarm_name)

        if alarm:

            if alarm.state in [AlarmState.UNACK, AlarmState.RTNUN]:
                user = Api.get_current_user()
                alarm.acknowledge(user=user)
                result['message'] = f"{alarm.name} was acknowledged successfully"
                result['data'] = alarm.serialize()

                return result, 200

            return {'message': f"Alarm Name {alarm_name} is not in Unacknowledged state"}, 400

        return {'message': f"Alarm Name {alarm_name} does not exist"}, 400

    
@ns.route('/acknowledge_all')
class AckAllAlarmsResource(Resource):

    @api.doc(security='apikey', description="Acknowledges all active alarms.")
    @api.response(200, "All alarms acknowledged successfully")
    @Api.token_required(auth=True)
    def post(self):
        """
        Acknowledge all alarms.

        Iterates through all alarms and acknowledges those that are in an Unacknowledged state.
        """
        alarms = app.alarm_manager.get_alarms()

        for _, alarm in alarms.items():

            if alarm.state in [AlarmState.UNACK, AlarmState.RTNUN]:
                
                user = Api.get_current_user()
                alarm.acknowledge(user=user)
        
        result = {
            'message': "Alarms were acknowledged successfully"
        }
        
        return result, 200
    

@ns.route('/designed_suppression/<alarm_name>')
@api.param('alarm_name', 'The alarm name')
class SuppressByDesignAlarmByNameResource(Resource):
    
    @api.doc(security='apikey', description="Suppresses an alarm by design.")
    @api.response(200, "Alarm suppressed successfully")
    @api.response(400, "Alarm not found")
    @Api.token_required(auth=True)
    def post(self, alarm_name:str):
        """
        Suppress alarm by design.

        Places the alarm into a 'Designed Suppression' state, preventing it from triggering.
        """
        result = dict()
        alarm = app.alarm_manager.get_alarm_by_name(alarm_name)

        if alarm:
            user = Api.get_current_user()
            alarm.designed_suppression(user=user)
            result['message'] = f"{alarm.name} was suppressed by design successfully"
            result['data'] = alarm.serialize()

            return result, 200

        return {'message': f"Alarm Name {alarm_name} does not exist"}, 400


@ns.route('/designed_unsuppression/<alarm_name>')
@api.param('alarm_name', 'The alarm name')
class DesignedUnsuppressionAlarmByNameResource(Resource):
    
    @api.doc(security='apikey', description="Unsuppresses an alarm that was suppressed by design.")
    @api.response(200, "Alarm unsuppressed successfully")
    @api.response(400, "Alarm not found or not in suppressed state")
    @Api.token_required(auth=True)
    def post(self, alarm_name:str):
        """
        Unsuppress alarm by design.

        Returns an alarm from 'Designed Suppression' state back to normal operation.
        """
        result = dict()
        alarm = app.alarm_manager.get_alarm_by_name(alarm_name)

        if alarm:

            if alarm.state in [AlarmState.DSUPR]:
                user = Api.get_current_user()
                alarm.designed_unsuppression(user=user)
                result['message'] = f"{alarm.name} was unsuppressed by design successfully"
                result['data'] = alarm.serialize()

                return result, 200

            return {'message': f"You cannot unsuppress by design an alarm if not in suppress state"}, 400

        return {'message': f"Alarm Name {alarm_name} does not exist"}, 400


@ns.route('/remove_from_service/<alarm_name>')
@api.param('alarm_name', 'The alarm name')
class OutOfServiceAlarmByNameResource(Resource):
    
    @api.doc(security='apikey', description="Removes an alarm from service.")
    @api.response(200, "Alarm removed from service successfully")
    @api.response(400, "Alarm not found")
    @Api.token_required(auth=True)
    def post(self, alarm_name:str):
        """
        Remove alarm from service.

        Places the alarm into 'Out Of Service' state, disabling it completely.
        """
        result = dict()
        alarm = app.alarm_manager.get_alarm_by_name(alarm_name)

        if alarm:
            user = Api.get_current_user()
            alarm.remove_from_service(user=user)
            result['message'] = f"{alarm.name} was pushed in out of service successfully"
            result['data'] = alarm.serialize()

            return result, 200

        return {'message': f"Alarm Name {alarm_name} does not exist"}, 400


@ns.route('/shelve/<alarm_name>')
@api.param('alarm_name', 'The alarm name')
class ShelveAlarmByNameResource(Resource):
    
    @api.doc(security='apikey', description="Shelves an alarm for a specified duration.")
    @api.response(200, "Alarm shelved successfully")
    @api.response(400, "Alarm not found")
    @Api.token_required(auth=True)
    @ns.expect(shelve_alarm_resource_by_name_model)
    def post(self, alarm_name:str):
        """
        Shelve alarm.

        Temporarily suppresses an alarm for a specified duration (seconds, minutes, hours, days, weeks).
        """
        result = dict()
        args = shelve_alarm_parser.parse_args()
        alarm = app.alarm_manager.get_alarm_by_name(alarm_name)
        if alarm:
            user = Api.get_current_user()
            alarm.shelve(
                user=user,
                **args
            )
            result['message'] = f"{alarm.name} was shelved successfully"
            result['data'] = alarm.serialize()

            return result, 200

        return {'message': f"Alarm Name {alarm_name} does not exist"}, 400


@ns.route('/return_to_service/<alarm_name>')
@api.param('alarm_name', 'The alarm name')
class ReturnToServiceAlarmByNameResource(Resource):
    
    @api.doc(security='apikey', description="Returns an alarm to service.")
    @api.response(200, "Alarm returned to service successfully")
    @api.response(400, "Alarm not found or not in Out of Service state")
    @Api.token_required(auth=True)
    def post(self, alarm_name:str):
        """
        Return alarm to service.

        Returns an alarm from 'Out Of Service' state back to normal operation.
        """
        result = dict()
        alarm = app.alarm_manager.get_alarm_by_name(alarm_name)

        if alarm:

            if alarm.state in [AlarmState.OOSRV]:
                user = Api.get_current_user()
                alarm.return_to_service(user=user)
                result['message'] = f"{alarm.name} was returned to service successfully"
                result['data'] = alarm.serialize()

                return result, 200

            return {'message': f"You cannot returned to service an alarm if not in out of service state"}, 400

        return {'message': f"Alarm Name {alarm_name} does not exist"}, 400


@ns.route('/add')
class AddAlarmResource(Resource):

    @api.doc(security='apikey', description="Creates a new alarm in the system.")
    @api.response(200, "Alarm created successfully")
    @api.response(400, "Alarm creation failed")
    @Api.token_required(auth=True)
    @ns.expect(create_alarm_model)
    def post(self):
        """
        Create alarm.

        Creates a new alarm in the automation application with the specified configuration.
        """
        payload = api.payload
        
        # Required fields
        name = payload.get('name')
        tag = payload.get('tag')
        
        if not name or not tag:
            return {
                'message': 'Missing required fields: name and tag are required'
            }, 400
        
        # Validate that tag exists
        tag_obj = app.get_tag_by_name(name=tag)
        if not tag_obj:
            return {
                'message': f'Tag "{tag}" does not exist'
            }, 400
        
        try:
            alarm, message = app.create_alarm(
                name=name,
                tag=tag,
                alarm_type=payload.get('alarm_type', 'BOOL'),
                trigger_value=payload.get('trigger_value', True),
                description=payload.get('description', '')
            )
            
            if alarm:
                return {
                    'message': f"Alarm '{name}' created successfully",
                    'alarm': {
                        'id': alarm.identifier,
                        'name': alarm.name,
                        'tag': alarm.tag.name if hasattr(alarm.tag, 'name') else str(alarm.tag),
                        'alarm_type': alarm.alarm_setpoint.type.value if hasattr(alarm.alarm_setpoint.type, 'value') else str(alarm.alarm_setpoint.type),
                        'trigger_value': alarm.alarm_setpoint.value
                    }
                }, 200
            else:
                return {
                    'message': f"Failed to create alarm: {message}"
                }, 400
        except Exception as e:
            return {
                'message': f"Error creating alarm: {str(e)}"
            }, 400


@ns.route('/update')
class UpdateAlarmResource(Resource):

    @api.doc(security='apikey', description="Updates an existing alarm configuration.")
    @api.response(200, "Alarm updated successfully")
    @api.response(400, "Alarm update failed")
    @api.response(404, "Alarm not found")
    @Api.token_required(auth=True)
    @ns.expect(update_alarm_model)
    def post(self):
        """
        Update alarm.

        Updates the configuration of an existing alarm. Only provided fields will be updated.
        """
        payload = api.payload
        
        # Required field
        alarm_id = payload.get('id')
        if not alarm_id:
            return {
                'message': 'Alarm ID is required'
            }, 400
        
        # Check if alarm exists
        alarm = app.get_alarm(id=alarm_id)
        if not alarm:
            return {
                'message': f'Alarm with ID {alarm_id} not found'
            }, 404
        
        # Build kwargs with only provided fields (excluding 'id')
        update_kwargs = {k: v for k, v in payload.items() if k != 'id' and v is not None}
        
        # Map 'alarm_type' to 'type' if needed, or use 'alarm_type' directly
        if 'alarm_type' in update_kwargs:
            update_kwargs['alarm_type'] = update_kwargs['alarm_type']
        
        if not update_kwargs:
            return {
                'message': 'No fields to update provided'
            }, 400
        
        # Validate tag if provided
        if 'tag' in update_kwargs:
            tag_obj = app.get_tag_by_name(name=update_kwargs['tag'])
            if not tag_obj:
                return {
                    'message': f'Tag "{update_kwargs["tag"]}" does not exist'
                }, 400
        
        try:
            app.update_alarm(
                id=alarm_id,
                name=update_kwargs.get('name'),
                tag=update_kwargs.get('tag'),
                description=update_kwargs.get('description'),
                alarm_type=update_kwargs.get('alarm_type'),
                trigger_value=update_kwargs.get('trigger_value')
            )
            
            # Get updated alarm
            updated_alarm = app.get_alarm(id=alarm_id)
            if updated_alarm:
                return {
                    'message': f"Alarm '{updated_alarm.name}' updated successfully",
                    'alarm': {
                        'id': updated_alarm.identifier,
                        'name': updated_alarm.name
                    }
                }, 200
            else:
                return {
                    'message': 'Alarm was updated but could not be retrieved'
                }, 200
        except Exception as e:
            return {
                'message': f"Error updating alarm: {str(e)}"
            }, 400


@ns.route('/delete/<alarm_id>')
@api.param('alarm_id', 'The alarm ID to delete')
class DeleteAlarmResource(Resource):

    @api.doc(security='apikey', description="Deletes an alarm from the system by ID.")
    @api.response(200, "Alarm deleted successfully")
    @api.response(404, "Alarm not found")
    @Api.token_required(auth=True)
    def delete(self, alarm_id):
        """
        Delete alarm.

        Deletes an alarm from the system by its ID.
        """
        # Check if alarm exists
        alarm = app.get_alarm(id=alarm_id)
        if not alarm:
            return {
                'message': f'Alarm with ID {alarm_id} not found'
            }, 404
        
        try:
            app.delete_alarm(id=alarm_id)
            return {
                'message': f'Alarm "{alarm.name}" deleted successfully'
            }, 200
        except Exception as e:
            return {
                'message': f"Error deleting alarm: {str(e)}"
            }, 400
