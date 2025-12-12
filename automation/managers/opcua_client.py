from ..opcua.models import Client
from ..dbmodels import OPCUA
from ..logger.datalogger import DataLoggerEngine
from ..tags import CVTEngine
from ..utils.decorators import logging_error_handler
from ..opcua.subscription import DAS

class OPCUAClientManager:
    r"""
    Manages multiple OPC UA Client connections and their subscriptions.

    It handles client lifecycle (add, remove, connect, disconnect), server discovery,
    and reading/writing values to OPC UA nodes.
    """

    def __init__(self):
        r"""
        Initializes the OPC UA Client Manager.
        """
        self._clients = dict()
        self.logger = DataLoggerEngine()
        self.cvt = CVTEngine()
        self.das = DAS()

    @logging_error_handler
    def discovery(self, host:str='127.0.0.1', port:int=4840)->list[dict]:
        r"""
        Discovers available OPC UA servers on a given host and port.

        **Parameters:**

        * **host** (str): IP address or hostname.
        * **port** (int): Port number.

        **Returns:**

        * **list[dict]**: Discovery results.
        """
        return Client.find_servers(host, port)

    @logging_error_handler
    def add(self, client_name:str, host:str, port:int):
        r"""
        Adds and connects a new OPC UA Client.

        **Parameters:**

        * **client_name** (str): Unique name for the client.
        * **host** (str): Server host.
        * **port** (int): Server port.

        **Returns:**

        * **tuple**: (Success boolean, Message string).
        """
        endpoint_url = f"opc.tcp://{host}:{port}"
        if client_name in self._clients:

            return True, f"Client Name {client_name} duplicated"

        opcua_client = Client(endpoint_url, client_name=client_name)
        
        message, status_connection = opcua_client.connect()
        if status_connection==200:

            self._clients[client_name] = opcua_client
            
            # DATABASE PERSISTENCY
            if self.logger.get_db():
                
                OPCUA.create(client_name=client_name, host=host, port=port)

            # RECONNECT TO SUBSCRIPTION 
            for tag in self.cvt.get_tags():
                
                if tag["opcua_address"]==endpoint_url:

                    if not tag["scan_time"]:

                        subscription = opcua_client.create_subscription(1000, self.das)
                        node_id = opcua_client.get_node_id_by_namespace(tag["node_namespace"])
                        self.das.subscribe(subscription=subscription, client_name=client_name, node_id=node_id)

                    self.das.restart_buffer(tag=self.cvt.get_tag(id=tag["id"]))
        
            return True, message
        
        return False, message

    @logging_error_handler
    def remove(self, client_name:str):
        r"""
        Disconnects and removes an OPC UA Client.

        **Parameters:**

        * **client_name** (str): The name of the client to remove.

        **Returns:**

        * **bool**: True if successful, False otherwise.
        """
        if client_name in self._clients:
            try:
                opcua_client = self._clients.pop(client_name)
                opcua_client.disconnect()
                # DATABASE PERSISTENCY
                opcua = OPCUA.get_by_client_name(client_name=client_name)
                if opcua:
                    if self.logger.get_db():
                        query = OPCUA.delete().where(OPCUA.client_name == client_name)
                        query.execute()

                return True
            except Exception as err:

                return False
        
        return False

    @logging_error_handler
    def connect(self, client_name:str)->dict:
        r"""
        Connects a specific client.

        **Parameters:**

        * **client_name** (str): Client name.
        """
        if client_name in self._clients:

            self._clients[client_name].connect()

    @logging_error_handler
    def disconnect(self, client_name:str)->dict:
        r"""
        Disconnects a specific client.

        **Parameters:**

        * **client_name** (str): Client name.
        """
        if client_name in self._clients:

            self._clients[client_name].disconnect()

    @logging_error_handler
    def get(self, client_name:str)->Client:
        r"""
        Retrieves a client instance by name.

        **Parameters:**

        * **client_name** (str): Client name.

        **Returns:**

        * **Client**: The client object.
        """
        if client_name in self._clients:

            return self._clients[client_name]
        
    @logging_error_handler
    def get_opcua_tree(self, client_name):
        r"""
        Browses the OPC UA address space tree starting from the root folder.

        **Parameters:**

        * **client_name** (str): Client name.

        **Returns:**

        * **tuple**: (Tree dict, HTTP status code).
        """
        client = self.get(client_name=client_name)
        if client.is_connected():
            root_node = client.get_root_node()
            _tree = client.browse_tree(root_node)
            result = {
                "Objects": _tree[0]["children"]
            }
            return result, 200
        
        return {}, 400
        
    @logging_error_handler
    def get_node_values(self, client_name:str, namespaces:list)->list:
        r"""
        Reads values from multiple nodes.

        **Parameters:**

        * **client_name** (str): Client name.
        * **namespaces** (list): List of node namespaces/IDs.

        **Returns:**

        * **list**: Values.
        """

        if client_name in self._clients:

            client = self._clients[client_name]
            if client.is_connected():
                return client.get_nodes_values(namespaces=namespaces)
        
        return list()
        
    @logging_error_handler
    def get_client_by_address(self, opcua_address:str)->Client|None:
        r"""
        Retrieves a client by its server address URL.
        
        **Parameters:**

        * **opcua_address** (str): OPC UA Server URL (e.g., "opc.tcp://localhost:4840").
        
        **Returns:**

        * **Client**: The connected client object or None.
        """
        for client_name, client in self._clients.items():
            if opcua_address == client.serialize()["server_url"]:
                if client.is_connected():
                    return client
        return None
    
    @logging_error_handler
    def get_node_value_by_opcua_address(self, opcua_address:str, namespace:str)->list:
        r"""
        Reads a node value using the server address to find the client.

        **Parameters:**

        * **opcua_address** (str): Server URL.
        * **namespace** (str): Node ID.
        """
        for client_name, client in self._clients.items():

            if opcua_address==client.serialize()["server_url"]:
                if client.is_connected():
                    return self.get_node_attributes(client_name=client_name, namespaces=[namespace])
    
    @logging_error_handler 
    def get_node_attributes(self, client_name:str, namespaces:list)->list:
        r"""
        Reads attributes (Description, DataType, etc.) for a list of nodes.

        **Parameters:**

        * **client_name** (str): Client name.
        * **namespaces** (list): List of Node IDs.

        **Returns:**

        * **list**: List of attribute dictionaries.
        """

        result = list()

        if client_name in self._clients:

            client = self._clients[client_name]

            if client.is_connected():
                for namespace in namespaces:
                    result.append(client.get_node_attributes(node_namespace=namespace))

        return result

    @logging_error_handler
    def serialize(self, client_name:str=None)->dict:
        r"""
        Serializes client configurations.

        **Parameters:**

        * **client_name** (str, optional): Specific client to serialize.

        **Returns:**

        * **dict**: Dictionary of serialized client data.
        """
        if client_name:

            if client_name in self._clients:

                opcua_client = self._clients[client_name]

            return opcua_client.serialize()

        return {client_name: client.serialize() for client_name, client in self._clients.items()}