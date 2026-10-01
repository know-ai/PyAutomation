from flask_restx import Namespace, Resource, fields, reqparse
from flask import request, make_response
from .... import PyAutomation
from ....extensions.api import api
from ....extensions import _api as Api
from ..machines_summary_columns import (
    load_machines_summary_columns,
    save_machines_summary_columns,
)
from ..workspace import load_realtime_trends_workspace, save_realtime_trends_workspace
import json

ns = Namespace('Settings', description='Application Configuration Settings')
app = PyAutomation()

settings_model = api.model("settings_model", {
    'logger_period': fields.Float(required=False, min=1.0, description='Logger worker period in seconds (>= 1.0)'),
    'log_max_bytes': fields.Integer(required=False, min=1024, description='Max bytes for log file rotation (>= 1024)'),
    'log_backup_count': fields.Integer(required=False, min=1, description='Number of backup log files to keep (>= 1)'),
    'log_level': fields.Integer(required=False, min=0, max=50, description='Logging level (0=NOTSET, 10=DEBUG, 20=INFO, 30=WARNING, 40=ERROR, 50=CRITICAL)'),
    'log_error_cooldown_seconds': fields.Float(required=False, min=0, description='Dedupe cooldown for ERROR logs in seconds (0 disables)'),
    'alarm_inhibit_uncertain_quality': fields.Boolean(required=False, description='When true, UNCERTAIN PV quality inhibits process setpoints (ISA-18.2)'),
})

@ns.route('/')
class SettingsResource(Resource):
    
    @api.doc(security='apikey', description="Retrieves current application configuration settings.")
    @api.response(200, "Settings retrieved successfully")
    @api.response(401, "Unauthorized")
    @api.response(403, "Role not allowed")
    @Api.token_required(auth=True)
    @Api.auth_roles(["admin", "supervisor", "sudo"])
    def get(self):
        """
        Get settings.

        Retrieves current application configuration including logger period, log rotation settings, and logging level.
        """
        try:
            config = app.get_app_config()
            return config, 200
        except Exception as e:
            return {'message': f'Failed to retrieve settings: {str(e)}'}, 500

@ns.route('/update')
class SettingsUpdateResource(Resource):
    
    @api.doc(security='apikey', description="Updates various application settings.")
    @api.response(200, "Settings updated successfully")
    @api.response(400, "Invalid parameter values")
    @api.response(403, "Role not allowed")
    @Api.token_required(auth=True)
    @Api.auth_roles(["admin", "supervisor", "sudo"])
    @ns.expect(settings_model)
    def put(self):
        """
        Update settings.

        Updates application configuration including logger period, log rotation settings, and logging level.
        """
        data = api.payload or {}
        try:
            previous_config = app.get_app_config() or {}
        except Exception:
            previous_config = {}
        
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

        if 'log_error_cooldown_seconds' in data:
            cooldown = data['log_error_cooldown_seconds']
            if cooldown < 0:
                return "log_error_cooldown_seconds must be >= 0", 400
            app.update_log_error_cooldown(float(cooldown))

        if 'alarm_inhibit_uncertain_quality' in data:
            inhibit = bool(data['alarm_inhibit_uncertain_quality'])
            app.set_app_config(alarm_inhibit_uncertain_quality=inhibit)
            try:
                from ....signal_conditioning.quality import set_inhibit_uncertain_quality

                set_inhibit_uncertain_quality(inhibit)
            except Exception:
                pass

        try:
            from ....utils.config_audit import record_configuration_event, settings_change_description

            description = settings_change_description(previous_config, data)
            if description:
                record_configuration_event(
                    message="System settings updated",
                    description=description,
                    user=Api.get_current_user(),
                )
        except Exception:
            pass

        return "Settings updated", 200


client_preference_model = api.model("client_preference_model", {
    "key": fields.String(required=True, description="Workstation preference key"),
    "value": fields.String(required=True, description="New value"),
})


@ns.route("/client-preference")
class ClientPreferenceAuditResource(Resource):

    @api.doc(security="apikey", description="Records a workstation preference change in the Events log.")
    @api.response(200, "Recorded")
    @api.response(400, "Unknown preference")
    @Api.token_required(auth=True)
    @ns.expect(client_preference_model)
    def post(self):
        data = api.payload or {}
        from ....utils.config_audit import client_preference_change, record_configuration_event

        change = client_preference_change(data.get("key"), data.get("value"))
        if change is None:
            return {"message": "Unknown preference"}, 400
        record_configuration_event(
            message=change[0],
            description=change[1],
            user=Api.get_current_user(),
        )
        return {"message": "Recorded"}, 200


workspace_model = api.model("realtime_trends_workspace_model", {
    'schemaVersion': fields.Integer(required=False),
    'kind': fields.String(required=False),
    'scope': fields.String(required=False),
    'updatedAt': fields.String(required=False),
    'charts': fields.List(fields.Raw, required=False),
})


@ns.route('/workspace/realtime-trends')
class RealtimeTrendsWorkspaceResource(Resource):

    @api.doc(
        security='apikey',
        description="Station-scoped real-time trends layout. Persisted on disk (db/), survives host reboot.",
    )
    @api.response(200, "Workspace retrieved")
    @Api.token_required(auth=True)
    def get(self):
        try:
            return load_realtime_trends_workspace(), 200
        except Exception as e:
            return {'message': f'Failed to retrieve realtime-trends workspace: {str(e)}'}, 500

    @api.doc(security='apikey', description="Replaces the station real-time trends layout.")
    @api.response(200, "Workspace saved")
    @api.response(400, "Invalid payload")
    @Api.token_required(auth=True)
    @ns.expect(workspace_model)
    def put(self):
        data = api.payload
        if data is None:
            return {'message': 'JSON body required'}, 400
        try:
            before = load_realtime_trends_workspace()
            saved = save_realtime_trends_workspace(data)
            from ....utils.config_audit import realtime_trends_changes, record_configuration_event

            actor = Api.get_current_user()
            for message, description in realtime_trends_changes(before, saved):
                record_configuration_event(message=message, description=description, user=actor)
            return saved, 200
        except OSError as e:
            return {'message': f'Failed to persist realtime-trends workspace: {str(e)}'}, 500
        except Exception as e:
            return {'message': f'Failed to save realtime-trends workspace: {str(e)}'}, 400


_COLUMN_EDITOR_ROLES = frozenset({"integrator", "admin", "administrator"})

machines_summary_columns_model = api.model("machines_summary_columns_model", {
    "schemaVersion": fields.Integer(required=False),
    "kind": fields.String(required=False),
    "scope": fields.String(required=False),
    "updatedAt": fields.String(required=False),
    "columns": fields.List(fields.String, required=False),
})


@ns.route("/workspace/machines-summary")
class MachinesSummaryColumnsResource(Resource):

    @api.doc(
        security="apikey",
        description="Station-scoped columns for the machines summary. Persisted on disk (db/).",
    )
    @api.response(200, "Columns retrieved")
    @Api.token_required(auth=True)
    def get(self):
        try:
            return load_machines_summary_columns(), 200
        except Exception as e:
            return {"message": f"Failed to retrieve machines-summary columns: {str(e)}"}, 500

    @api.doc(security="apikey", description="Replaces the station machines-summary columns.")
    @api.response(200, "Columns saved")
    @api.response(400, "Invalid payload")
    @api.response(403, "Role not allowed")
    @Api.token_required(auth=True)
    @ns.expect(machines_summary_columns_model)
    def put(self):
        user = Api.get_current_user()
        role_name = str(getattr(getattr(user, "role", None), "name", "") or "").strip().lower()
        if role_name not in _COLUMN_EDITOR_ROLES:
            return {"message": "Only integrator or administrator can change summary columns"}, 403
        data = api.payload
        if data is None:
            return {"message": "JSON body required"}, 400
        try:
            before = load_machines_summary_columns()
            saved = save_machines_summary_columns(data)
            from ....utils.config_audit import record_configuration_event, summary_column_changes

            actor = Api.get_current_user()
            for message, description in summary_column_changes(
                before.get("columns"),
                saved.get("columns"),
            ):
                record_configuration_event(message=message, description=description, user=actor)
            return saved, 200
        except OSError as e:
            return {"message": f"Failed to persist machines-summary columns: {str(e)}"}, 500
        except Exception as e:
            return {"message": f"Failed to save machines-summary columns: {str(e)}"}, 400


@ns.route('/export_config')
class ExportConfigResource(Resource):
    
    @api.doc(security='apikey', description="Exports all configuration data to a JSON file. Excludes historical data (TagValue, Events, Logs, AlarmSummary).")
    @api.response(200, "Configuration exported successfully")
    @api.response(400, "Export failed")
    @api.response(401, "Unauthorized")
    @api.response(403, "Role not allowed")
    @Api.token_required(auth=True)
    @Api.auth_roles(["admin", "supervisor", "sudo"])
    def get(self):
        """
        Export configuration.

        Exports all configuration tables (Manufacturer, Segment, Variables, Units, DataTypes,
        Tags, AlarmTypes, AlarmStates, Alarms, Roles, Users, OPCUA, OPCUAServer,
        Machines, TagsMachines) to a JSON file. Historical data is excluded.
        """
        try:
            config_data = app.export_configuration()
            
            if "error" in config_data:
                status = 503 if config_data["error"] == "invalid-node-scope" else 400
                return {
                    'message': config_data.get("message") or config_data["error"]
                }, status
            
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
    @api.response(403, "Role not allowed")
    @ns.expect(import_config_parser)
    @Api.token_required(auth=True)
    @Api.auth_roles(["admin", "supervisor", "sudo"])
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
            
            error = result.get("error")
            if error == "invalid-node-scope":
                return {
                    'message': result.get("message") or error,
                    'details': result.get("results", {}),
                }, 503
            if error == "foreign-or-unscoped-runtime-data":
                return {
                    'message': result.get("message") or error,
                    'violations': result.get("violations", []),
                    'details': result.get("results", {}),
                }, 403
            if error:
                return {'message': error, 'details': result.get("results", {})}, 400

            from ....utils.config_audit import import_description, record_configuration_event

            record_configuration_event(
                message="Configuration imported",
                description=import_description(file.filename, result),
                user=Api.get_current_user(),
            )
            
            return {
                'message': result.get("message", "Configuration imported successfully"),
                'summary': result.get("summary", {}),
                'results': result.get("results", {})
            }, 200
            
        except Exception as e:
            return {'message': f'Import failed: {str(e)}'}, 400
