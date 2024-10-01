from datetime import datetime, timedelta
from flask_restx import Namespace, Resource, fields
from .... import PyAutomation
from ....extensions.api import api
from ....extensions import _api as Api
from ....dbmodels.alarms import AlarmSummary

ns = Namespace('Alarms Summary', description='Alarms Summary')
app = PyAutomation()


alarms_summary_filter_model = api.model("alarms_summary_filter_model",{
    'names': fields.List(fields.String(), required=False),
    'states': fields.List(fields.String(), required=False),
    'tags': fields.List(fields.String(), required=False),
    'greater_than_timestamp': fields.DateTime(required=False, default=datetime.now() - timedelta(minutes=2), description=f'Greater than timestamp - DateTime Format: {app.cvt.DATETIME_FORMAT}'),
    'less_than_timestamp': fields.DateTime(required=False, default=datetime.now(), description=f'Less than timestamp - DateTime Format: {app.cvt.DATETIME_FORMAT}')
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
        
        return app.filter_alarms_by(**api.payload)
    

@ns.route('/lasts/<lasts>')
class LastsAlarmsResource(Resource):

    @api.doc(security='apikey')
    @Api.token_required(auth=True)
    def get(self, lasts:int=10):
        r"""
        Get lasts alarms
        """
        
        return app.get_lasts_alarms(lasts=lasts)
    

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
