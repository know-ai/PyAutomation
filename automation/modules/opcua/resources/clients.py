from flask import request
from flask_restx import Namespace, Resource, fields, reqparse
from .... import PyAutomation
from ....extensions.api import api
from ....extensions import _api as Api
import json
from datetime import datetime


ns = Namespace('OPCUA Clients', description='OPC UA Client Management Resources')
app = PyAutomation()

# Models
add_client_model = api.model("add_client_model", {
    'client_name': fields.String(required=True, description='Unique name for the OPC UA client'),
    'host': fields.String(required=False, description='OPC UA server host/IP address', default='127.0.0.1'),
    'port': fields.Integer(required=False, description='OPC UA server port', default=4840)
})

namespaces_model = api.model("namespaces_model", {
    'namespaces': fields.List(fields.String, required=True, description='List of node namespaces/IDs to read')
})

# Parsers
add_client_parser = reqparse.RequestParser()
add_client_parser.add_argument('client_name', type=str, required=True, help='Unique name for the OPC UA client')
add_client_parser.add_argument('host', type=str, required=False, help='OPC UA server host/IP address', default='127.0.0.1')
add_client_parser.add_argument('port', type=int, required=False, help='OPC UA server port', default=4840)

namespaces_parser = reqparse.RequestParser()
namespaces_parser.add_argument('namespaces', type=list, location='args', required=True, help='List of node namespaces/IDs to read (comma-separated or as array)')


def extract_primitive_value(value, visited=None):
    """
    Recursively extracts primitive values from OPC UA objects.
    Explores the structure of complex objects to get all primitive data types.
    """
    if visited is None:
        visited = set()
    
    # Avoid circular references
    obj_id = id(value)
    if obj_id in visited:
        return None
    visited.add(obj_id)
    
    try:
        # If it's already a primitive JSON-serializable type, return it
        json.dumps(value)
        visited.remove(obj_id)
        return value
    except (TypeError, ValueError):
        pass
    
    # Handle None
    if value is None:
        visited.remove(obj_id)
        return None
    
    # Handle datetime objects
    if isinstance(value, datetime):
        visited.remove(obj_id)
        return value.isoformat()
    
    # Handle lists and tuples
    if isinstance(value, (list, tuple)):
        result = [extract_primitive_value(item, visited) for item in value]
        visited.remove(obj_id)
        return result
    
    # Handle dictionaries
    if isinstance(value, dict):
        result = {}
        for k, v in value.items():
            result[k] = extract_primitive_value(v, visited)
        visited.remove(obj_id)
        return result
    
    # Handle DataValue objects from OPC UA
    if hasattr(value, '__class__') and 'DataValue' in str(value.__class__):
        data_value_dict = {}
        try:
            # Extract Value (Variant)
            if hasattr(value, 'Value') and value.Value:
                if hasattr(value.Value, 'Value'):
                    data_value_dict['Value'] = extract_primitive_value(value.Value.Value, visited)
                else:
                    data_value_dict['Value'] = extract_primitive_value(value.Value, visited)
            else:
                data_value_dict['Value'] = None
            
            # Extract SourceTimestamp
            if hasattr(value, 'SourceTimestamp'):
                ts = value.SourceTimestamp
                data_value_dict['SourceTimestamp'] = ts.isoformat() if ts else None
            else:
                data_value_dict['SourceTimestamp'] = None
            
            # Extract ServerTimestamp
            if hasattr(value, 'ServerTimestamp'):
                ts = value.ServerTimestamp
                data_value_dict['ServerTimestamp'] = ts.isoformat() if ts else None
            else:
                data_value_dict['ServerTimestamp'] = None
            
            # Extract StatusCode
            if hasattr(value, 'StatusCode'):
                sc = value.StatusCode
                if hasattr(sc, 'name'):
                    data_value_dict['StatusCode'] = sc.name
                elif hasattr(sc, 'value'):
                    data_value_dict['StatusCode'] = sc.value
                else:
                    data_value_dict['StatusCode'] = str(sc)
            else:
                data_value_dict['StatusCode'] = None
        except Exception as e:
            # If extraction fails, return a string representation
            data_value_dict = {'error': f'Failed to extract DataValue: {str(e)}'}
        
        visited.remove(obj_id)
        return data_value_dict
    
    # Handle Variant objects
    if hasattr(value, '__class__') and 'Variant' in str(value.__class__):
        if hasattr(value, 'Value'):
            result = extract_primitive_value(value.Value, visited)
            visited.remove(obj_id)
            return result
    
    # Handle LocalizedText objects
    if hasattr(value, 'Text'):
        result = value.Text
        visited.remove(obj_id)
        return result
    
    # Handle NodeId objects
    if hasattr(value, 'to_string'):
        result = value.to_string()
        visited.remove(obj_id)
        return result
    
    # Handle enum-like objects (StatusCode, NodeClass, ValueRank, etc.)
    if hasattr(value, 'name'):
        result = value.name
        visited.remove(obj_id)
        return result
    
    # Handle objects with __dict__ - recursively extract all attributes
    if hasattr(value, '__dict__'):
        result = {}
        try:
            for attr_name, attr_value in value.__dict__.items():
                # Skip private attributes
                if not attr_name.startswith('_'):
                    result[attr_name] = extract_primitive_value(attr_value, visited)
            visited.remove(obj_id)
            return result
        except Exception:
            pass
    
    # Fallback: try to get common OPC UA attributes
    result = {}
    common_attrs = ['Value', 'Text', 'name', 'to_string', 'SourceTimestamp', 'ServerTimestamp', 'StatusCode']
    for attr in common_attrs:
        if hasattr(value, attr):
            try:
                attr_value = getattr(value, attr)
                if callable(attr_value) and attr != 'to_string':
                    continue
                if attr == 'to_string':
                    result[attr] = attr_value()
                else:
                    result[attr] = extract_primitive_value(attr_value, visited)
            except:
                pass
    
    if result:
        visited.remove(obj_id)
        return result
    
    # Final fallback: string representation
    visited.remove(obj_id)
    return str(value) if value is not None else None


def serialize_opcua_attributes(attributes):
    """
    Serializes OPC UA attributes to JSON-serializable format.
    Extracts all primitive values from complex OPC UA objects like DataValue.
    Handles tuples returned by get_node_attributes.
    Filters out empty dicts (nodes that don't exist).
    """
    serialized = []
    
    for attr in attributes:
        # Handle tuple (dict, status_code) returned by get_node_attributes
        if isinstance(attr, tuple) and len(attr) == 2:
            attr_dict = attr[0]
        elif isinstance(attr, dict):
            attr_dict = attr
        else:
            continue
        
        # Skip empty dicts (nodes that don't exist or had errors)
        if not attr_dict:
            continue
        
        # Recursively extract all primitive values from the dictionary
        serialized_attr = extract_primitive_value(attr_dict)
        # Only add non-empty serialized attributes
        if serialized_attr:
            serialized.append(serialized_attr)
    
    return serialized


@ns.route('/')
class OPCUAClientsCollection(Resource):

    @api.doc(security='apikey', description="Retrieves all configured OPC UA clients.")
    @api.response(200, "Success")
    @Api.token_required(auth=True)
    def get(self):
        """
        Get all OPC UA clients.

        Retrieves a dictionary of all configured OPC UA clients with their connection information.
        """
        return app.get_opcua_clients(), 200


@ns.route('/add')
class AddOPCUAClientResource(Resource):

    @api.doc(security='apikey', description="Adds and connects a new OPC UA client.")
    @api.response(200, "Client added successfully")
    @api.response(400, "Client addition failed")
    @Api.token_required(auth=True)
    @ns.expect(add_client_model)
    def post(self):
        """
        Add OPC UA client.

        Registers and connects a new OPC UA client to the specified server.
        """
        args = add_client_parser.parse_args()
        result = app.add_opcua_client(
            client_name=args['client_name'],
            host=args.get('host', '127.0.0.1'),
            port=args.get('port', 4840)
        )
        
        if result:
            success, message_or_data = result
            if success:
                return {
                    'message': f"OPC UA client '{args['client_name']}' added successfully",
                    'data': message_or_data if isinstance(message_or_data, dict) else {'message': message_or_data}
                }, 200
            else:
                return {
                    'message': f"Failed to add OPC UA client: {message_or_data}"
                }, 400
        
        return {
            'message': f"Failed to discover OPC UA server at {args.get('host', '127.0.0.1')}:{args.get('port', 4840)}"
        }, 400


@ns.route('/remove/<client_name>')
@api.param('client_name', 'The OPC UA client name to remove')
class RemoveOPCUAClientResource(Resource):

    @api.doc(security='apikey', description="Removes an OPC UA client.")
    @api.response(200, "Client removed successfully")
    @api.response(400, "Client removal failed")
    @Api.token_required(auth=True)
    def delete(self, client_name):
        """
        Remove OPC UA client.

        Disconnects and removes an OPC UA client configuration.
        """
        success = app.remove_opcua_client(client_name=client_name)
        
        if success:
            return {
                'message': f"OPC UA client '{client_name}' removed successfully"
            }, 200
        
        return {
            'message': f"OPC UA client '{client_name}' not found or failed to remove"
        }, 400


@ns.route('/tree/<client_name>')
@api.param('client_name', 'The OPC UA client name')
class OPCUAClientTreeResource(Resource):

    @api.doc(security='apikey', description="Retrieves the hierarchical node tree structure from a connected OPC UA server.")
    @api.response(200, "Success")
    @api.response(400, "Client not found")
    @Api.token_required(auth=True)
    def get(self, client_name):
        """
        Get OPC UA client node tree.

        Retrieves the hierarchical node tree structure from a connected OPC UA server.
        """
        try:
            tree = app.get_opcua_tree(client_name=client_name)
            return tree, 200
        except Exception as e:
            return {
                'message': f"Failed to retrieve node tree for client '{client_name}': {str(e)}"
            }, 400


@ns.route('/attrs/<client_name>')
@api.param('client_name', 'The OPC UA client name')
class OPCUAClientAttributesResource(Resource):

    @api.doc(security='apikey', description="Reads attributes from multiple OPC UA nodes.")
    @api.response(200, "Success")
    @api.response(400, "Client not found or invalid request")
    @Api.token_required(auth=True)
    @ns.expect(namespaces_model)
    def post(self, client_name):
        """
        Get node attributes.

        Reads attributes (e.g., Description, DataType) from multiple nodes using the specified OPC UA client.
        Requires namespaces list in request body as JSON array.
        """
        if not request.is_json:
            return {
                'message': "Request must be JSON with 'namespaces' array"
            }, 400
        
        data = request.json
        namespaces = data.get('namespaces')
        
        if not namespaces:
            return {
                'message': "namespaces parameter is required in request body as array"
            }, 400
        
        if not isinstance(namespaces, list):
            return {
                'message': "namespaces must be an array/list"
            }, 400
        
        if len(namespaces) == 0:
            return {
                'message': "namespaces array cannot be empty"
            }, 400
        
        try:
            attributes = app.get_node_attributes(client_name=client_name, namespaces=namespaces)
            # Serialize all attributes to JSON-serializable format
            serialized_attributes = serialize_opcua_attributes(attributes)
            return {
                'data': serialized_attributes
            }, 200
        except Exception as e:
            return {
                'message': f"Failed to read node attributes for client '{client_name}': {str(e)}"
            }, 400


@ns.route('/values/<client_name>')
@api.param('client_name', 'The OPC UA client name')
class OPCUAClientValuesResource(Resource):

    @api.doc(security='apikey', description="Reads values from multiple OPC UA nodes for polling.")
    @api.response(200, "Success")
    @api.response(400, "Client not found or invalid request")
    @Api.token_required(auth=True)
    @ns.expect(namespaces_model)
    def post(self, client_name):
        """
        Get node values.

        Reads values from multiple nodes using the specified OPC UA client. 
        Used for polling time and updating in the explorer.
        Requires namespaces list in request body as JSON array.
        """
        if not request.is_json:
            return {
                'message': "Request must be JSON with 'namespaces' array"
            }, 400
        
        data = request.json
        namespaces = data.get('namespaces')
        
        if not namespaces:
            return {
                'message': "namespaces parameter is required in request body as array"
            }, 400
        
        if not isinstance(namespaces, list):
            return {
                'message': "namespaces must be an array/list"
            }, 400
        
        if len(namespaces) == 0:
            return {
                'message': "namespaces array cannot be empty"
            }, 400
        
        try:
            values = app.get_node_values(client_name=client_name, namespaces=namespaces)
            # Extract all primitive values recursively from OPC UA objects
            serialized_values = [extract_primitive_value(value) for value in values]
            
            return {
                'data': serialized_values
            }, 200
        except Exception as e:
            return {
                'message': f"Failed to read node values for client '{client_name}': {str(e)}"
            }, 400

