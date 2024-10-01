from datetime import datetime, timedelta
from flask_restx import Namespace, Resource, fields
from .... import PyAutomation
from ....extensions.api import api
from ....extensions import _api as Api

ns = Namespace('Operation Logs', description='Operation Logs')
app = PyAutomation()


logs_filter_model = api.model("logs_filter_model",{
    'usernames': fields.List(fields.String(), required=False),
    'alarm_names': fields.List(fields.String(), required=False),
    'event_ids': fields.List(fields.Integer(), required=False),
    'classification': fields.List(fields.String(), required=False),
    'greater_than_timestamp': fields.DateTime(required=False, default=datetime.now() - timedelta(minutes=2), description=f'Greater than timestamp - DateTime Format: {app.cvt.DATETIME_FORMAT}'),
    'less_than_timestamp': fields.DateTime(required=False, default=datetime.now(), description=f'Less than timestamp - DateTime Format: {app.cvt.DATETIME_FORMAT}')
})

logs_model = api.model("logs_model",{
    'message': fields.String(required=True, description="Log message"),
    'alarm_summary_id': fields.Integer(required=False, description="Alarm summary id comment"),
    'event_id': fields.Integer(required=False, description="Event id comment"),
    'description': fields.String(required=False, description="Log description")
})

@ns.route('/add')
class AddLogsByResource(Resource):

    @api.doc(security='apikey')
    @Api.token_required(auth=True)
    @ns.expect(logs_model)
    def post(self):
        r"""
        Create Log
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

    @api.doc(security='apikey')
    @Api.token_required(auth=True)
    @ns.expect(logs_filter_model)
    def post(self):
        r"""
        Logs Filter By
        """
        
        return app.filter_logs_by(**api.payload), 200
    

@ns.route('/lasts/<lasts>')
class LastsEventsResource(Resource):

    @api.doc(security='apikey')
    @Api.token_required(auth=True)
    def get(self, lasts:int=10):
        r"""
        Get lasts events
        """
        
        return app.get_lasts_logs(lasts=lasts), 200
