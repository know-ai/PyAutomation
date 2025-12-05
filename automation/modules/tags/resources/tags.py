import pytz
from datetime import datetime, timedelta
from flask_restx import Namespace, Resource, fields, reqparse
from .... import PyAutomation
from ....extensions.api import api
from ....extensions import _api as Api
from .... import _TIMEZONE, TIMEZONE

ns = Namespace('Tags', description='Tags')
app = PyAutomation()

query_trends_model = api.model("query_trends_model",{
    'tags':  fields.List(fields.String(), required=True),
    'greater_than_timestamp': fields.DateTime(required=True, default=datetime.now(pytz.utc).astimezone(TIMEZONE) - timedelta(minutes=30), description='Greater than DateTime'),
    'less_than_timestamp': fields.DateTime(required=True, default=datetime.now(pytz.utc).astimezone(TIMEZONE), description='Less than DateTime'),
    'timezone': fields.String(required=True, default=_TIMEZONE)
})

write_value_model = api.model("write_value_model", {
    'tag_name': fields.String(required=True, description='Nombre del tag'),
    'value': fields.Raw(required=True, description='Valor a escribir (float, int, bool, str)')
})


@ns.route('/')
class TagsCollection(Resource):

    @api.doc(security='apikey')
    @Api.token_required(auth=True)
    def get(self):
        """
        Get Tags
        """
        return app.get_tags(), 200

@ns.route('/names')
class TagsNamesCollection(Resource):

    parser = reqparse.RequestParser()
    parser.add_argument('names', type=str, action='append', location='args', help='Tags names to get')

    @api.doc(security='apikey', parser=parser)
    @Api.token_required(auth=True)
    def get(self):
        """
        Get Tags Names
        """
        args = self.parser.parse_args()
        names = args.get('names')
        return app.get_tags_by_names(names=names or []), 200
    
@ns.route('/query_trends')
class QueryTrendsResource(Resource):

    @api.doc(security='apikey')
    @Api.token_required(auth=True)
    @ns.expect(query_trends_model)
    def post(self):
        """
        Query tag value filtering by timestamp

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
    
@ns.route('/write_value')
class WriteValueResource(Resource):

    @api.doc(security='apikey')
    @Api.token_required(auth=True)
    @ns.expect(write_value_model)
    def post(self):
        """
        Escribe un valor a un tag en CVT y en el servidor OPC UA si está configurado
        
        Authorized Roles: {0}
        """
        tag_name = api.payload['tag_name']
        value = api.payload['value']
        
        # Buscar el tag en CVT
        tag = app.cvt.get_tag_by_name(name=tag_name)
        if not tag:
            return {'message': f'Tag {tag_name} no existe', 'success': False}, 404
        
        # Escribir en CVT
        try:
            timestamp = datetime.now(pytz.utc).astimezone(TIMEZONE)
            app.cvt.set_value(id=tag.id, value=value, timestamp=timestamp)
        except Exception as err:
            return {
                'message': f'Error escribiendo en CVT: {str(err)}',
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
            'message': 'Valor escrito en CVT' + (' y OPC UA' if opcua_status == 200 else ''),
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

    @api.doc(security='apikey')
    @Api.token_required(auth=True)
    def get(self):
        """
        Get Available Timezones
        """
        return pytz.all_timezones, 200