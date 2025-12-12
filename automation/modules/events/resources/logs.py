import pytz
from datetime import datetime, timedelta
from flask_restx import Namespace, Resource, fields
from .... import PyAutomation
from ....extensions.api import api
from ....extensions import _api as Api
from .... import _TIMEZONE, TIMEZONE

ns = Namespace('Operation Logs', description='Application Operation Logs')
app = PyAutomation()


logs_filter_model = api.model("logs_filter_model",{
    'usernames': fields.List(fields.String(), required=False, description='List of usernames to filter by'),
    'alarm_names': fields.List(fields.String(), required=False, description='List of associated alarm names'),
    'event_ids': fields.List(fields.Integer(), required=False, description='List of associated event IDs'),
    'classification': fields.String(required=False, description='Log classification'),
    'message': fields.String(required=False, description='Partial message content'),
    'description': fields.String(required=False, description='Partial description content'),
    'greater_than_timestamp': fields.DateTime(required=False, default=datetime.now(pytz.utc).astimezone(TIMEZONE) - timedelta(minutes=30), description=f'Start time for filtering - DateTime Format: {app.cvt.DATETIME_FORMAT}'),
    'less_than_timestamp': fields.DateTime(required=False, default=datetime.now(pytz.utc).astimezone(TIMEZONE), description=f'End time for filtering - DateTime Format: {app.cvt.DATETIME_FORMAT}',),
    'timezone': fields.String(required=False, default=_TIMEZONE, description='Timezone for the query'),
    'page': fields.Integer(required=False, default=1, description='Page number for pagination'),
    'limit': fields.Integer(required=False, default=20, description='Items per page')
})

logs_model = api.model("logs_model",{
    'message': fields.String(required=True, description="Main log message"),
    'alarm_summary_id': fields.Integer(required=False, description="ID of the associated alarm summary (optional)"),
    'event_id': fields.Integer(required=False, description="ID of the associated event (optional)"),
    'description': fields.String(required=False, description="Detailed description of the log entry")
})

@ns.route('/add')
class AddLogsByResource(Resource):

    @api.doc(security='apikey', description="Creates a new operation log entry.")
    @api.response(200, "Success")
    @api.response(400, "Creation failed")
    @Api.token_required(auth=True)
    @ns.expect(logs_model)
    def post(self):
        r"""
        Create Log.

        Adds a new entry to the operation logs. Can be linked to an alarm or event.
        """
        user = Api.get_current_user()
        api.payload.update({
            "user": user
        })
        if "event_id" in api.payload:
            api.payload.update({
                "classification": "Event"
            })
        elif "alarm_summary_id" in api.payload:
            api.payload.update({
                "classification": "Alarm"
            })
        else:
            api.payload.update({
                "classification": "General"
            })

        log, message = app.create_log(**api.payload)
        if log:
            
            return log.serialize(), 200
        
        return message, 400

    
@ns.route('/filter_by')
class LogsFilterByResource(Resource):

    @api.doc(security='apikey', description="Filters operation logs based on criteria.")
    @api.response(200, "Success")
    @api.response(400, "Invalid parameters")
    @Api.token_required(auth=True)
    @ns.expect(logs_filter_model)
    def post(self):
        r"""
        Filter Logs.

        Retrieves operation logs matching the specified filter criteria.
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
        return app.filter_logs_by(**api.payload), 200
    

@ns.route('/lasts/<lasts>')
@api.param('lasts', 'Number of records to retrieve')
class LastsEventsResource(Resource):

    @api.doc(security='apikey', description="Retrieves the last N operation logs.")
    @api.response(200, "Success")
    @Api.token_required(auth=True)
    def get(self, lasts:int=10):
        r"""
        Get latest logs.

        Retrieves the most recent operation logs.
        """
        
        return app.get_lasts_logs(lasts=int(lasts)), 200
