import pytz
from datetime import datetime, timedelta
from flask_restx import Namespace, Resource, fields
from .... import PyAutomation
from ....extensions.api import api
from ....extensions import _api as Api
from ....dbmodels.events import Events
from .... import _TIMEZONE, TIMEZONE

ns = Namespace('Events Logger', description='System Event Logging and Retrieval')
app = PyAutomation()


events_filter_model = api.model("events_filter_model",{
    'usernames': fields.List(fields.String(), required=False, description='List of usernames to filter by'),
    'priorities': fields.List(fields.Integer(), required=False, description='List of priority levels to filter by'),
    'criticities': fields.List(fields.Integer(), required=False, description='List of criticality levels to filter by'),
    'message': fields.String(required=False, description='Partial message content to search for'),
    'classification': fields.String(required=False, description='Event classification/category'),
    'description': fields.String(required=False, description='Partial description content to search for'),
    'greater_than_timestamp': fields.DateTime(required=False, default=datetime.now(pytz.utc).astimezone(TIMEZONE) - timedelta(minutes=30), description=f'Start time for filtering - DateTime Format: {app.cvt.DATETIME_FORMAT}'),
    'less_than_timestamp': fields.DateTime(required=False, default=datetime.now(pytz.utc).astimezone(TIMEZONE), description=f'End time for filtering - DateTime Format: {app.cvt.DATETIME_FORMAT}'),
    'timezone': fields.String(required=False, default=_TIMEZONE, description='Timezone for the query'),
    'page': fields.Integer(required=False, default=1, description='Page number for pagination'),
    'limit': fields.Integer(required=False, default=20, description='Items per page')
})

    
@ns.route('/filter_by')
class EventsSummaryFilterByResource(Resource):

    @api.doc(security='apikey', description="Filters system events based on criteria.")
    @api.response(200, "Success")
    @api.response(400, "Invalid parameters")
    @Api.token_required(auth=True)
    @ns.expect(events_filter_model)
    def post(self):
        r"""
        Filter system events.

        Retrieves a list of system events matching the provided filters.
        """
        timezone = _TIMEZONE
        if "timezone" in api.payload:
            timezone = api.payload["timezone"]

        if timezone not in pytz.all_timezones:
            return f"Invalid Timezone", 400

        # Get timezone object for conversions
        tz = pytz.timezone(timezone)
        
        separator = '.'
        
        # Convert timestamps from user timezone to UTC before passing to model
        if 'greater_than_timestamp' in api.payload:
            greater_than_timestamp = api.payload['greater_than_timestamp']
            # Format the string
            timestamp_str = greater_than_timestamp.replace("T", " ").split(separator, 1)[0] + '.00'
            
            # Parse as naive datetime in user's timezone
            try:
                dt_naive = datetime.strptime(timestamp_str, '%Y-%m-%d %H:%M:%S.%f')
            except ValueError:
                dt_naive = datetime.strptime(timestamp_str.split('.')[0], '%Y-%m-%d %H:%M:%S')
            
            # Localize to user's timezone, then convert to UTC
            dt_local = tz.localize(dt_naive)
            dt_utc = dt_local.astimezone(pytz.UTC)
            
            # Pass as naive UTC datetime to model (model expects UTC naive)
            api.payload['greater_than_timestamp'] = dt_utc.replace(tzinfo=None)
        
        if "less_than_timestamp" in api.payload:
            less_than_timestamp = api.payload['less_than_timestamp']
            # Format the string
            timestamp_str = less_than_timestamp.replace("T", " ").split(separator, 1)[0] + '.00'
            
            # Parse as naive datetime in user's timezone
            try:
                dt_naive = datetime.strptime(timestamp_str, '%Y-%m-%d %H:%M:%S.%f')
            except ValueError:
                dt_naive = datetime.strptime(timestamp_str.split('.')[0], '%Y-%m-%d %H:%M:%S')
            
            # Localize to user's timezone, then convert to UTC
            dt_local = tz.localize(dt_naive)
            dt_utc = dt_local.astimezone(pytz.UTC)
            
            # Pass as naive UTC datetime to model (model expects UTC naive)
            api.payload['less_than_timestamp'] = dt_utc.replace(tzinfo=None)
        
        # Keep timezone in payload for serialization
        result = app.filter_events_by(**api.payload)
        
        # The timezone is already passed to filter_by and used in serialize()
        return result
    

@ns.route('/lasts/<lasts>')
@api.param('lasts', 'Number of records to retrieve')
class LastsEventsResource(Resource):

    @api.doc(security='apikey', description="Retrieves the last N system events.")
    @api.response(200, "Success")
    @Api.token_required(auth=True)
    def get(self, lasts:int=10):
        r"""
        Get latest events.

        Retrieves the most recent system events from the log.
        """
        
        return app.get_lasts_events(lasts=int(lasts))
    

@ns.route('/<id>/comments')
@api.param('id', 'Event ID')
class EventsCommentsResource(Resource):

    @api.doc(security='apikey', description="Retrieves comments associated with a specific event.")
    @api.response(200, "Success")
    @Api.token_required(auth=True)
    def get(self, id:int):
        r"""
        Get event comments.

        Retrieves user comments linked to a specific system event.
        """
        comments = Events.get_comments(id=id)
        return comments, 200
