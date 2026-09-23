from flask import request
from flask_restx import Namespace, Resource, fields, reqparse
from .... import PyAutomation
from ....extensions.api import api
from ....extensions import _api as Api


ns = Namespace('OPCUA Server', description='OPC UA Server Management Resources')
app = PyAutomation()

attrs_parser = reqparse.RequestParser()
attrs_parser.add_argument(
    'name',
    type=str,
    location='args',
    required=False,
    default='',
    help='Optional case-insensitive filter on attribute name or namespace',
)

# Models
update_access_level_model = api.model("update_access_level_model", {
    'namespace': fields.String(required=True, description='OPC UA node namespace string'),
    'access_level': fields.Raw(required=True, description='Bitmask, hex, or label'),
    'name': fields.String(required=False, description='Node name (optional, used if record does not exist)')
})


@ns.route('/attrs')
class OPCUAServerAttributesResource(Resource):

    @api.doc(security='apikey', description="Retrieves all attributes (variables and properties) from the OPC UA Server state machine.")
    @api.response(200, "Success")
    @api.response(404, "OPC UA Server not found")
    @Api.token_required(auth=True)
    @ns.expect(attrs_parser)
    def get(self):
        r"""
        Get OPC UA Server attributes.

        Retrieves all OPC UA nodes (variables and their properties) from the embedded OPC UA Server
        with their access levels (Read, Write, ReadWrite).

        Returns a list of dictionaries containing:
        - name: Full path name (parent_folder.variable_name or parent_folder.variable_name.property_name)
        - namespace: OPC UA node namespace string
        - access_level: Access level ("Read", "Write", or "ReadWrite")
        """
        try:
            args = attrs_parser.parse_args()
            attrs = app.get_opcua_server_attrs(name=args.get('name') or '')
            return {
                "data": attrs
            }, 200
        except Exception as e:
            return {
                "message": f"Failed to retrieve OPC UA Server attributes: {str(e)}"
            }, 404


@ns.route('/attrs/update')
class OPCUAServerUpdateAccessLevelResource(Resource):

    @api.doc(security='apikey', description="Updates the access type (Read, Write, ReadWrite) for a specific OPC UA Server node.")
    @api.response(200, "Access type updated successfully")
    @api.response(400, "Invalid request or parameters")
    @api.response(404, "Node not found")
    @Api.token_required(auth=True)
    @ns.expect(update_access_level_model)
    def put(self):
        r"""
        Update the access bitmask of one OPC UA Server node.
        """
        from ....opcua_server.access.level import access_label, parse_access_level

        if not request.is_json:
            return {"message": "Request must be JSON"}, 400
        data = request.json
        namespace = data.get('namespace')
        access_level = data.get('access_level')
        name = data.get('name')
        if not namespace:
            return {"message": "namespace parameter is required"}, 400
        if access_level is None:
            return {"message": "access_level parameter is required"}, 400
        try:
            level = parse_access_level(access_level)
        except ValueError as exc:
            return {"message": str(exc)}, 400
        try:
            success, message = app.update_opcua_server_node_access_level(
                namespace=namespace,
                access_level=level,
                name=name
            )
            if success:
                return {
                    "message": message,
                    "namespace": namespace,
                    "access_level": level,
                    "access_level_label": access_label(level),
                    "user_access_level": level,
                    "access_restrictions": 0,
                }, 200
            return {"message": message}, 404
        except Exception as exc:
            return {"message": f"Failed to update access level: {exc}"}, 400

