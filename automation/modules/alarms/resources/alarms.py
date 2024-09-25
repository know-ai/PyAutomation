from flask_restx import Namespace, Resource, fields
from automation import PyAutomation
from automation.alarms import AlarmState
from automation.extensions.api import api


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


@ns.route('/')
class AlarmsCollection(Resource):

    def get(self):
        """
        Get Alarms
        """
        return app.alarm_manager.serialize(), 200
    
@ns.route('/<id>')
class AlarmResource(Resource):

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

                alarm.acknowledge()
                result['message'] = f"{alarm.name} was acknowledged successfully"
                result['data'] = alarm.serialize()

                return result, 200

            return {'message': f"Alarm Name {alarm_name} is not in Unacknowledged state"}, 400

        return {'message': f"Alarm Name {alarm_name} is not exist"}, 400

    
@ns.route('/acknowledge_all')
class AckAllAlarmsResource(Resource):

    def post(self):
        """
        Acknowledge all alarms triggered
        """
        alarms = app.alarm_manager.get_alarms()

        for id, alarm in alarms.items():

            if not alarm._is_process_alarm:

                if alarm.state in [AlarmState.UNACK, AlarmState.RTNUN]:

                    alarm.acknowledge()
        
        result = {
            'message': "Alarms were acknowledged successfully"
        }
        
        return result, 200
    

@ns.route('/silence_all')
class SilenceAllAlarmsResource(Resource):

    def post(self):
        """
        Silence all alarms triggered
        """
        alarms = app.alarm_manager.get_alarms()
        result = {
            'message': "None"
        }

        for id, alarm in alarms.items():

            if not alarm._is_process_alarm:

                if alarm.audible:
                    
                    alarm.silence()
            
                    result = {
                        'message': "Alarms were silenced successfully"
                    }
        
        return result, 200
    

@ns.route('/name/enable')
class EnableAlarmByNameResource(Resource):
    
    @ns.expect(alarm_resource_by_name_model)
    def post(self):
        """
        Enable alarm
        """
        result = dict()
        alarm_name = api.payload['alarm_name']
        alarm = app.alarm_manager.get_alarm_by_name(alarm_name)

        if alarm:

            alarm.enable()
            result['message'] = f"{alarm.name} was enabled successfully"
            result['data'] = alarm.serialize()

            return result, 200

        return {'message': f"Alarm Name {alarm_name} is not exist"}, 400


@ns.route('/name/disable')
class DisableAlarmByNameResource(Resource):
    
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
                alarm.disable()
                result['message'] = f"{alarm.name} was disabled successfully"
                result['data'] = alarm.serialize()

                return result, 200

            return {'message': f"You cannot disable an alarm if not in Normal state"}, 400

        return {'message': f"Alarm Name {alarm_name} is not exist"}, 400


@ns.route('/name/suppress_by_design')
class SuppressByDesignAlarmByNameResource(Resource):
    
    @ns.expect(alarm_resource_by_name_model)
    def post(self):
        """
        Suppressed by design alarm
        """
        result = dict()
        alarm_name = api.payload['alarm_name']
        alarm = app.alarm_manager.get_alarm_by_name(alarm_name)

        if alarm:

            alarm.suppress_by_design()
            result['message'] = f"{alarm.name} was suppressed by design successfully"
            result['data'] = alarm.serialize()

            return result, 200

        return {'message': f"Alarm Name {alarm_name} is not exist"}, 400


@ns.route('/name/unsuppress_by_design')
class UnsuppressByDesignAlarmByNameResource(Resource):
    
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
                alarm.unsuppress_by_design()
                result['message'] = f"{alarm.name} was suppressed by design successfully"
                result['data'] = alarm.serialize()

                return result, 200

            return {'message': f"You cannot unsuppress by design an alarm if not in suppress state"}, 400

        return {'message': f"Alarm Name {alarm_name} is not exist"}, 400


@ns.route('/name/out_of_service')
class OutOfServiceAlarmByNameResource(Resource):
    
    @ns.expect(alarm_resource_by_name_model)
    def post(self):
        """
        Out Of Service alarm
        """
        result = dict()
        alarm_name = api.payload['alarm_name']
        alarm = app.alarm_manager.get_alarm_by_name(alarm_name)

        if alarm:

            alarm.out_of_service()
            result['message'] = f"{alarm.name} was pusshed in out of service successfully"
            result['data'] = alarm.serialize()

            return result, 200

        return {'message': f"Alarm Name {alarm_name} is not exist"}, 400


@ns.route('/name/shelve')
class ShelveAlarmByNameResource(Resource):
    
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

            alarm.shelve(
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
                alarm.return_to_service()
                result['message'] = f"{alarm.name} was returned to service successfully"
                result['data'] = alarm.serialize()

                return result, 200

            return {'message': f"You cannot returned to service an alarm if not in out of service state"}, 400

        return {'message': f"Alarm Name {alarm_name} is not exist"}, 400


@ns.route('/name/silence')
class SilenceAlarmByNameResource(Resource):
    
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
                alarm.silence()
                result['message'] = f"{alarm.name} was silenced successfully"
                result['data'] = alarm.serialize()

                return result, 200

            return {'message': f"Alarm Name {alarm_name} is not sound"}, 400

        return {'message': f"Alarm Name {alarm_name} is not exist"}, 400


@ns.route('/name/sound')
class SoundAlarmByNameResource(Resource):
    
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
                alarm.sound()
                result['message'] = f"{alarm.name} was returned to audible successfully"
                result['data'] = alarm.serialize()

                return result, 200 

            return {'message': f"Alarm Name {alarm_name} is sound"}, 400

        return {'message': f"Alarm Name {alarm_name} is not exist"}, 400
