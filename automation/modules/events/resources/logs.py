from flask_restx import Namespace, Resource, fields
from automation import PyAutomation
from automation.extensions.api import api
from datetime import datetime, timedelta
from automation.extensions import _api as Api

ns = Namespace('Operation Logs', description='Operation Logs')
app = PyAutomation()


logs_filter_model = api.model("logs_filter_model",{
    'usernames': fields.List(fields.String(), required=False),
    'alarm_names': fields.List(fields.String(), required=False),
    'event_ids': fields.List(fields.Integer(), required=False),
    'greater_than_timestamp': fields.DateTime(required=False, default=datetime.now() - timedelta(minutes=2), description=f'Greater than timestamp - DateTime Format: {app.cvt.DATETIME_FORMAT}'),
    'less_than_timestamp': fields.DateTime(required=False, default=datetime.now(), description=f'Less than timestamp - DateTime Format: {app.cvt.DATETIME_FORMAT}')
})

    
@ns.route('/filter_by')
class LogsFilterByResource(Resource):

    @api.doc(security='apikey')
    @Api.token_required(auth=True)
    @ns.expect(logs_filter_model)
    def post(self):
        r"""
        Logs Filter By
        """
        
        return app.filter_logs_by(**api.payload)
    

@ns.route('/lasts/<lasts>')
class LastsEventsResource(Resource):

    @api.doc(security='apikey')
    @Api.token_required(auth=True)
    def get(self, lasts:int=10):
        r"""
        Get lasts events
        """
        
        return app.get_lasts_logs(lasts=lasts)
