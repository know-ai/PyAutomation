from flask_restx import Namespace, Resource, fields
from .... import PyAutomation
from automation.alarms import AlarmState
from ....extensions.api import api
from ....extensions import _api as Api


ns = Namespace('Alarms', description='Alarms')
app = PyAutomation()

alarm_resource_by_name_model = api.model("alarm_resource_by_name_model",{
    'alarm_name': fields.String(required=True, description='Alarm Name')
})

shelve_alarm_resource_by_name_model = api.model("shelve_alarm_resource_by_name_model",{
    'alarm_name': fields.String(required=True, description='Alarm Name'),
    'seconds': fields.Integer(required=False, description='Shelve time'),
    'minutes': fields.Integer(required=False, description='Shelve time'),
    'hours': fields.Integer(required=False, description='Shelve time'),
    'days': fields.Integer(required=False, description='Shelve time'),
    'weeks': fields.Integer(required=False, description='Shelve time')
})

append_alarm_resource_model = api.model("append_alarm_resource_model",{
    'name': fields.String(required=True, description='Alarm Name'),
    'tag': fields.String(required=True, description='Tag to whom the alarm will be subscribed'),
    'description': fields.String(required=False, description='Alarm description'),
    'type': fields.String(required=True, description='Alarm Type - Allowed ["HIGH-HIGH", "HIGH", "BOOL", "LOW", "LOW-LOW"]'),
    'trigger_value': fields.Float(required=True, description="Alarm trigger value")
})


@ns.route('/')
class AlarmsCollection(Resource):

    @api.doc(security='apikey')
    @Api.token_required(auth=True)
    def get(self):
        """
        Get Alarms
        """
        return app.alarm_manager.serialize(), 200
    
@ns.route('/actions/<alarm_name>')
class AlarmsActionsCollection(Resource):

    @api.doc(security='apikey')
    @Api.token_required(auth=True)
    def get(self, alarm_name:str):
        """
        Get allowed actions
        """
        alarm = app.alarm_manager.get_alarm_by_name(name=alarm_name)
        if alarm:

            return alarm.get_operator_actions(), 200
        
        return {'message': f"Alarm Name {alarm_name} is not exist"}, 400
    
@ns.route('/add')
class CreateAlarmResource(Resource):

    @api.doc(security='apikey')
    @Api.token_required(auth=True)
    @ns.expect(append_alarm_resource_model)
    def post(self):
        """
        Create Alarm
        """
        user = Api.get_current_user()
        alarm_name = api.payload["name"]
        message = app.create_alarm(user=user, **api.payload)

        if message:

            return app.create_alarm(user=user, **api.payload), 400
        
        alarm = app.get_alarm_by_name(name=alarm_name)

        return alarm.serialize(), 200
    
@ns.route('/<id>')
class AlarmResource(Resource):

    @api.doc(security='apikey')
    @Api.token_required(auth=True)
    def get(self, id):
        """
        Gets alarm by alarm id
        """
        alarm = app.get_alarm(id)

        if alarm:
        
            return alarm.serialize(), 200

        return {'message': f"Alarm ID {id} is not exist"}, 400
    

@ns.route('/name/<alarm_name>')
class AlarmByNameResource(Resource):

    @api.doc(security='apikey')
    @Api.token_required(auth=True)
    def get(self, alarm_name):
        """
        Get alarm info
        """
        alarm = app.alarm_manager.get_alarm_by_name(alarm_name)

        if alarm:

            return alarm.serialize(), 200 
        
        return {'message': f"Alarm Name {alarm_name} is not exist"}, 400
    
    
@ns.route('/acknowledge/<alarm_name>')
class AckAlarmByNameResource(Resource):
    
    @api.doc(security='apikey')
    @Api.token_required(auth=True)
    def post(self, alarm_name:str):
        """
        Acknowledge alarm
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

        return {'message': f"Alarm Name {alarm_name} is not exist"}, 400

    
@ns.route('/acknowledge_all')
class AckAllAlarmsResource(Resource):

    @api.doc(security='apikey')
    @Api.token_required(auth=True)
    def post(self):
        """
        Acknowledge all alarms triggered
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
class SuppressByDesignAlarmByNameResource(Resource):
    
    @api.doc(security='apikey')
    @Api.token_required(auth=True)
    def post(self, alarm_name:str):
        """
        Suppressed by design alarm
        """
        result = dict()
        alarm = app.alarm_manager.get_alarm_by_name(alarm_name)

        if alarm:
            user = Api.get_current_user()
            alarm.designed_suppression(user=user)
            result['message'] = f"{alarm.name} was suppressed by design successfully"
            result['data'] = alarm.serialize()

            return result, 200

        return {'message': f"Alarm Name {alarm_name} is not exist"}, 400


@ns.route('/designed_unsuppression/<alarm_name>')
class DesignedUnsuppressionAlarmByNameResource(Resource):
    
    @api.doc(security='apikey')
    @Api.token_required(auth=True)
    def post(self, alarm_name:str):
        """
        Unsuppress by design alarm
        """
        result = dict()
        alarm = app.alarm_manager.get_alarm_by_name(alarm_name)

        if alarm:

            if alarm.state in [AlarmState.DSUPR]:
                user = Api.get_current_user()
                alarm.designed_unsuppression(user=user)
                result['message'] = f"{alarm.name} was suppressed by design successfully"
                result['data'] = alarm.serialize()

                return result, 200

            return {'message': f"You cannot unsuppress by design an alarm if not in suppress state"}, 400

        return {'message': f"Alarm Name {alarm_name} is not exist"}, 400


@ns.route('/remove_from_service/<alarm_name>')
class OutOfServiceAlarmByNameResource(Resource):
    
    @api.doc(security='apikey')
    @Api.token_required(auth=True)
    def post(self, alarm_name:str):
        """
        Out Of Service alarm
        """
        result = dict()
        alarm = app.alarm_manager.get_alarm_by_name(alarm_name)

        if alarm:
            user = Api.get_current_user()
            alarm.remove_from_service(user=user)
            result['message'] = f"{alarm.name} was pusshed in out of service successfully"
            result['data'] = alarm.serialize()

            return result, 200

        return {'message': f"Alarm Name {alarm_name} is not exist"}, 400


@ns.route('/shelve/<alarm_name>')
class ShelveAlarmByNameResource(Resource):
    
    @api.doc(security='apikey')
    @Api.token_required(auth=True)
    @ns.expect(shelve_alarm_resource_by_name_model)
    def post(self, alarm_name:str):
        """
        Shelve alarm
        """
        result = dict()
        alarm = app.alarm_manager.get_alarm_by_name(alarm_name)
        seconds = minutes = hours = days = weeks = 0

        if "seconds" in api.payload:

            seconds = api.payload['seconds']

        if "minutes" in api.payload:

            minutes = api.payload['minutes']

        if "hours" in api.payload:

            hours = api.payload['hours']

        if "days" in api.payload:

            days = api.payload['days']

        if "weeks" in api.payload:

            weeks = api.payload['weeks']

        if alarm:
            user = Api.get_current_user()
            alarm.shelve(
                user=user,
                seconds=seconds,
                minutes=minutes,
                hours=hours,
                days=days,
                weeks=weeks
            )
            result['message'] = f"{alarm.name} was shelved successfully"
            result['data'] = alarm.serialize()

            return result, 200

        return {'message': f"Alarm Name {alarm_name} is not exist"}, 400


@ns.route('/return_to_service/<alarm_name>')
class ReturnToServiceAlarmByNameResource(Resource):
    
    @api.doc(security='apikey')
    @Api.token_required(auth=True)
    def post(self, alarm_name:str):
        """
        Return to service alarm
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

        return {'message': f"Alarm Name {alarm_name} is not exist"}, 400

