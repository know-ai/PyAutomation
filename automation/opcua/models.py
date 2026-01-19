from opcua import Client as OPCClient
from opcua import ua
from datetime import datetime
# import sched
from opcua.ua.uatypes import NodeId, datatype_to_varianttype
import re, uuid, logging, time
from ..utils import _colorize_message
import json
from enum import Enum


class Client(OPCClient):
    r"""
    Documentation here
    """
    def __init__(self, url, client_name:str, timeout=60):
        r"""
        Documentation here
        """
        self._id = None
        self._server_url = url
        self._timeout = timeout
        self.name = client_name
        self._client = None
        self._is_open = False
        self._opc_ua_tree = dict()
        # self.scheduler = sched.scheduler(time.time, time.sleep) 
        # self.token_renewal_interval = 30 # Cada 10 minutos
        super(Client, self).__init__(url, timeout)

    def get_id(self):
        r"""
        Documentation here
        """
        return self._id
    
    def is_token_valid(self): 
        try: 
            secure_channel = self.uaclient._uasocket._connection 
            token_id = secure_channel.security_token.TokenId 
            if token_id == secure_channel.next_security_token.TokenId or token_id == secure_channel.prev_security_token.TokenId: 
 
                return True
             
            else: 
                logging.error("Security token is not valid.") 
                return False 
        except Exception as e: 
            logging.error(f"Failed to check security token: {e}") 
            return False

    def connect(self):
        r"""
        Documentation here
        """
        try:
            # Connect to the server
            super(Client, self).connect()

            # Now you're connected again!
            self._is_open = True
            self._id = str(uuid.uuid4())
            result = {
                'message': 'Successful connection',
                'url': self._server_url,
                'is_connected': self._is_open,
                'id': self.get_id()
                }
            return result, 200
            
        except Exception as _err:
            str_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            logger = logging.getLogger("pyautomation")
            logger.error(f"Error during OPCUA server {self._server_url} connection")
            print(_colorize_message(f"[{str_date}] [ERROR] Error during OPCUA server {self._server_url} connection", "ERROR"))
            self._is_open = False
            result = {
                'message': 'Connection could not be established',
                'url': self._server_url,
                'is_connected': self._is_open,
                'id': self.get_id()
                }
            return result, 404
        
    def revolve_security_tokens(self): 
        logging.critical("Trying revolving security token") 
        try: 
            self.uaclient._uasocket._connection.revolve_tokens() 
            logging.critical("Security tokens revolved successfully") 
        except Exception as e: 
            logging.error(f"Failed to revolve security tokens: {e}")
        
    def reconnect(self):

        # if not self.is_connected() or not self.is_token_valid(): 
        if not self.is_connected(): 
            
            from automation import PyAutomation
            app = PyAutomation()
            str_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            app.sio.emit("on.opcua.disconnected", data={"message": f"Disconneted from {self._server_url}"})
            logging.critical(f"Attempting to reconnect to OPCUA server {self._server_url}")  
            print(_colorize_message(f"[{str_date}] [CRITICAL] Attempting to reconnect to OPCUA server {self._server_url}", "CRITICAL"))
            try:

                result, status = self.connect()
                
                if status == 200:
                    # Revolver tokens de seguridad para asegurar la validez 
                    # self.revolve_security_tokens()
                    app.sio.emit("on.opcua.connected", data={"message": f"Conneted to {self._server_url}"})
                    tags = app.get_tags()
                    for tag in tags:
                        _tag = app.cvt.get_tag(id=tag["id"])
                        app.subscribe_opcua(tag=_tag, opcua_address=tag['opcua_address'], node_namespace=tag['node_namespace'], scan_time=tag['scan_time'], reload=True)
                        
                    logging.critical(f"Reconnected to {self._server_url}") 
                    print(_colorize_message(f"[{str_date}] [INFO] Reconnected to OPCUA server {self._server_url}", "INFO"))
            except: 
                logging.critical(f"Reconnection to OPCUA server {self._server_url} failed...")
                print(_colorize_message(f"[{str_date}] [CRITICAL] Reconnection to OPCUA server {self._server_url} failed...", "CRITICAL"))

    def __reset_object_attributes(self):
        r"""
        Documentation here
        """
        self._server_url = None
        self._client = None
        self._opc_ua_tree = dict()

    def disconnect(self):
        r"""
        Documentation here
        """
        try:
            super(Client, self).disconnect()
            self.__reset_object_attributes()
            result = {
                'message': 'Successful disconnection',
                'is_connected': False
                }
            return result, 200

        except Exception as _err:
            result = {'message': 'Disconnect could not be performed'}
            return result, 404

    def get_opc_ua_tree(self):
        r"""
        Documentation here
        """
        try:
            if self.is_connected():
                root = self.get_objects_node()
                node = self.get_node(root)
                tree = self.__walk_into_nodes(node)
                return tree, 200

        except Exception as _err:
            self.disconnect()
            result = { 'message': str(_err)}
            return result, 500

    def __walk_into_nodes(self, node, tree=None):
        r"""
        Documentation here
        """
        if tree is None:

            tree = dict()

        _object = list()

        if self.is_connected():

            for ref in node.get_children_descriptions():

                _node = self.get_node(ref.NodeId)
                # ('Aliases', 'MyObjects', 'Server', 'StaticData')

                if _node.get_browse_name().Name not in ('Aliases', 'MyObjects', 'Server', 'StaticData'):

                    result = self.__opc_ua_tree(ref.NodeId)

                    if _node.get_children():

                        _children = self.__get_children_node_recursively(_node)

                        result['children'] = _children
                    
                    _object.append(result)

            tree[f"{node.get_browse_name().Name}"] = _object

            return tree

    def __get_children_node_recursively(self, node, children=None):
        r"""
        Documentation here
        """

        if children is None:

            children = list()
        if self.is_connected():
            for child in node.get_children():

                result = self.__opc_ua_tree(child.nodeid)

                if child.get_children():

                    _children = self.__get_children_node_recursively(child)

                    result['children'] = _children

                children.append(result)            

            return children

    def __opc_ua_tree(self, namespace_node):
        r"""
        Documentation here
        """
        if self.is_connected():
            _node = self.get_node(namespace_node)

            result = {
                "title": _node.get_browse_name().Name,
                "key": _node.nodeid.to_string(),
                "children": [],
                "NodeClass": _node.get_node_class().name,
            }

            return result

    def get_values(self, nodes:list):
        r"""
        Documentation here
        """
        if self.is_connected(): 
            results = self.uaclient.get_attributes(nodes, ua.AttributeIds.Value)
            result = [{"Namespace": nodes[id].to_string(), "Value": result.Value.Value, "Timestamp": result.SourceTimestamp} for id, result in enumerate(results)]
            
            return result, 200

    def get_nodes_id_by_namespaces(self, namespaces:list):
        r"""
        Documentar here
        """
        nodes = list()

        for namespace in namespaces:
            if self.is_connected():
                _node = self.get_node(NodeId.from_string(namespace))
                nodes.append(_node)

        return nodes
    
    def get_node_id_by_namespace(self, namespace:str):
        r"""
        Documentar here
        """
        if self.is_connected():
            return self.get_node(NodeId.from_string(namespace))

    def get_nodes_values(self, namespaces:list)->list:
        r"""
        Documentation here
        """
        result = list()
        nodes = list()

        for namespace in namespaces:
            if self.is_connected():
                _node = self.get_node(NodeId.from_string(namespace))
                nodes.append(_node)
                    
                if _node.get_node_class().name.lower()=='variable':
                    node = {
                        "Namespace": namespace,
                        "Value": _node.get_value()
                        }
                    result.append(node)

        return result

    def write_value(self, node_namespace: str, value):
        r"""
        Escribe un valor en un nodo variable del servidor OPC UA
        
        Args:
            node_namespace: Namespace del nodo en formato string (ej: "ns=2;i=1234")
            value: Valor a escribir (el tipo debe ser compatible con el nodo)
        
        Returns:
            tuple: (dict con resultado, status_code)
        """
        try:
            if not self.is_connected():
                return {
                    'message': 'Cliente no conectado al servidor',
                    'namespace': node_namespace,
                    'success': False
                }, 400
            
            _node = self.get_node(NodeId.from_string(node_namespace))
            
            # Verificar que es un nodo variable
            if _node.get_node_class().name.lower() != 'variable':
                return {
                    'message': f'El nodo no es de tipo Variable, es {_node.get_node_class().name}',
                    'namespace': node_namespace,
                    'success': False
                }, 400
            
            # Verificar permisos de escritura
            access_level = _node.get_access_level()
            user_access_level = _node.get_user_access_level()
            
            # Escribir el valor
            _node.set_value(value)
            
            result = {
                'message': 'Valor escrito exitosamente',
                'namespace': node_namespace,
                'value': value,
                'success': True
            }
            return result, 200
            
        except Exception as err:
            logger = logging.getLogger("pyautomation")
            logger.error(f"Error escribiendo valor en {node_namespace}: {err}")
            result = {
                'message': f'Error al escribir valor: {str(err)}',
                'namespace': node_namespace,
                'success': False
            }
            return result, 500

    @staticmethod
    def find_servers(hostname, port):
        r"""
        Documentation here
        """
        str_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        try:
            logging.info(f"Searching OPCUA servers in opc.tcp://{hostname}:{port}")
            print(_colorize_message(f"[{str_date}] [INFO] Searching OPCUA servers in opc.tcp://{hostname}:{port}", "INFO"))
            _client = OPCClient(f'opc.tcp://{hostname}:{port}')
            servers = _client.connect_and_find_servers()
            logging.info(f"OPCUA servers found: {len(servers)}")
            print(_colorize_message(f"[{str_date}] [INFO] OPCUA servers found: {len(servers)}", "INFO"))
        except Exception as err:
            logging.error(f"Error searching OPCUA servers in opc.tcp://{hostname}:{port}, Make sure the server is running and the port is correct")
            print(_colorize_message(f"[{str_date}] [ERROR] Error searching OPCUA servers in opc.tcp://{hostname}:{port}, Make sure the server is running and the port is correct", "ERROR"))
            
        _servers = list()
        if _servers:
            for server in _servers:
                _server = dict()
                _server['ApplicationUri'] = server.ApplicationUri
                _server['ProductUri'] = server.ProductUri
                _server['ApplicationName'] = server.ApplicationName.Text
                _server['ApplicationType'] = server.ApplicationType.Server
                _server['GatewayServerUri'] = server.GatewayServerUri
                _server['DiscoveryProfileUri'] = server.DiscoveryProfileUri
                _server['DiscoveryUrls'] = server.DiscoveryUrls
                _servers.append(_server)


        return _servers

    @staticmethod
    def get_endpoints(hostname, port):
        r"""
        Documentation here
        """
        try:
            _client = OPCClient(f'opc.tcp://{hostname}:{port}')
            endpoints = _client.connect_and_get_server_endpoints()
            _endpoints = list()
            for ep in endpoints:

                if isinstance(ep.Server.DiscoveryUrls, list):
                    
                    _endpoints.extend(ep.Server.DiscoveryUrls)
                
                else:

                    _endpoints.append(ep.Server.DiscoveryUrls)

            _endpoints = list(set(_endpoints))

            for ep in _endpoints:
                if not ep.startswith('opc.tcp'):
                    _endpoints.remove(ep)

            result = [re.sub('//.*?/',f'//{hostname}:{port}/', __ep) for __ep in _endpoints]
            result = {
                'message': 'Successful search',
                'endpoints': result
            }

            return result, 200
            
        except Exception as err:

            result = {
                'message': 'Unsuccessful search',
                'endpoints': []
            }
            return result, 400

    def is_connected(self):
        r"""
        Documentation here
        """
        try:
            return self.uaclient._uasocket._connection.is_open() 
        
        except Exception as _err:

            return False

    def get_node_attributes(self, node_namespace)->dict:
        r"""
        Documentation here
        """
        if self.is_connected():
            _node = self.get_node(NodeId.from_string(node_namespace))

            node_class = _node.get_node_class().name.lower()

            if node_class=='variable':

                result = {
                    "NamespaceIndex": _node.nodeid.NamespaceIndex,
                    "NamespaceUri": _node.nodeid.NamespaceUri,
                    "Identifier": _node.nodeid.Identifier,
                    "Namespace": _node.nodeid.to_string(),
                    "NodeClass": _node.get_node_class().name,
                    "BrowseName": _node.get_browse_name().Name,
                    "DataValue": _node.get_data_value(),
                    "DisplayName": _node.get_display_name().Text,
                    "DataType": datatype_to_varianttype(_node.get_data_type()).name,
                    "AccesLevel": [access_lvl.name for access_lvl in _node.get_access_level()],
                    "UserAccessLevel": [user_access_lvl.name for user_access_lvl in _node.get_user_access_level()],
                    "Description": _node.get_description().Text if _node.get_description() else None,
                    "Value": _node.get_value(),
                    "ArrayDimensions": _node.get_array_dimensions(),
                    "ValueRank": _node.get_value_rank().name
                }

            else:

                result = {
                    "NamespaceIndex": _node.nodeid.NamespaceIndex,
                    "NamespaceUri": _node.nodeid.NamespaceUri,
                    "Identifier": _node.nodeid.Identifier,
                    "Namespace": _node.nodeid.to_string(),
                    "NodeClass": _node.get_node_class().name,
                    "BrowseName": _node.get_browse_name().Name,
                    "DisplayName": _node.get_display_name().Text,
                    "Description": _node.get_description().Text if _node.get_description() else ''
                }

            return result, 200
        
        return {}, 400
    
    def get_nodes_attributes(self, namespaces:list)->list:
        r"""
        Documentation here
        """
        nodes = list()
        for namespace in namespaces:
            if self.is_connected():
                node = self.get_node_attributes(node_namespace=namespace)
                nodes.append(node)

        return nodes

    def get_referenced_nodes(self, node_id):
        r"""
        Documentation here
        """
        result = list()
        if self.is_connected():
            _node = self.get_node(NodeId.from_string(node_id))
            referenced_nodes = _node.get_referenced_nodes()
            
            for count, node in  enumerate(referenced_nodes):

                node_name = node.get_browse_name().Name
                if count==0:
                    result.append(('OrganizedBy', node_name))
                elif count==1:
                    result.append(('HasTypeDefinition', node_name))
                else:
                    result.append(('Organizes', node_name))

            return result, 200
        
        return result, 400

    def browse_tree(self, node):
        children_list = []
        if self.is_connected():
            if node.get_node_class() == ua.NodeClass.Object:
                children = node.get_children()
                for child_id in children:
                    child_node = self.get_node(child_id)
                    display_name = child_node.get_display_name().Text or "Unnamed Node"
                    if display_name not in ('Aliases', 'MyObjects', 'Server', 'StaticData', 'Types', 'ReferenceTypes', 'EventTypes', 'InterfaceTypes', 'Views'):
                        child_dict = {
                            "title": display_name,
                            "key": child_node.nodeid.to_string(),
                            "NodeClass": child_node.get_node_class().name,
                            "children": self.browse_tree(child_node) if child_node.get_node_class() == ua.NodeClass.Object else []
                        }
                        if child_node.get_node_class() == ua.NodeClass.Variable:
                            variable_info = {
                                "title": display_name,
                                "key": child_node.nodeid.to_string(),
                                "NodeClass": child_node.get_node_class().name,
                                "children": []
                            }
                            for prop_id in child_node.get_properties():
                                prop_node = self.get_node(prop_id)
                                prop_display_name = prop_node.get_display_name().Text or "Unnamed Property"
                                try:
                                    prop_dict = {
                                        "title": prop_display_name,
                                        "key": prop_node.nodeid.to_string(),
                                        "NodeClass": prop_node.get_node_class().name,
                                        "value": self._to_jsonable(prop_node.get_value()),
                                        "children": []
                                    }
                                    variable_info["children"].append(prop_dict)
                                except ua.uaerrors.BadWaitingForInitialData:
                                    variable_info["children"].append({
                                        "title": prop_display_name,
                                        "key": prop_node.nodeid.to_string(),
                                        "NodeClass": prop_node.get_node_class().name,
                                        "value": None,
                                        "children": []
                                    })
                            child_dict = variable_info
                        children_list.append(child_dict)
        return children_list

    @staticmethod
    def _to_jsonable(value, _visited=None):
        """
        Convierte tipos OPC UA (y objetos complejos) a estructuras JSON-serializables.

        Se usa para evitar errores como:
        TypeError: Object of type Range is not JSON serializable
        """
        if _visited is None:
            _visited = set()

        # evitar ciclos
        obj_id = id(value)
        if obj_id in _visited:
            return None
        _visited.add(obj_id)

        try:
            json.dumps(value)
            _visited.remove(obj_id)
            return value
        except Exception:
            pass

        if value is None:
            _visited.remove(obj_id)
            return None

        # datetime
        if isinstance(value, datetime):
            _visited.remove(obj_id)
            return value.isoformat()

        # bytes
        if isinstance(value, (bytes, bytearray)):
            _visited.remove(obj_id)
            return value.hex()

        # enums
        if isinstance(value, Enum):
            _visited.remove(obj_id)
            return value.name

        # NodeId / ua types comunes
        if isinstance(value, NodeId):
            _visited.remove(obj_id)
            return value.to_string()

        # python-opcua: Range (EngineeringUnitsRange)
        # suele tener atributos Low/High
        if hasattr(value, "Low") and hasattr(value, "High"):
            try:
                out = {"Low": Client._to_jsonable(value.Low, _visited), "High": Client._to_jsonable(value.High, _visited)}
                _visited.remove(obj_id)
                return out
            except Exception:
                pass

        # LocalizedText
        if hasattr(value, "Text") and hasattr(value, "Locale"):
            try:
                out = {"Text": value.Text, "Locale": value.Locale}
                _visited.remove(obj_id)
                return out
            except Exception:
                pass

        # QualifiedName
        if hasattr(value, "Name") and hasattr(value, "NamespaceIndex"):
            try:
                out = {"Name": value.Name, "NamespaceIndex": int(value.NamespaceIndex)}
                _visited.remove(obj_id)
                return out
            except Exception:
                pass

        # list / tuple
        if isinstance(value, (list, tuple)):
            out = [Client._to_jsonable(v, _visited) for v in value]
            _visited.remove(obj_id)
            return out

        # dict
        if isinstance(value, dict):
            out = {str(k): Client._to_jsonable(v, _visited) for k, v in value.items()}
            _visited.remove(obj_id)
            return out

        # objetos con atributos públicos
        if hasattr(value, "__dict__"):
            try:
                out = {}
                for k, v in value.__dict__.items():
                    if str(k).startswith("_"):
                        continue
                    out[str(k)] = Client._to_jsonable(v, _visited)
                _visited.remove(obj_id)
                return out
            except Exception:
                pass

        # fallback
        _visited.remove(obj_id)
        return str(value)

    def browse_tree_generic(
        self,
        node,
        *,
        max_depth: int = 10,
        max_nodes: int = 50_000,
        include_properties: bool = True,
        include_property_values: bool = False,
        _depth: int = 0,
        _visited_nodeids=None,
        _count=None,
    ):
        """
        Browse genérico del address space, robusto para cualquier servidor OPC UA.

        - Evita ciclos (visited por NodeId)
        - Limita profundidad y cantidad total de nodos (protección performance)
        - Mantiene compatibilidad con el formato que consume el frontend: title/key/NodeClass/children
        """
        if _visited_nodeids is None:
            _visited_nodeids = set()
        if _count is None:
            _count = {"n": 0}

        if not self.is_connected():
            return []
        if _depth > max_depth:
            return []
        if _count["n"] >= max_nodes:
            return []

        children_list = []
        try:
            children = node.get_children()
        except Exception:
            return []

        for child_id in children:
            if _count["n"] >= max_nodes:
                break

            try:
                child_node = self.get_node(child_id)
                nid = child_node.nodeid.to_string()
            except Exception:
                continue

            if nid in _visited_nodeids:
                continue
            _visited_nodeids.add(nid)
            _count["n"] += 1

            try:
                display_name = child_node.get_display_name().Text or child_node.get_browse_name().Name or "Unnamed Node"
            except Exception:
                display_name = "Unnamed Node"

            try:
                node_class = child_node.get_node_class().name
            except Exception:
                node_class = "Unknown"

            # determinar si tiene hijos (sin depender de si estamos por debajo del max_depth)
            has_children = False
            try:
                child_children = child_node.get_children()
                has_children = bool(child_children)
            except Exception:
                child_children = []

            # Variables pueden exponer properties (EURange/EngineeringUnits/etc.) aunque no tengan children "normales"
            if include_properties:
                try:
                    if child_node.get_node_class() == ua.NodeClass.Variable:
                        has_children = has_children or bool(child_node.get_properties())
                except Exception:
                    pass

            node_dict = {
                "title": display_name,
                "key": nid,
                "NodeClass": node_class,
                "children": [],
                "has_children": bool(has_children),
            }

            # Recursión: Objects (y algunos servers exponen estructuras bajo Variable/ObjectType)
            try:
                if _depth < max_depth and child_children:
                    node_dict["children"] = self.browse_tree_generic(
                        child_node,
                        max_depth=max_depth,
                        max_nodes=max_nodes,
                        include_properties=include_properties,
                        include_property_values=include_property_values,
                        _depth=_depth + 1,
                        _visited_nodeids=_visited_nodeids,
                        _count=_count,
                    )
            except Exception:
                node_dict["children"] = []

            # Propiedades para variables (EURange, EngineeringUnits, etc.)
            if include_properties:
                try:
                    if child_node.get_node_class() == ua.NodeClass.Variable:
                        for prop_id in child_node.get_properties():
                            if _count["n"] >= max_nodes:
                                break
                            prop_node = self.get_node(prop_id)
                            prop_nid = prop_node.nodeid.to_string()
                            if prop_nid in _visited_nodeids:
                                continue
                            _visited_nodeids.add(prop_nid)
                            _count["n"] += 1

                            prop_name = prop_node.get_display_name().Text or prop_node.get_browse_name().Name or "Unnamed Property"
                            prop_dict = {
                                "title": prop_name,
                                "key": prop_nid,
                                "NodeClass": prop_node.get_node_class().name,
                                "children": [],
                            }
                            if include_property_values:
                                try:
                                    prop_dict["value"] = self._to_jsonable(prop_node.get_value())
                                except Exception:
                                    prop_dict["value"] = None
                            node_dict["children"].append(prop_dict)
                except Exception:
                    pass

            children_list.append(node_dict)

        return children_list

    def browse_children_generic(
        self,
        node,
        *,
        max_nodes: int = 5_000,
        include_properties: bool = True,
        include_property_values: bool = False,
    ):
        """
        Devuelve SOLO los hijos directos de un nodo (sin recursión).

        Útil para lazy-loading desde el HMI al expandir carpetas profundas.
        """
        if not self.is_connected():
            return []

        out = []
        visited = set()
        count = 0

        try:
            children = node.get_children()
        except Exception:
            children = []

        for child_id in children:
            if count >= max_nodes:
                break
            try:
                child_node = self.get_node(child_id)
                nid = child_node.nodeid.to_string()
            except Exception:
                continue

            if nid in visited:
                continue
            visited.add(nid)
            count += 1

            try:
                display_name = child_node.get_display_name().Text or child_node.get_browse_name().Name or "Unnamed Node"
            except Exception:
                display_name = "Unnamed Node"

            try:
                node_class = child_node.get_node_class().name
            except Exception:
                node_class = "Unknown"

            # ¿tiene hijos?
            has_children = False
            try:
                has_children = bool(child_node.get_children())
            except Exception:
                has_children = False

            # properties en variables
            if include_properties:
                try:
                    if child_node.get_node_class() == ua.NodeClass.Variable:
                        has_children = has_children or bool(child_node.get_properties())
                except Exception:
                    pass

            node_dict = {
                "title": display_name,
                "key": nid,
                "NodeClass": node_class,
                "children": [],
                "has_children": bool(has_children),
            }
            out.append(node_dict)

        # Adjuntar properties del nodo si es Variable (como hijos directos)
        if include_properties:
            try:
                if node.get_node_class() == ua.NodeClass.Variable:
                    for prop_id in node.get_properties():
                        if count >= max_nodes:
                            break
                        prop_node = self.get_node(prop_id)
                        prop_nid = prop_node.nodeid.to_string()
                        if prop_nid in visited:
                            continue
                        visited.add(prop_nid)
                        count += 1

                        prop_name = prop_node.get_display_name().Text or prop_node.get_browse_name().Name or "Unnamed Property"
                        prop_dict = {
                            "title": prop_name,
                            "key": prop_nid,
                            "NodeClass": prop_node.get_node_class().name,
                            "children": [],
                            "has_children": False,
                        }
                        if include_property_values:
                            try:
                                prop_dict["value"] = self._to_jsonable(prop_node.get_value())
                            except Exception:
                                prop_dict["value"] = None
                        out.append(prop_dict)
            except Exception:
                pass

        return out

    def serialize(self):
        r"""
        Documentation here
        """
        return {
            'client_id': self.get_id(),
            'server_url': self._server_url,
            'timeout': self._timeout,
            'is_opened': self.is_connected()
        }