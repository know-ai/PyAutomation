from flask_restx import Namespace, Resource, fields
from automation import PyAutomation
from automation.dbmodels import AlarmSummary, AlarmStates, Alarms
from automation.extensions.api import api
import logging
from datetime import datetime, timedelta
DATETIME_FORMAT = "%m/%d/%Y, %H:%M:%S.%f"

ns = Namespace('Alarms Summary', description='Alarms Summary')
app = PyAutomation()

alarms_summary_filter_model = api.model("alarms_summary_filter_model",{
    'name': fields.String(required=False, description='Alarm name'),
    'state': fields.String(required=False, description='Alarm state ["Normal", "Unacknowledged", "Acknowledged", "RTN Unacknowledged", "Shelved", "Suppressed By Design", "Out Of Service"]'),
    'greater_than_timestamp': fields.DateTime(required=False, default=datetime.now() - timedelta(minutes=2), description=f'Greater than timestamp - DateTime Format: {DATETIME_FORMAT}'),
    'less_than_timestamp': fields.DateTime(required=False, default=datetime.now(), description=f'Less than timestamp - DateTime Format: {DATETIME_FORMAT}')
})


@ns.route('/')
class AlarmsSummaryCollection(Resource):

    def get(self):
        """
        Get Alarms Summary
        """
        return AlarmSummary.read_all(), 200
    
@ns.route('/filter_by')
class AlarmsSummarygFilterByResource(Resource):

    @ns.expect(alarms_summary_filter_model)
    def post(self):
        r"""
        Alarms Summary Filter By
        """
        payload = api.payload
        
        _query = ''

        # State
        if 'state' in payload.keys():
            
            state = payload["state"]
            _state = AlarmStates.read_by_name(state)

            if _state:

                state_id = [_state.id]

                if _query:
                
                    _query += ' & ' + f'AlarmSummary.state_id.in_({state_id})'

                else:

                    _query = f'AlarmSummary.state_id.in_({state_id})'

            else:
            
                return {'message': f'State {state} not exist'}, 400

        if 'name' in payload.keys():
            
            name = payload["name"]
            
            _alarm = Alarms.read_by_name(name)
            
            if _alarm:
                
                alarm_id = [_alarm.id]

                if _query:

                    _query += ' & ' + f'AlarmSummary.alarm_id.in_({alarm_id})'

                else:
                    
                    _query = f'AlarmSummary.alarm_id.in_({alarm_id})'

            else:

                return {'message': f'Alarm {name} not exist'}, 400

        try:

            separator = '.'
            # GREATER THAN TIMESTAMP
            if 'greater_than_timestamp' in payload.keys():

                greater_than_timestamp = payload.pop('greater_than_timestamp')
                greater_than_timestamp = datetime.strptime(greater_than_timestamp.replace("T", " ").split(separator, 1)[0], DATETIME_FORMAT)

                if _query:

                    _query += ' & ' + f'(AlarmSummary.alarm_time >= greater_than_timestamp)'

                else:

                    _query = f'(AlarmSummary.alarm_time >= greater_than_timestamp)'

            # LESS THAN TIMESTAMP
            if 'less_than_timestamp' in payload.keys():

                less_than_timestamp = payload.pop('less_than_timestamp')
                less_than_timestamp = datetime.strptime(less_than_timestamp.replace("T", " ").split(separator, 1)[0], DATETIME_FORMAT)
                
                if _query:

                    _query += ' & ' + f'(AlarmSummary.alarm_time <= less_than_timestamp)'

                else:
                
                    _query = f'(AlarmSummary.alarm_time <= less_than_timestamp)'


            if _query:
               
                alarms = AlarmSummary.select().where(eval(_query)).order_by(AlarmSummary.id.desc())

            else: 

                return {'message': f"Please provide a valid key"}, 400

            result = [alarm.serialize() for alarm in alarms]

            return result, 200

        except Exception as ex:

            trace = []
            tb = ex.__traceback__
            while tb is not None:
                trace.append({
                    "filename": tb.tb_frame.f_code.co_filename,
                    "name": tb.tb_frame.f_code.co_name,
                    "lineno": tb.tb_lineno
                })
                tb = tb.tb_next
            msg = str({
                'type': type(ex).__name__,
                'message': str(ex),
                'trace': trace
            })
            logging.warning(msg=msg)
            return {'message': msg}, 400