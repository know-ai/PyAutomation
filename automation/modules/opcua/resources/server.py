from flask import request
from flask_restx import Namespace, Resource, fields
from .... import PyAutomation
from ....extensions.api import api
from ....extensions import _api as Api


ns = Namespace('OPCUA Server', description='OPC UA Server Management Resources')
app = PyAutomation()

# Models
update_access_type_model = api.model("update_access_type_model", {
    'namespace': fields.String(required=True, description='OPC UA node namespace string'),
    'access_type': fields.String(required=True, description='Access type: Read, Write, or ReadWrite'),
    'name': fields.String(required=False, description='Node name (optional, used if record does not exist)')
})


@ns.route('/attrs')
class OPCUAServerAttributesResource(Resource):

    @api.doc(security='apikey', description="Retrieves all attributes (variables and properties) from the OPC UA Server state machine.")
    @api.response(200, "Success")
    @api.response(404, "OPC UA Server not found")
    @Api.token_required(auth=True)
    def get(self):
        r"""
        Get OPC UA Server attributes.

        Retrieves all OPC UA nodes (variables and their properties) from the embedded OPC UA Server
        with their access levels (Read, Write, ReadWrite).

        Returns a list of dictionaries containing:
        - name: Full path name (parent_folder.variable_name or parent_folder.variable_name.property_name)
        - namespace: OPC UA node namespace string
        - access_type: Access level ("Read", "Write", or "ReadWrite")
        """
        try:
            attrs = app.get_opcua_server_attrs()
            return {
                "data": attrs
            }, 200
        except Exception as e:
            return {
                "message": f"Failed to retrieve OPC UA Server attributes: {str(e)}"
            }, 404


@ns.route('/attrs/update')
class OPCUAServerUpdateAccessTypeResource(Resource):

    @api.doc(security='apikey', description="Updates the access type (Read, Write, ReadWrite) for a specific OPC UA Server node.")
    @api.response(200, "Access type updated successfully")
    @api.response(400, "Invalid request or parameters")
    @api.response(404, "Node not found")
    @Api.token_required(auth=True)
    @ns.expect(update_access_type_model)
    def put(self):
        r"""
        Update OPC UA Server node access type.

        Updates the access level for a specific OPC UA Server node identified by its namespace.
        The access_type must be one of: "Read", "Write", or "ReadWrite".

        Request body:
        - namespace: OPC UA node namespace string (required)
        - access_type: New access type - "Read", "Write", or "ReadWrite" (required)
        - name: Node name (optional, used if database record does not exist)
        """
        if not request.is_json:
            return {
                "message": "Request must be JSON"
            }, 400
        
        data = request.json
        namespace = data.get('namespace')
        access_type = data.get('access_type')
        name = data.get('name')
        
        if not namespace:
            return {
                "message": "namespace parameter is required"
            }, 400
        
        if not access_type:
            return {
                "message": "access_type parameter is required"
            }, 400
        
        if access_type not in ["Read", "Write", "ReadWrite"]:
            return {
                "message": "access_type must be one of: 'Read', 'Write', or 'ReadWrite'"
            }, 400
        
        try:
            success, message = app.update_opcua_server_node_access_type(
                namespace=namespace,
                access_type=access_type,
                name=name
            )
            
            if success:
                return {
                    "message": message,
                    "namespace": namespace,
                    "access_type": access_type
                }, 200
            else:
                return {
                    "message": message
                }, 404
        except Exception as e:
            return {
                "message": f"Failed to update access type: {str(e)}"
            }, 400

