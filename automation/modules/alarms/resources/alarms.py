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
        Gets all alarm names defined
        """
        alarm = app.alarm_manager.get_alarm_by_name(alarm_name)

        if alarm:

            return alarm.serialize(), 200 
        
        return {'message': f"Alarm Name {alarm_name} is not exist"}, 400
    
    
@ns.route('/name/acknowledge')
class AckAlarmByNameResource(Resource):
    
    @api.doc(security='apikey')
    @Api.token_required(auth=True)
    @ns.expect(alarm_resource_by_name_model)
    def post(self):
        """
        Acknowledge alarm
        """
        result = dict()
        alarm_name = api.payload['alarm_name']
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
    

@ns.route('/silence_all')
class SilenceAllAlarmsResource(Resource):

    @api.doc(security='apikey')
    @Api.token_required(auth=True)
    def post(self):
        """
        Silence all alarms triggered
        """
        alarms = app.alarm_manager.get_alarms()
        result = {
            'message': "None"
        }

        for id, alarm in alarms.items():

            if alarm.audible:
                user = Api.get_current_user()
                alarm.silence(user=user)
        
                result = {
                    'message': "Alarms were silenced successfully"
                }
        
        return result, 200
    

@ns.route('/name/enable')
class EnableAlarmByNameResource(Resource):
    
    @api.doc(security='apikey')
    @Api.token_required(auth=True)
    @ns.expect(alarm_resource_by_name_model)
    def post(self):
        """
        Enable alarm
        """
        result = dict()
        alarm_name = api.payload['alarm_name']
        alarm = app.alarm_manager.get_alarm_by_name(alarm_name)

        if alarm:
            user = Api.get_current_user()
            alarm.enable(user=user)
            result['message'] = f"{alarm.name} was enabled successfully"
            result['data'] = alarm.serialize()

            return result, 200

        return {'message': f"Alarm Name {alarm_name} is not exist"}, 400


@ns.route('/name/disable')
class DisableAlarmByNameResource(Resource):
    
    @api.doc(security='apikey')
    @Api.token_required(auth=True)
    @ns.expect(alarm_resource_by_name_model)
    def post(self):
        """
        Disable alarm
        """
        result = dict()
        alarm_name = api.payload['alarm_name']
        alarm = app.alarm_manager.get_alarm_by_name(alarm_name)

        if alarm:

            if alarm.state in [AlarmState.NORM]:
                user = Api.get_current_user()
                alarm.disable(user=user)
                result['message'] = f"{alarm.name} was disabled successfully"
                result['data'] = alarm.serialize()

                return result, 200

            return {'message': f"You cannot disable an alarm if not in Normal state"}, 400

        return {'message': f"Alarm Name {alarm_name} is not exist"}, 400


@ns.route('/name/suppress_by_design')
class SuppressByDesignAlarmByNameResource(Resource):
    
    @api.doc(security='apikey')
    @Api.token_required(auth=True)
    @ns.expect(alarm_resource_by_name_model)
    def post(self):
        """
        Suppressed by design alarm
        """
        result = dict()
        alarm_name = api.payload['alarm_name']
        alarm = app.alarm_manager.get_alarm_by_name(alarm_name)

        if alarm:
            user = Api.get_current_user()
            alarm.suppress_by_design(user=user)
            result['message'] = f"{alarm.name} was suppressed by design successfully"
            result['data'] = alarm.serialize()

            return result, 200

        return {'message': f"Alarm Name {alarm_name} is not exist"}, 400


@ns.route('/name/unsuppress_by_design')
class UnsuppressByDesignAlarmByNameResource(Resource):
    
    @api.doc(security='apikey')
    @Api.token_required(auth=True)
    @ns.expect(alarm_resource_by_name_model)
    def post(self):
        """
        Unsuppress by design alarm
        """
        result = dict()
        alarm_name = api.payload['alarm_name']
        alarm = app.alarm_manager.get_alarm_by_name(alarm_name)

        if alarm:

            if alarm.state in [AlarmState.DSUPR]:
                user = Api.get_current_user()
                alarm.unsuppress_by_design(user=user)
                result['message'] = f"{alarm.name} was suppressed by design successfully"
                result['data'] = alarm.serialize()

                return result, 200

            return {'message': f"You cannot unsuppress by design an alarm if not in suppress state"}, 400

        return {'message': f"Alarm Name {alarm_name} is not exist"}, 400


@ns.route('/name/out_of_service')
class OutOfServiceAlarmByNameResource(Resource):
    
    @api.doc(security='apikey')
    @Api.token_required(auth=True)
    @ns.expect(alarm_resource_by_name_model)
    def post(self):
        """
        Out Of Service alarm
        """
        result = dict()
        alarm_name = api.payload['alarm_name']
        alarm = app.alarm_manager.get_alarm_by_name(alarm_name)

        if alarm:
            user = Api.get_current_user()
            alarm.out_of_service(user=user)
            result['message'] = f"{alarm.name} was pusshed in out of service successfully"
            result['data'] = alarm.serialize()

            return result, 200

        return {'message': f"Alarm Name {alarm_name} is not exist"}, 400


@ns.route('/name/shelve')
class ShelveAlarmByNameResource(Resource):
    
    @api.doc(security='apikey')
    @Api.token_required(auth=True)
    @ns.expect(shelve_alarm_resource_by_name_model)
    def post(self):
        """
        Shelve alarm
        """
        result = dict()
        alarm_name = api.payload['alarm_name']
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


@ns.route('/name/return_to_service')
class ReturnToServiceAlarmByNameResource(Resource):
    
    @api.doc(security='apikey')
    @Api.token_required(auth=True)
    @ns.expect(alarm_resource_by_name_model)
    def post(self):
        """
        Return to service alarm
        """
        result = dict()
        alarm_name = api.payload['alarm_name']
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


@ns.route('/name/silence')
class SilenceAlarmByNameResource(Resource):
    
    @api.doc(security='apikey')
    @Api.token_required(auth=True)
    @ns.expect(alarm_resource_by_name_model)
    def post(self):
        """
        Silence alarm
        """
        result = dict()
        alarm_name = api.payload['alarm_name']
        alarm = app.alarm_manager.get_alarm_by_name(alarm_name)
        if alarm:

            if alarm.audible:
                user = Api.get_current_user()
                alarm.silence(user=user)
                result['message'] = f"{alarm.name} was silenced successfully"
                result['data'] = alarm.serialize()

                return result, 200

            return {'message': f"Alarm Name {alarm_name} is not sound"}, 400

        return {'message': f"Alarm Name {alarm_name} is not exist"}, 400


@ns.route('/name/sound')
class SoundAlarmByNameResource(Resource):
    
    @api.doc(security='apikey')
    @Api.token_required(auth=True)
    @ns.expect(alarm_resource_by_name_model)
    def post(self):
        """
        Sound alarm
        """
        result = dict()
        alarm_name = api.payload['alarm_name']
        alarm = app.alarm_manager.get_alarm_by_name(alarm_name)

        if alarm:

            if not alarm.audible:
                user = Api.get_current_user()
                alarm.sound(user=user)
                result['message'] = f"{alarm.name} was returned to audible successfully"
                result['data'] = alarm.serialize()

                return result, 200 

            return {'message': f"Alarm Name {alarm_name} is sound"}, 400

        return {'message': f"Alarm Name {alarm_name} is not exist"}, 400
