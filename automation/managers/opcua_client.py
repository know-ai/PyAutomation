from ..opcua.models import Client
from ..dbmodels import OPCUA
from ..logger.datalogger import DataLoggerEngine
from ..tags import CVTEngine
from ..opcua.subscription import DAS

class OPCUAClientManager:
    r"""
    Documentation here
    """

    def __init__(self):
        r"""
        Documentation here
        """
        self._clients = dict()
        self.logger = DataLoggerEngine()
        self.cvt = CVTEngine()
        self.das = DAS()

    def discovery(self, host:str='127.0.0.1', port:int=4840)->list[dict]:
        r"""
        Documentation here
        """
        return Client.find_servers(host, port)

    def add(self, client_name:str, host:str, port:int):
        r"""
        Documentation here
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

    def remove(self, client_name:str):
        r"""
        Documentation here
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

    def connect(self, client_name:str)->dict:
        r"""
        Documentation here
        """
        if client_name in self._clients:

            self._clients[client_name].connect()

    def disconnect(self, client_name:str)->dict:
        r"""
        Documentation here
        """
        if client_name in self._clients:

            self._clients[client_name].disconnect()

    def get(self, client_name:str)->Client:
        r"""
        Documentation here
        """
        if client_name in self._clients:

            return self._clients[client_name]
        
    def get_opcua_tree(self, client_name):
        r"""
        Documentation here
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
        
    def get_node_values(self, client_name:str, namespaces:list)->list:

        if client_name in self._clients:

            client = self._clients[client_name]
            if client.is_conneted():
                return client.get_nodes_values(namespaces=namespaces)
        
    def get_node_value_by_opcua_address(self, opcua_address:str, namespace:str)->list:
        r"""
        Documentation here
        """
        for client_name, client in self._clients.items():

            if opcua_address==client.serialize()["server_url"]:
                if client.is_connected():
                    return self.get_node_attributes(client_name=client_name, namespaces=[namespace])
        
    def get_node_attributes(self, client_name:str, namespaces:list)->list:

        result = list()

        if client_name in self._clients:

            client = self._clients[client_name]

            for namespace in namespaces:
                if client.is_connected():
                    result.append(client.get_node_attributes(node_namespace=namespace))

            return result

    def serialize(self, client_name:str=None)->dict:
        r"""
        Documentation here
        """
        if client_name:

            if client_name in self._clients:

                opcua_client = self._clients[client_name]

            return opcua_client.serialize()

        return {client_name: client.serialize() for client_name, client in self._clients.items()}