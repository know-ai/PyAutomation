from flask_restx import Namespace, Resource, fields
from .... import PyAutomation
from ....extensions.api import api
from ....extensions import _api as Api

ns = Namespace('Settings', description='Settings')
app = PyAutomation()

settings_model = api.model("settings_model", {
    'logger_period': fields.Float(required=True, min=1.0, description='Logger worker period in seconds')
})

@ns.route('/logger_period')
class LoggerPeriodResource(Resource):
    
    @api.doc(security='apikey')
    @Api.token_required(auth=True)
    @ns.expect(settings_model)
    def put(self):
        """
        Update logger worker period
        """
        logger_period = api.payload.get('logger_period')
        
        if logger_period < 1.0:
            return "Logger period must be >= 1.0", 400
            
        app.update_logger_period(logger_period)
        
        return "Logger period updated", 200

