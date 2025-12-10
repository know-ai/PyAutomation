import pytz
from datetime import datetime, timedelta
from flask_restx import Namespace, Resource, fields
from .... import PyAutomation
from ....extensions.api import api
from ....extensions import _api as Api
from ....dbmodels.alarms import AlarmSummary
from .... import _TIMEZONE, TIMEZONE

ns = Namespace('Alarms Summary', description='Historical Alarm Data')
app = PyAutomation()

alarms_summary_filter_model = api.model("alarms_summary_filter_model",{
    'names': fields.List(fields.String(), required=False, description='List of alarm names to filter by'),
    'states': fields.List(fields.String(), required=False, description='List of alarm states to filter by'),
    'tags': fields.List(fields.String(), required=False, description='List of tags to filter by'),
    'greater_than_timestamp': fields.DateTime(required=False, default=datetime.now(pytz.utc).astimezone(TIMEZONE) - timedelta(minutes=30), description=f'Start time for filtering - DateTime Format: {app.cvt.DATETIME_FORMAT}'),
    'less_than_timestamp': fields.DateTime(required=False, default=datetime.now(pytz.utc).astimezone(TIMEZONE), description=f'End time for filtering - DateTime Format: {app.cvt.DATETIME_FORMAT}'),
    'timezone': fields.String(required=False, default=_TIMEZONE, description='Timezone for the query'),
    'page': fields.Integer(required=False, default=1, description='Page number for pagination'),
    'limit': fields.Integer(required=False, default=20, description='Items per page')
})

    
@ns.route('/filter_by')
class AlarmsSummaryFilterByResource(Resource):

    @api.doc(security='apikey', description="Filters historical alarm data.")
    @api.response(200, "Success")
    @api.response(400, "Invalid parameters")
    @Api.token_required(auth=True)
    @ns.expect(alarms_summary_filter_model)
    def post(self):
        r"""
        Filter alarm history.

        Retrieves a list of historical alarm events based on the provided filter criteria.
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
@api.param('lasts', 'Number of records to retrieve')
class LastsAlarmsResource(Resource):

    @api.doc(security='apikey', description="Retrieves the last N alarm events.")
    @api.response(200, "Success")
    @Api.token_required(auth=True)
    def get(self, lasts:int=10):
        r"""
        Get latest alarm events.

        Retrieves the most recent alarm events from the history.
        """

        return app.get_lasts_alarms(lasts=int(lasts))
    

@ns.route('/<id>/comments')
@api.param('id', 'Alarm Summary ID')
class AlarmsSummaryCommentsResource(Resource):

    @api.doc(security='apikey', description="Retrieves comments for a specific alarm event.")
    @api.response(200, "Success")
    @Api.token_required(auth=True)
    def get(self, id:int):
        r"""
        Get alarm event comments.

        Retrieves user comments associated with a specific alarm history record.
        """
        comments = AlarmSummary.get_alarm_summary_comments(id=id)
        return comments, 200
