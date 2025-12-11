from flask_restx import Namespace, Resource, fields, reqparse
from flask import request, make_response
from .... import PyAutomation
from ....extensions.api import api
from ....extensions import _api as Api
import json

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

@ns.route('/export_config')
class ExportConfigResource(Resource):
    
    @api.doc(security='apikey', description="Exports all configuration data to a JSON file. Excludes historical data (TagValue, Events, Logs, AlarmSummary).")
    @api.response(200, "Configuration exported successfully")
    @api.response(400, "Export failed")
    @api.response(401, "Unauthorized")
    # @Api.token_required(auth=True)
    def get(self):
        """
        Export configuration.

        Exports all configuration tables (Manufacturer, Segment, Variables, Units, DataTypes,
        Tags, AlarmTypes, AlarmStates, Alarms, Roles, Users, OPCUA, AccessType, OPCUAServer,
        Machines, TagsMachines) to a JSON file. Historical data is excluded.
        """
        try:
            config_data = app.export_configuration()
            
            if "error" in config_data:
                return {'message': config_data["error"]}, 400
            
            # Create JSON string in memory
            json_str = json.dumps(config_data, indent=2, default=str)
            json_bytes = json_str.encode('utf-8')
            
            # Create response with explicit headers to force download
            # Using application/octet-stream helps force download in Swagger UI
            response = make_response(json_bytes)
            response.headers['Content-Type'] = 'application/octet-stream'
            response.headers['Content-Disposition'] = 'attachment; filename="configuration_export.json"'
            response.headers['Content-Length'] = str(len(json_bytes))
            response.headers['X-Content-Type-Options'] = 'nosniff'
            
            return response
        except Exception as e:
            return {'message': f'Export failed: {str(e)}'}, 400

import_config_parser = reqparse.RequestParser(bundle_errors=True)
import_config_parser.add_argument('file', type=reqparse.FileStorage, location='files', required=True, help='JSON configuration file to import')

@ns.route('/import_config')
class ImportConfigResource(Resource):
    
    @Api.validate_reqparser(reqparser=import_config_parser)
    @api.doc(security='apikey', description="Imports configuration data from a JSON file. Restores all configuration tables while preserving historical data.")
    @api.response(200, "Configuration imported successfully")
    @api.response(400, "Import failed")
    @api.response(401, "Unauthorized")
    @ns.expect(import_config_parser)
    # @Api.token_required(auth=True)
    def post(self):
        """
        Import configuration.

        Imports configuration data from a JSON file. The file should be in the format
        exported by the export_config endpoint. Historical data (TagValue, Events, Logs,
        AlarmSummary) is not affected by the import.
        """
        try:
            if 'file' not in request.files:
                return {'message': 'No file provided'}, 400
            
            file = request.files['file']
            
            if file.filename == '':
                return {'message': 'No file selected'}, 400
            
            if not file.filename.endswith('.json'):
                return {'message': 'File must be a JSON file'}, 400
            
            # Read and parse JSON
            file_content = file.read()
            try:
                config_data = json.loads(file_content.decode('utf-8'))
            except json.JSONDecodeError as e:
                return {'message': f'Invalid JSON file: {str(e)}'}, 400
            
            # Import configuration
            result = app.import_configuration(config_data)
            
            if "error" in result:
                return {'message': result["error"], 'details': result.get("results", {})}, 400
            
            return {
                'message': result.get("message", "Configuration imported successfully"),
                'summary': result.get("summary", {}),
                'results': result.get("results", {})
            }, 200
            
        except Exception as e:
            return {'message': f'Import failed: {str(e)}'}, 400
