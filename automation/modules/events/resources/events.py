from flask_restx import Namespace, Resource, fields
from automation import PyAutomation
from automation.extensions.api import api
from datetime import datetime, timedelta
from automation.extensions import _api as Api
from automation.dbmodels.events import Events

ns = Namespace('Events Logger', description='Events Logger')
app = PyAutomation()


events_filter_model = api.model("events_filter_model",{
    'usernames': fields.List(fields.String(), required=False),
    'priorities': fields.List(fields.Integer(), required=False),
    'criticities': fields.List(fields.Integer(), required=False),
    'greater_than_timestamp': fields.DateTime(required=False, default=datetime.now() - timedelta(minutes=2), description=f'Greater than timestamp - DateTime Format: {app.cvt.DATETIME_FORMAT}'),
    'less_than_timestamp': fields.DateTime(required=False, default=datetime.now(), description=f'Less than timestamp - DateTime Format: {app.cvt.DATETIME_FORMAT}')
})

    
@ns.route('/filter_by')
class EventsSummaryFilterByResource(Resource):

    @api.doc(security='apikey')
    @Api.token_required(auth=True)
    @ns.expect(events_filter_model)
    def post(self):
        r"""
        Events Summary Filter By
        """
        
        return app.filter_events_by(**api.payload)
    

@ns.route('/lasts/<lasts>')
class LastsEventsResource(Resource):

    @api.doc(security='apikey')
    @Api.token_required(auth=True)
    def get(self, lasts:int=10):
        r"""
        Get lasts events
        """
        
        return app.get_lasts_events(lasts=lasts)
    

@ns.route('/<id>/comments')
class EventsCommentsResource(Resource):

    @api.doc(security='apikey')
    @Api.token_required(auth=True)
    def get(self, id:int):
        r"""
        Get Alarm Summary Comments
        """
        comments = Events.get_comments(id=id)
        return comments, 200
