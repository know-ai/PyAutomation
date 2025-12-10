from flask_restx import Namespace, Resource, fields
from .... import PyAutomation
from ....extensions.api import api
from ....extensions import _api as Api

ns = Namespace('Settings', description='Application Configuration Settings')
app = PyAutomation()

settings_model = api.model("settings_model", {
    'logger_period': fields.Float(required=False, min=1.0, description='Logger worker period in seconds (>= 1.0)'),
    'log_max_bytes': fields.Integer(required=False, min=1024, description='Max bytes for log file rotation (>= 1024)'),
    'log_backup_count': fields.Integer(required=False, min=1, description='Number of backup log files to keep (>= 1)'),
    'log_level': fields.Integer(required=False, min=0, max=50, description='Logging level (0=NOTSET, 10=DEBUG, 20=INFO, 30=WARNING, 40=ERROR, 50=CRITICAL)')
})

@ns.route('/update')
class SettingsUpdateResource(Resource):
    
    @api.doc(security='apikey', description="Updates various application settings.")
    @api.response(200, "Settings updated successfully")
    @api.response(400, "Invalid parameter values")
    @Api.token_required(auth=True)
    @ns.expect(settings_model)
    def put(self):
        """
        Update settings.

        Updates application configuration including logger period, log rotation settings, and logging level.
        """
        data = api.payload
        
        # 1. Update Logger Worker Period
        if 'logger_period' in data:
            logger_period = data['logger_period']
            if logger_period < 1.0:
                return "Logger period must be >= 1.0", 400
            app.update_logger_period(logger_period)

        # 2. Update Log Rotation Config
        if 'log_max_bytes' in data and 'log_backup_count' in data:
            max_bytes = data['log_max_bytes']
            backup_count = data['log_backup_count']
            
            if max_bytes < 1024:
                 return "log_max_bytes must be >= 1024", 400
            if backup_count < 1:
                 return "log_backup_count must be >= 1", 400
                 
            app.update_log_config(max_bytes, backup_count)
        
        elif 'log_max_bytes' in data or 'log_backup_count' in data:
             return "Both log_max_bytes and log_backup_count must be provided together", 400

        # 3. Update Log Level
        if 'log_level' in data:
            log_level = data['log_level']
            # Basic validation for standard levels
            if log_level not in [0, 10, 20, 30, 40, 50]:
                return "Invalid log_level. Use standard Python logging levels (10, 20, 30, 40, 50)", 400
            
            app.update_log_level(log_level)

        return "Settings updated", 200

@ns.route('/logger_period')
class LoggerPeriodResource(Resource):
    
    @api.doc(security='apikey', description="Updates only the logger worker period.")
    @api.response(200, "Logger period updated successfully")
    @api.response(400, "Invalid logger period")
    @Api.token_required(auth=True)
    @ns.expect(settings_model)
    def put(self):
        """
        Update logger period.

        Updates the execution period of the logger worker.
        """
        logger_period = api.payload.get('logger_period')
        
        if logger_period < 1.0:
            return "Logger period must be >= 1.0", 400
            
        app.update_logger_period(logger_period)
        
        return "Logger period updated", 200
