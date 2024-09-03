from automation.opcua.models import Client

class OPCUAClientManager:
    r"""
    Documentation here
    """

    def __init__(self):
        r"""
        Documentation here
        """
        self._clients = dict()

    def discovery(self, host:str='127.0.0.1', port:int=4840)->list[dict]:
        r"""
        Documentation here
        """
        return Client.find_servers(host, port)

    def add(self, client_name:str, endpoint_url:str):
        r"""
        Documentation here
        """
        if client_name in self._clients:

            return KeyError(f"Client Name {client_name} duplicated")
        
        opcua_client = Client(endpoint_url)
        message, status_connection = opcua_client.connect()
        if status_connection==200:

            self._clients[client_name] = opcua_client
        
        return message

    def remove(self, client_name:str):
        r"""
        Documentation here
        """
        if client_name in self._clients:

            opcua_client = self._clients.pop(client_name)
            opcua_client.disconnect()

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
        return client.get_opc_ua_tree()
        
    def get_node_values(self, client_name:str, namespaces:list)->list:

        if client_name in self._clients:

            client = self._clients[client_name]

            return client.get_nodes_values(namespaces=namespaces)


    def serialize(self, client_name:str=None)->dict:
        r"""
        Documentation here
        """
        if client_name:

            if client_name in self._clients:

                opcua_client = self._clients[client_name]

            return opcua_client.serialize()

        return {client_name: client.serialize() for client_name, client in self._clients.items()}