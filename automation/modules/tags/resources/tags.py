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
    'sample_time': fields.Integer(required=True, description='Resampling interval in seconds'),
    'timezone': fields.String(required=True, default=_TIMEZONE, description='Timezone for the query'),
    'page': fields.Integer(required=False, default=1, description='Page number'),
    'limit': fields.Integer(required=False, default=20, description='Items per page')
})

write_value_model = api.model("write_value_model", {
    'tag_name': fields.String(required=True, description='Tag Name'),
    'value': fields.Raw(required=True, description='Value to write (float, int, bool, str)')
})


@ns.route('/')
class TagsCollection(Resource):

    @api.doc(security='apikey', description="Retrieves all available tags.")
    @api.response(200, "Success")
    @Api.token_required(auth=True)
    def get(self):
        """
        Get all tags.

        Retrieves a list of all tags currently defined in the system.
        """
        return app.get_tags(), 200

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
        sample_time = api.payload.get('sample_time', 60) # Default 1 min if not provided, but model requires it

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