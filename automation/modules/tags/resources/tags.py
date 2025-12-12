import pytz
from datetime import datetime, timedelta
from flask_restx import Namespace, Resource, fields, reqparse
from .... import PyAutomation
from ....extensions.api import api
from ....extensions import _api as Api
from .... import _TIMEZONE, TIMEZONE

ns = Namespace('Tags', description='Tag Management and Real-time Data')
app = PyAutomation()

query_trends_model = api.model("query_trends_model",{
    'tags':  fields.List(fields.String(), required=True, description='List of tag names to query'),
    'greater_than_timestamp': fields.DateTime(required=True, default=datetime.now(pytz.utc).astimezone(TIMEZONE) - timedelta(minutes=30), description='Start DateTime'),
    'less_than_timestamp': fields.DateTime(required=True, default=datetime.now(pytz.utc).astimezone(TIMEZONE), description='End DateTime'),
    'timezone': fields.String(required=True, default=_TIMEZONE, description='Timezone for the query')
})

query_table_model = api.model("query_table_model",{
    'tags':  fields.List(fields.String(), required=True, description='List of tag names to query'),
    'greater_than_timestamp': fields.DateTime(required=True, default=datetime.now(pytz.utc).astimezone(TIMEZONE) - timedelta(minutes=30), description='Start DateTime'),
    'less_than_timestamp': fields.DateTime(required=True, default=datetime.now(pytz.utc).astimezone(TIMEZONE), description='End DateTime'),
    'timezone': fields.String(required=True, default=_TIMEZONE, description='Timezone for the query'),
    'page': fields.Integer(required=False, default=1, description='Page number'),
    'limit': fields.Integer(required=False, default=20, description='Items per page')
})

query_tabular_data_model = api.model("query_tabular_data_model",{
    'tags':  fields.List(fields.String(), required=True, description='List of tag names to query'),
    'greater_than_timestamp': fields.DateTime(required=True, default=datetime.now(pytz.utc).astimezone(TIMEZONE) - timedelta(minutes=30), description='Start DateTime'),
    'less_than_timestamp': fields.DateTime(required=True, default=datetime.now(pytz.utc).astimezone(TIMEZONE), description='End DateTime'),
    'sample_time': fields.Integer(required=False, default=30, description='Resampling interval in seconds (must be > 0)'),
    'timezone': fields.String(required=True, default=_TIMEZONE, description='Timezone for the query'),
    'page': fields.Integer(required=False, default=1, description='Page number'),
    'limit': fields.Integer(required=False, default=20, description='Items per page')
})

write_value_model = api.model("write_value_model", {
    'tag_name': fields.String(required=True, description='Tag Name'),
    'value': fields.Raw(required=True, description='Value to write (float, int, bool, str)')
})

create_tag_model = api.model("create_tag_model", {
    'name': fields.String(required=True, description='Unique tag name'),
    'unit': fields.String(required=True, description='Engineering unit'),
    'variable': fields.String(required=True, description='Variable type (e.g., Pressure, Temperature)'),
    'display_unit': fields.String(required=False, description='Unit for display purposes', default=''),
    'data_type': fields.String(required=False, description='Data type (float, int, bool, str)', default='float'),
    'description': fields.String(required=False, description='Tag description'),
    'display_name': fields.String(required=False, description='Friendly name for display'),
    'opcua_address': fields.String(required=False, description='OPC UA server URL'),
    'node_namespace': fields.String(required=False, description='OPC UA Node ID'),
    'scan_time': fields.Integer(required=False, description='Polling interval in ms'),
    'dead_band': fields.Float(required=False, description='Deadband value'),
    'process_filter': fields.Boolean(required=False, description='Enable process filter', default=False),
    'gaussian_filter': fields.Boolean(required=False, description='Enable Gaussian filter', default=False),
    'gaussian_filter_threshold': fields.Float(required=False, description='Gaussian filter threshold', default=1.0),
    'gaussian_filter_r_value': fields.Float(required=False, description='Gaussian filter R value', default=0.0),
    'outlier_detection': fields.Boolean(required=False, description='Enable outlier detection', default=False),
    'out_of_range_detection': fields.Boolean(required=False, description='Enable out of range detection', default=False),
    'frozen_data_detection': fields.Boolean(required=False, description='Enable frozen data detection', default=False),
    'segment': fields.String(required=False, description='Network segment', default=''),
    'manufacturer': fields.String(required=False, description='Device manufacturer', default='')
})

update_tag_model = api.model("update_tag_model", {
    'id': fields.String(required=True, description='Tag ID'),
    'name': fields.String(required=False, description='Tag name'),
    'unit': fields.String(required=False, description='Engineering unit'),
    'variable': fields.String(required=False, description='Variable type'),
    'display_unit': fields.String(required=False, description='Unit for display purposes'),
    'data_type': fields.String(required=False, description='Data type'),
    'description': fields.String(required=False, description='Tag description'),
    'display_name': fields.String(required=False, description='Friendly name for display'),
    'opcua_address': fields.String(required=False, description='OPC UA server URL'),
    'node_namespace': fields.String(required=False, description='OPC UA Node ID'),
    'scan_time': fields.Integer(required=False, description='Polling interval in ms'),
    'dead_band': fields.Float(required=False, description='Deadband value'),
    'process_filter': fields.Boolean(required=False, description='Enable process filter'),
    'gaussian_filter': fields.Boolean(required=False, description='Enable Gaussian filter'),
    'gaussian_filter_threshold': fields.Float(required=False, description='Gaussian filter threshold'),
    'gaussian_filter_r_value': fields.Float(required=False, description='Gaussian filter R value'),
    'outlier_detection': fields.Boolean(required=False, description='Enable outlier detection'),
    'out_of_range_detection': fields.Boolean(required=False, description='Enable out of range detection'),
    'frozen_data_detection': fields.Boolean(required=False, description='Enable frozen data detection'),
    'segment': fields.String(required=False, description='Network segment'),
    'manufacturer': fields.String(required=False, description='Device manufacturer')
})


@ns.route('/')
class TagsCollection(Resource):

    parser = reqparse.RequestParser()
    parser.add_argument('page', type=int, location='args', help='Page number', default=1)
    parser.add_argument('limit', type=int, location='args', help='Items per page', default=20)

    @api.doc(security='apikey', description="Retrieves all available tags with pagination support.")
    @api.response(200, "Success")
    @ns.expect(parser)
    @Api.token_required(auth=True)
    def get(self):
        """
        Get all tags.

        Retrieves a paginated list of all tags currently defined in the system.
        Supports pagination via query parameters: page (default: 1) and limit (default: 20).
        """
        args = self.parser.parse_args()
        page = args.get('page', 1)
        limit = args.get('limit', 20)
        
        # Validate pagination parameters
        if page < 1:
            return {'message': 'Page number must be greater than 0'}, 400
        if limit < 1:
            return {'message': 'Limit must be greater than 0'}, 400
        
        # Get all tags
        all_tags = app.get_tags()
        total = len(all_tags)
        
        # Calculate pagination
        start_idx = (page - 1) * limit
        end_idx = start_idx + limit
        paginated_tags = all_tags[start_idx:end_idx]
        
        return {
            'data': paginated_tags,
            'pagination': {
                'page': page,
                'limit': limit,
                'total': total,
                'pages': (total + limit - 1) // limit if total > 0 else 0
            }
        }, 200

@ns.route('/names')
class TagsNamesCollection(Resource):

    parser = reqparse.RequestParser()
    parser.add_argument('names', type=str, action='append', location='args', help='List of tag names to retrieve')

    @api.doc(security='apikey', description="Retrieves specific tags by name.")
    @api.response(200, "Success")
    @ns.expect(parser)
    @Api.token_required(auth=True)
    def get(self):
        """
        Get tags by name.

        Retrieves details for a specific list of tags provided as query parameters.
        """
        args = self.parser.parse_args()
        names = args.get('names')
        return app.get_tags_by_names(names=names or []), 200
    
@ns.route('/query_trends')
class QueryTrendsResource(Resource):

    @api.doc(security='apikey', description="Queries historical trend data for tags.")
    @api.response(200, "Success")
    @api.response(400, "Invalid parameters or Timezone")
    @api.response(404, "Tag not found")
    @Api.token_required(auth=True)
    @ns.expect(query_trends_model)
    def post(self):
        """
        Query trends.

        Retrieves historical time-series data for a list of tags within a specified time range.
        
        Authorized Roles: {0}
        """
        timezone = _TIMEZONE
        tags = api.payload['tags']
        if "timezone" in api.payload:

            timezone = api.payload["timezone"]

        if timezone not in pytz.all_timezones:

            return f"Invalid Timezone", 400
        
        for tag in tags:

            if not app.get_tag_by_name(name=tag):

                return f"{tag} not exist into db", 404
        
        separator = '.'
        greater_than_timestamp = api.payload['greater_than_timestamp']
        start = greater_than_timestamp.replace("T", " ").split(separator, 1)[0] + '.00'
        less_than_timestamp = api.payload['less_than_timestamp']
        stop = less_than_timestamp.replace("T", " ").split(separator, 1)[0] + '.00'
        result = app.get_trends(start, stop, timezone, *tags)
        
        return result, 200

@ns.route('/query_table')
class QueryTableResource(Resource):

    @api.doc(security='apikey', description="Queries historical data in table format.")
    @api.response(200, "Success")
    @api.response(400, "Invalid parameters")
    @api.response(404, "Tag not found")
    @Api.token_required(auth=True)
    @ns.expect(query_table_model)
    def post(self):
        """
        Query data table.

        Retrieves historical tag values in a paginated list format.

        Authorized Roles: {0}
        """
        timezone = _TIMEZONE
        tags = api.payload['tags']
        page = api.payload.get('page', 1)
        limit = api.payload.get('limit', 20)

        if "timezone" in api.payload:
            timezone = api.payload["timezone"]

        if timezone not in pytz.all_timezones:
            return f"Invalid Timezone", 400
        
        for tag in tags:
            if not app.get_tag_by_name(name=tag):
                return f"{tag} not exist into db", 404
        
        separator = '.'
        greater_than_timestamp = api.payload['greater_than_timestamp']
        # Ensure timestamp format is consistent
        start = greater_than_timestamp.replace("T", " ").split(separator, 1)[0] + '.00'
        
        less_than_timestamp = api.payload['less_than_timestamp']
        stop = less_than_timestamp.replace("T", " ").split(separator, 1)[0] + '.00'
        
        result = app.get_tags_tables(start, stop, timezone, tags, page, limit)
        
        return result, 200
    
@ns.route('/get_tabular_data')
class GetTabularDataResource(Resource):

    @api.doc(security='apikey', description="Queries historical data in a resampled tabular format.")
    @api.response(200, "Success")
    @api.response(400, "Invalid parameters")
    @api.response(404, "Tag not found")
    @Api.token_required(auth=True)
    @ns.expect(query_tabular_data_model)
    def post(self):
        """
        Get tabular data.

        Query tag values in tabular format with pagination and resampling.
        
        The result contains data points at regular intervals (sample_time) from greater_than_timestamp 
        up to less_than_timestamp. If exact data is missing, the previous known value is used (forward fill).
        
        Authorized Roles: {0}
        """
        timezone = _TIMEZONE
        tags = api.payload['tags']
        page = api.payload.get('page', 1)
        limit = api.payload.get('limit', 20)
        sample_time = api.payload.get('sample_time', 30)

        # Validar que sample_time sea un entero positivo > 0
        if not isinstance(sample_time, int) or sample_time <= 0:
            return {'message': 'sample_time must be a positive integer greater than 0'}, 400

        if "timezone" in api.payload:
            timezone = api.payload["timezone"]

        if timezone not in pytz.all_timezones:
            return f"Invalid Timezone", 400
        
        for tag in tags:
            if not app.get_tag_by_name(name=tag):
                return f"{tag} not exist into db", 404
        
        separator = '.'
        greater_than_timestamp = api.payload['greater_than_timestamp']
        # Ensure timestamp format is consistent
        start = greater_than_timestamp.replace("T", " ").split(separator, 1)[0] + '.00'
        
        less_than_timestamp = api.payload['less_than_timestamp']
        stop = less_than_timestamp.replace("T", " ").split(separator, 1)[0] + '.00'
        
        result = app.get_tabular_data(start, stop, timezone, tags, sample_time, page, limit)
        
        return result, 200

@ns.route('/write_value')
class WriteValueResource(Resource):

    @api.doc(security='apikey', description="Writes a value to a tag.")
    @api.response(200, "Success (CVT and OPC UA if applicable)")
    @api.response(207, "Partial Success (CVT OK, OPC UA Failed)")
    @api.response(404, "Tag not found")
    @api.response(500, "Internal Error")
    @Api.token_required(auth=True)
    @ns.expect(write_value_model)
    def post(self):
        """
        Write tag value.

        Writes a value to a tag in the Current Value Table (CVT). 
        If the tag is mapped to an OPC UA Node, it also attempts to write to the OPC UA Server.
        
        Authorized Roles: {0}
        """
        tag_name = api.payload['tag_name']
        value = api.payload['value']
        
        # Buscar el tag en CVT
        tag = app.cvt.get_tag_by_name(name=tag_name)
        if not tag:
            return {'message': f'Tag {tag_name} does not exist', 'success': False}, 404
        
        # Escribir en CVT
        try:
            timestamp = datetime.now(pytz.utc).astimezone(TIMEZONE)
            app.cvt.set_value(id=tag.id, value=value, timestamp=timestamp)
        except Exception as err:
            return {
                'message': f'Error writing to CVT: {str(err)}',
                'tag': tag_name,
                'success': False
            }, 500
        
        # Si tiene node_namespace, escribir en OPC UA Server usando el método de core
        opcua_result = None
        opcua_status = None
        if tag.node_namespace and tag.opcua_address:
            opcua_result, opcua_status = app.write_opcua_value(
                opcua_address=tag.opcua_address,
                node_namespace=tag.node_namespace,
                value=value
            )
        
        # Resultado consolidado
        result = {
            'message': 'Value written to CVT' + (' and OPC UA' if opcua_status == 200 else ''),
            'tag': tag_name,
            'value': value,
            'cvt_success': True,
            'opcua_success': opcua_status == 200 if opcua_status else None,
            'opcua_detail': opcua_result if opcua_result else None
        }
        
        # Status: 200 si CVT OK, aunque OPC UA falle (parcial success)
        final_status = 200 if opcua_status in (200, None) else 207  # 207 = Multi-Status
        return result, final_status

@ns.route('/add')
class AddTagResource(Resource):

    @api.doc(security='apikey', description="Creates a new tag in the system.")
    @api.response(200, "Tag created successfully")
    @api.response(400, "Tag creation failed")
    @Api.token_required(auth=True)
    @ns.expect(create_tag_model)
    def post(self):
        """
        Create tag.

        Creates a new tag in the automation application with the specified configuration.
        """
        payload = api.payload
        
        # Required fields
        name = payload.get('name')
        unit = payload.get('unit')
        variable = payload.get('variable')
        
        if not name or not unit or not variable:
            return {
                'message': 'Missing required fields: name, unit, and variable are required'
            }, 400
        
        try:
            tag, message = app.create_tag(
                name=name,
                unit=unit,
                variable=variable,
                display_unit=payload.get('display_unit', ''),
                data_type=payload.get('data_type', 'float'),
                description=payload.get('description'),
                display_name=payload.get('display_name'),
                opcua_address=payload.get('opcua_address'),
                node_namespace=payload.get('node_namespace'),
                scan_time=payload.get('scan_time'),
                dead_band=payload.get('dead_band'),
                process_filter=payload.get('process_filter', False),
                gaussian_filter=payload.get('gaussian_filter', False),
                gaussian_filter_threshold=payload.get('gaussian_filter_threshold', 1.0),
                gaussian_filter_r_value=payload.get('gaussian_filter_r_value', 0.0),
                outlier_detection=payload.get('outlier_detection', False),
                out_of_range_detection=payload.get('out_of_range_detection', False),
                frozen_data_detection=payload.get('frozen_data_detection', False),
                segment=payload.get('segment', ''),
                manufacturer=payload.get('manufacturer', '')
            )
            
            if tag:
                return {
                    'message': f"Tag '{name}' created successfully",
                    'tag': {
                        'id': tag.id,
                        'name': tag.name,
                        'unit': tag.unit,
                        'variable': tag.variable
                    }
                }, 200
            else:
                return {
                    'message': f"Failed to create tag: {message}"
                }, 400
        except Exception as e:
            return {
                'message': f"Error creating tag: {str(e)}"
            }, 400


@ns.route('/update')
class UpdateTagResource(Resource):

    @api.doc(security='apikey', description="Updates an existing tag configuration.")
    @api.response(200, "Tag updated successfully")
    @api.response(400, "Tag update failed")
    @api.response(404, "Tag not found")
    @Api.token_required(auth=True)
    @ns.expect(update_tag_model)
    def post(self):
        """
        Update tag.

        Updates the configuration of an existing tag. Only provided fields will be updated.
        """
        payload = api.payload
        
        # Required field
        tag_id = payload.get('id')
        if not tag_id:
            return {
                'message': 'Tag ID is required'
            }, 400
        
        # Check if tag exists
        try:
            tag = app.cvt.get_tag(id=tag_id)
            if not tag:
                return {
                    'message': f'Tag with ID {tag_id} not found'
                }, 404
        except Exception:
            return {
                'message': f'Tag with ID {tag_id} not found'
            }, 404
        
        # Build kwargs with only provided fields (excluding 'id')
        update_kwargs = {k: v for k, v in payload.items() if k != 'id' and v is not None}
        
        if not update_kwargs:
            return {
                'message': 'No fields to update provided'
            }, 400
        
        try:
            updated_tag, message = app.update_tag(id=tag_id, **update_kwargs)
            
            if updated_tag:
                return {
                    'message': f"Tag '{updated_tag.name}' updated successfully",
                    'tag': {
                        'id': updated_tag.id,
                        'name': updated_tag.name
                    }
                }, 200
            else:
                return {
                    'message': f"Failed to update tag: {message}"
                }, 400
        except Exception as e:
            return {
                'message': f"Error updating tag: {str(e)}"
            }, 400


@ns.route('/delete/<tag_name>')
@api.param('tag_name', 'The tag name to delete')
class DeleteTagResource(Resource):

    @api.doc(security='apikey', description="Deletes a tag from the system by name.")
    @api.response(200, "Tag deleted successfully")
    @api.response(400, "Tag deletion failed")
    @api.response(404, "Tag not found")
    @Api.token_required(auth=True)
    def delete(self, tag_name):
        """
        Delete tag.

        Deletes a tag from the system by its name. 
        Note: Tags with associated alarms cannot be deleted.
        """
        # Check if tag exists
        tag = app.get_tag_by_name(name=tag_name)
        if not tag:
            return {
                'message': f'Tag "{tag_name}" not found'
            }, 404
        
        try:
            result = app.delete_tag_by_name(name=tag_name)
            
            if result:
                # If result is a string, it's an error message
                return {
                    'message': result
                }, 400
            else:
                return {
                    'message': f'Tag "{tag_name}" deleted successfully'
                }, 200
        except Exception as e:
            return {
                'message': f"Error deleting tag: {str(e)}"
            }, 400


@ns.route('/timezones')
class TimezonesCollection(Resource):

    @api.doc(security='apikey', description="Retrieves a list of available timezones.")
    @api.response(200, "Success")
    @Api.token_required(auth=True)
    def get(self):
        """
        Get Timezones.

        Retrieves a list of all supported timezones.
        """
        return pytz.all_timezones, 200