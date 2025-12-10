from peewee import CharField, IntegerField
from ..dbmodels.core import BaseModel

class OPCUA(BaseModel):
    r"""
    Database model for OPC UA Client configurations.
    """
    
    client_name = CharField(unique=True)
    host = CharField()
    port = IntegerField()

    @classmethod
    def create(cls, client_name:str, host:str, port:int):
        r"""
        Creates a new OPC UA client configuration.

        **Parameters:**

        * **client_name** (str): Unique name for the client.
        * **host** (str): Server hostname or IP.
        * **port** (int): Server port.

        **Returns:**

        * **OPCUA**: The created record.
        """

        if not cls.client_name_exist(client_name):

            query = cls(client_name=client_name, host=host, port=port)
            query.save()

            return query
        
    @classmethod
    def get_by_client_name(cls, client_name:str):
        r"""
        Retrieves a client configuration by name.
        """
        return cls.get_or_none(client_name=client_name)
    
    @classmethod
    def client_name_exist(cls, client_name:str):
        r"""
        Checks if a client name exists.
        """
        query = cls.get_or_none(client_name=client_name)
        
        if query is not None:

            return True
        
        return False
    
    def serialize(self):
        r"""
        Serializes the client configuration.
        """
        return {
            "client_name": self.client_name,
            "host": self.host,
            "port": self.port
        }