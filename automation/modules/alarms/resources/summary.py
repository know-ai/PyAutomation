from flask_restx import Namespace, Resource, fields
from automation import PyAutomation
from automation.extensions.api import api
from datetime import datetime, timedelta
DATETIME_FORMAT = "%m/%d/%Y, %H:%M:%S.%f"

ns = Namespace('Alarms Summary', description='Alarms Summary')
app = PyAutomation()

alarms_summary_filter_model = api.model("alarms_summary_filter_model",{
    'names': fields.List(fields.String(), required=True),
    'states': fields.List(fields.String(), required=True),
    'tags': fields.List(fields.String(), required=True),
    'greater_than_timestamp': fields.DateTime(required=False, default=datetime.now() - timedelta(minutes=2), description=f'Greater than timestamp - DateTime Format: {DATETIME_FORMAT}'),
    'less_than_timestamp': fields.DateTime(required=False, default=datetime.now(), description=f'Less than timestamp - DateTime Format: {DATETIME_FORMAT}')
})

    
@ns.route('/filter_by')
class AlarmsSummarygFilterByResource(Resource):

    @ns.expect(alarms_summary_filter_model)
    def post(self):
        r"""
        Alarms Summary Filter By
        """
        
        return app.filter_alarms_by(**api.payload)
    

@ns.route('/lasts/<lasts>')
class LastsAlarmsResource(Resource):

    def get(self, lasts:int=10):
        r"""
        Get lasts alarms
        """
        
        return app.get_lasts_alarms(lasts=lasts)
