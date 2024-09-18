from peewee import CharField, IntegerField
from automation.dbmodels.core import BaseModel

class OPCUA(BaseModel):

    client_name = CharField(unique=True)
    host = CharField()
    port = IntegerField()

    @classmethod
    def create(cls, client_name:str, host:str, port:int):
        r"""
        You can use Model.create() to create a new model instance. This method accepts keyword arguments, where the keys correspond 
        to the names of the model's fields. A new instance is returned and a row is added to the table.

        ```python
        >>> AlarmsType.create(name='High-High')
        {
            'message': (str)
            'data': (dict) {
                'name': 'HIGH-HIGH'
            }
        }
        ```
        
        This will INSERT a new row into the database. The primary key will automatically be retrieved and stored on the model instance.

        **Parameters**

        * **name:** (str), Industrial protocol name

        **Returns**

        * **result:** (dict) --> {'message': (str), 'data': (dict) row serialized}

        """

        if not cls.client_name_exist(client_name):

            query = cls(client_name=client_name, host=host, port=port)
            query.save()

            return query
        
    @classmethod
    def get_by_client_name(cls, client_name:str):
        r"""
        Documentation here
        """
        return cls.get_or_none(client_name=client_name)
    
    @classmethod
    def client_name_exist(cls, client_name:str):
        r"""
        Verify is a name exist into database

        **Parameters**

        * **name:** (str) Variable name

        **Returns**

        * **bool:** If True, name exist into database 
        """
        query = cls.get_or_none(client_name=client_name)
        
        if query is not None:

            return True
        
        return False
    
    def serialize(self):
        r"""
        Documentation here
        """
        return {
            "client_name": self.client_name,
            "host": self.host,
            "port": self.port
        }
