from datetime import datetime
import logging
from ..utils import _colorize_message
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
            str_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            logging.info(f"OPC UA client {client_name} connected successfully")
            print(_colorize_message(f"[{str_date}] [INFO] OPC UA client {client_name} connected successfully", "INFO"))
            self._clients[client_name] = opcua_client
            
            # DATABASE PERSISTENCY
            if self.logger.get_db():
                
                OPCUA.create(client_name=client_name, host=host, port=port)

            # RECONNECT TO SUBSCRIPTION 
            # Buscar tags que usan este cliente (por nombre o por URL)
            for tag in self.cvt.get_tags():
                tag_id = tag.get("id")
                if not tag_id:
                    continue
                
                tag_obj = self.cvt.get_tag(id=tag_id)
                should_reconnect = False
                
                if tag_obj:
                    # Verificar si el tag usa este cliente
                    # Opción 1: Si el tag tiene opcua_client_name que coincida (case-insensitive)
                    if hasattr(tag_obj, 'opcua_client_name') and tag_obj.opcua_client_name:
                        if tag_obj.opcua_client_name.lower() == client_name.lower():
                            should_reconnect = True
                    # Opción 2: Compatibilidad hacia atrás - si usa la URL
                    elif tag.get("opcua_address") == endpoint_url:
                        should_reconnect = True
                        # Si el tag tenía URL pero no nombre, actualizar para usar el nombre del cliente
                        if hasattr(tag_obj, 'set_opcua_client_name'):
                            tag_obj.set_opcua_client_name(client_name)
                
                if should_reconnect:
                    if not tag.get("scan_time"):
                        subscription = opcua_client.create_subscription(1000, self.das)
                        node_id = opcua_client.get_node_id_by_namespace(tag["node_namespace"])
                        self.das.subscribe(subscription=subscription, client_name=client_name, node_id=node_id)
                    self.das.restart_buffer(tag=tag_obj)
        
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
    def update(self, old_client_name:str, new_client_name:str=None, host:str=None, port:int=None):
        r"""
        Updates an existing OPC UA Client configuration.

        **Parameters:**

        * **old_client_name** (str): The current name of the client to update (required).
        * **new_client_name** (str, optional): New name for the client. If None, keeps the current name.
        * **host** (str, optional): New server host. If None, keeps the current host.
        * **port** (int, optional): New server port. If None, keeps the current port.

        **Returns:**

        * **tuple**: (Success boolean, Message string).
        """
        if old_client_name not in self._clients:
            return False, f"Client '{old_client_name}' not found"
        
        # Obtener el cliente actual
        old_client = self._clients[old_client_name]
        old_serialized = old_client.serialize()
        old_endpoint_url = old_serialized["server_url"]
        
        # Extraer host y port actuales del endpoint URL
        old_host = None
        old_port = None
        try:
            if old_endpoint_url.startswith("opc.tcp://"):
                parts = old_endpoint_url.replace("opc.tcp://", "").split(":")
                if len(parts) == 2:
                    old_host = parts[0]
                    old_port = int(parts[1])
        except:
            pass
        
        # Si no se proporcionan nuevos valores, usar los actuales
        if new_client_name is None:
            new_client_name = old_client_name
        if host is None:
            host = old_host
        if port is None:
            port = old_port
        
        # Si no hay cambios, retornar éxito sin hacer nada
        if new_client_name == old_client_name and host == old_host and port == old_port:
            return True, f"Client '{old_client_name}' configuration unchanged"
        
        # Si el nuevo nombre es diferente, verificar que no exista
        if new_client_name != old_client_name and new_client_name in self._clients:
            return False, f"Client name '{new_client_name}' already exists"
        
        # Si solo cambió el nombre (host y port son iguales), actualizar solo en memoria y BD
        if host == old_host and port == old_port and new_client_name != old_client_name:
            # Solo cambiar el nombre sin desconectar/reconectar
            self._clients[new_client_name] = self._clients.pop(old_client_name)
            # Actualizar nombre del cliente interno si tiene ese atributo
            if hasattr(old_client, 'name'):
                old_client.name = new_client_name
            
            # Actualizar en la base de datos
            if self.logger.get_db():
                opcua = OPCUA.get_by_client_name(client_name=old_client_name)
                if opcua:
                    # Eliminar el registro viejo
                    query = OPCUA.delete().where(OPCUA.client_name == old_client_name)
                    query.execute()
                    # Crear nuevo registro con el nuevo nombre
                    OPCUA.create(client_name=new_client_name, host=old_host, port=old_port)
            
            # IMPORTANTE: Actualizar todos los tags que referencian este cliente por nombre
            # Buscar tags que usan el nombre antiguo del cliente (case-insensitive)
            tags = self.cvt.get_tags()
            for tag in tags:
                tag_id = tag.get("id")
                if not tag_id:
                    continue
                
                tag_obj = self.cvt.get_tag(id=tag_id)
                if tag_obj and hasattr(tag_obj, 'opcua_client_name') and tag_obj.opcua_client_name:
                    # Comparación case-insensitive para detectar el cliente
                    if tag_obj.opcua_client_name.lower() == old_client_name.lower():
                        # Actualizar el nombre del cliente en el tag
                        tag_obj.set_opcua_client_name(new_client_name)
                        # También actualizar en la base de datos si está conectada
                        if self.logger.get_db():
                            from ..dbmodels import Tags
                            db_tag = Tags.get_or_none(identifier=tag_id)
                            if db_tag:
                                db_tag.opcua_client_name = new_client_name
                                db_tag.save()
            
            str_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            logging.info(f"OPC UA client '{old_client_name}' renamed to '{new_client_name}' successfully")
            print(_colorize_message(f"[{str_date}] [INFO] OPC UA client '{old_client_name}' renamed to '{new_client_name}' successfully", "INFO"))
            return True, f"Client '{old_client_name}' renamed to '{new_client_name}' successfully"
        
        # Si cambió host/port (con o sin cambio de nombre), necesitamos reconectar
        # Guardar si estaba conectado
        was_connected = old_client.is_connected()
        
        # Desconectar el cliente antiguo
        try:
            if was_connected:
                old_client.disconnect()
        except Exception as err:
            str_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            logging.warning(f"Error disconnecting old client {old_client_name}: {err}")
            print(_colorize_message(f"[{str_date}] [WARNING] Error disconnecting old client {old_client_name}: {err}", "WARNING"))
        
        # Remover de memoria temporalmente (guardar referencia para restaurar si falla)
        temp_client = self._clients.pop(old_client_name)
        
        # Actualizar en la base de datos
        if self.logger.get_db():
            opcua = OPCUA.get_by_client_name(client_name=old_client_name)
            if opcua:
                if new_client_name != old_client_name:
                    # Si cambió el nombre, eliminar el registro viejo
                    query = OPCUA.delete().where(OPCUA.client_name == old_client_name)
                    query.execute()
                    # Crear nuevo registro con nueva configuración
                    OPCUA.create(client_name=new_client_name, host=host, port=port)
                else:
                    # Si solo cambió host/port, actualizar el registro
                    opcua.host = host
                    opcua.port = port
                    opcua.save()
        
        # Crear nuevo cliente con la nueva configuración
        endpoint_url = f"opc.tcp://{host}:{port}"
        opcua_client = Client(endpoint_url, client_name=new_client_name)
        
        # Intentar conectar con la nueva configuración
        message, status_connection = opcua_client.connect()
        
        if status_connection == 200:
            str_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            logging.info(f"OPC UA client {new_client_name} updated and connected successfully")
            print(_colorize_message(f"[{str_date}] [INFO] OPC UA client {new_client_name} updated and connected successfully", "INFO"))
            self._clients[new_client_name] = opcua_client
            
            # Actualizar referencias en tags cuando cambia la configuración del cliente
            # Buscar tags que usan este cliente (por nombre o por URL antigua)
            tags = self.cvt.get_tags()
            new_endpoint_url = f"opc.tcp://{host}:{port}"
            
            for tag in tags:
                tag_id = tag.get("id")
                if not tag_id:
                    continue
                
                # Verificar si el tag usa este cliente
                # Opción 1: Si el tag tiene opcua_client_name que coincida
                tag_obj = self.cvt.get_tag(id=tag_id)
                should_update = False
                
                if tag_obj:
                    # Si el tag tiene opcua_client_name, verificar si coincide con el cliente actualizado
                    # Usar comparación case-insensitive para ser más robusto
                    if hasattr(tag_obj, 'opcua_client_name') and tag_obj.opcua_client_name:
                        tag_client_name_lower = tag_obj.opcua_client_name.lower()
                        if tag_client_name_lower == old_client_name.lower() or tag_client_name_lower == new_client_name.lower():
                            should_update = True
                    # Opción 2: Compatibilidad hacia atrás - si usa la URL antigua
                    elif tag.get("opcua_address") == old_endpoint_url:
                        should_update = True
                        # Si el tag tenía URL pero no nombre, actualizar para usar el nombre del cliente
                        if hasattr(tag_obj, 'set_opcua_client_name'):
                            tag_obj.set_opcua_client_name(new_client_name)
                
                if should_update:
                    # Actualizar opcua_address en el tag (mantener compatibilidad)
                    self.cvt.update_tag(id=tag_id, opcua_address=new_endpoint_url)
                    # También actualizar opcua_client_name si el método existe
                    tag_obj = self.cvt.get_tag(id=tag_id)
                    if tag_obj and hasattr(tag_obj, 'set_opcua_client_name'):
                        tag_obj.set_opcua_client_name(new_client_name)
                    
                    # Actualizar en la base de datos si está conectada
                    if self.logger.get_db():
                        from ..dbmodels import Tags
                        db_tag = Tags.get_or_none(identifier=tag_id)
                        if db_tag:
                            db_tag.opcua_address = new_endpoint_url
                            db_tag.opcua_client_name = new_client_name
                            db_tag.save()
                    
                    # Reconectar suscripciones si es necesario
                    if tag_obj:
                        if not tag.get("scan_time"):
                            subscription = opcua_client.create_subscription(1000, self.das)
                            node_id = opcua_client.get_node_id_by_namespace(tag.get("node_namespace", ""))
                            if node_id:
                                self.das.subscribe(subscription=subscription, client_name=new_client_name, node_id=node_id)
                        self.das.restart_buffer(tag=tag_obj)
            
            return True, message
        
        # Si la conexión falló, restaurar el cliente anterior solo si el nombre no cambió
        if new_client_name == old_client_name:
            try:
                # Restaurar cliente en memoria
                self._clients[old_client_name] = temp_client
                # Si estaba conectado, intentar reconectar
                if was_connected:
                    old_message, old_status = temp_client.connect()
                    if old_status == 200:
                        # Revertir cambios en la base de datos
                        if self.logger.get_db():
                            opcua = OPCUA.get_by_client_name(client_name=old_client_name)
                            if opcua:
                                opcua.host = old_host
                                opcua.port = old_port
                                opcua.save()
                        return False, f"Failed to connect to new server. Client restored to previous configuration. Error: {message}"
            except Exception as restore_err:
                str_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                logging.warning(f"Failed to restore old client {old_client_name}: {restore_err}")
                print(_colorize_message(f"[{str_date}] [WARNING] Failed to restore old client {old_client_name}: {restore_err}", "WARNING"))
        
        return False, message

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
        if not client:
            return {}, 404
        if client.is_connected():
            root_node = client.get_root_node()
            _tree = client.browse_tree(root_node)
            result = {
                "Objects": _tree[0]["children"]
            }
            return result, 200
    
        
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
    def get_client_name_by_address(self, opcua_address:str)->str|None:
        r"""
        Obtiene el nombre del cliente OPC UA basándose en su URL de servidor.
        
        **Parameters:**

        * **opcua_address** (str): OPC UA Server URL (e.g., "opc.tcp://localhost:4840").
        
        **Returns:**

        * **str|None**: Nombre del cliente si se encuentra, None en caso contrario.
        """
        # Buscar en clientes conectados
        for client_name, client in self._clients.items():
            if opcua_address == client.serialize()["server_url"]:
                return client_name
        
        # Si no está en memoria, buscar en la base de datos
        if self.logger.get_db():
            # Extraer host y port de la URL
            try:
                # Formato: opc.tcp://host:port
                url_parts = opcua_address.replace("opc.tcp://", "").split(":")
                if len(url_parts) == 2:
                    host = url_parts[0]
                    port = int(url_parts[1])
                    # Buscar en la base de datos
                    opcua_record = OPCUA.select().where(
                        (OPCUA.host == host) & (OPCUA.port == port)
                    ).first()
                    if opcua_record:
                        return opcua_record.client_name
            except Exception as e:
                logging.warning(f"Error resolving client name from address {opcua_address}: {e}")
        
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