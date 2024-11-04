import pytz
from datetime import datetime, timedelta
from flask_restx import Namespace, Resource, fields
from .... import PyAutomation
from ....extensions.api import api
from ....extensions import _api as Api
from ....dbmodels.alarms import AlarmSummary
from .... import _TIMEZONE, TIMEZONE

ns = Namespace('Alarms Summary', description='Alarms Summary')
app = PyAutomation()

alarms_summary_filter_model = api.model("alarms_summary_filter_model",{
    'names': fields.List(fields.String(), required=False),
    'states': fields.List(fields.String(), required=False),
    'tags': fields.List(fields.String(), required=False),
    'greater_than_timestamp': fields.DateTime(required=False, default=datetime.now(pytz.utc).astimezone(TIMEZONE) - timedelta(minutes=30), description=f'Greater than timestamp - DateTime Format: {app.cvt.DATETIME_FORMAT}'),
    'less_than_timestamp': fields.DateTime(required=False, default=datetime.now(pytz.utc).astimezone(TIMEZONE), description=f'Less than timestamp - DateTime Format: {app.cvt.DATETIME_FORMAT}'),
    'timezone': fields.String(required=False, default=_TIMEZONE)
})

    
@ns.route('/filter_by')
class AlarmsSummarygFilterByResource(Resource):

    @api.doc(security='apikey')
    @Api.token_required(auth=True)
    @ns.expect(alarms_summary_filter_model)
    def post(self):
        r"""
        Alarms Summary Filter By
        """
        timezone = _TIMEZONE
        if "timezone" in api.payload:

            timezone = api.payload["timezone"]

        if timezone not in pytz.all_timezones:

            return f"Invalid Timezone", 400

        separator = '.'
        if 'greater_than_timestamp' in api.payload:
            
            greater_than_timestamp = api.payload['greater_than_timestamp']
            api.payload['greater_than_timestamp'] = greater_than_timestamp.replace("T", " ").split(separator, 1)[0] + '.00'
        
        if "less_than_timestamp" in api.payload:

            less_than_timestamp = api.payload['less_than_timestamp']
            api.payload['less_than_timestamp'] = less_than_timestamp.replace("T", " ").split(separator, 1)[0] + '.00'
                
        return app.filter_alarms_by(**api.payload)
    

@ns.route('/lasts/<lasts>')
class LastsAlarmsResource(Resource):

    @api.doc(security='apikey')
    @Api.token_required(auth=True)
    def get(self, lasts:int=10):
        r"""
        Get lasts alarms
        """

        return app.get_lasts_alarms(lasts=int(lasts))
    

@ns.route('/<id>/comments')
class AlarmsSummaryCommentsResource(Resource):

    @api.doc(security='apikey')
    @Api.token_required(auth=True)
    def get(self, id:int):
        r"""
        Get Alarm Summary Comments
        """
        comments = AlarmSummary.get_alarm_summary_comments(id=id)
        return comments, 200
