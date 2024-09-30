from peewee import Proxy, Model

proxy = Proxy()

SQLITE = 'sqlite'
MYSQL = 'mysql'
POSTGRESQL = 'postgresql'


class BaseModel(Model):

    @classmethod
    def read(cls, id:int|str):
        r"""
        Select a single record

        You can use this method to retrieve a single instance matching the given query. 

        This method is a shortcut that calls Model.select() with the given query, but limits the result set to a single row. 
        Additionally, if no model matches the given query, a DoesNotExist exception will be raised.

        **Parameters**

        * **id:** (int), Record ID

        **Returns**

        * **result:** (dict) --> {'message': (str), 'data': (list) row serialized}

        """
        query = cls.select().where(cls.id == id).get_or_none()

        if query:
            
            return query

    @classmethod
    def read_all(cls):
        r"""
        Select all records

        You can use this method to retrieve all instances matching in the database. 

        This method is a shortcut that calls Model.select() with the given query.

        **Parameters**

        **Returns**

        * **result:** (dict) --> {'message': (str), 'data': (list) row serialized}
        """
        data = [query.serialize() for query in cls.select()]

        return data

    @classmethod
    def put(cls, id:str, **fields)-> dict:
        r""""
        Update a single record

        Once a model instance has a primary key, you UPDATE a field by its id. 
        The model's primary key will not change:
        """     
        if cls.id_exists(id):

            query = cls.update(**fields).where(cls.id == id)
            query.execute()
            return query
        
    # @classmethod
    # def delete(cls, id:int):
    #     r"""
    #     Delete record from database including 
    #     """
    #     query = super().delete().where(cls.id==id)
    #     query.execute()
            

    @classmethod
    def id_exists(cls, id:str|int)->bool|None:
        r"""
        Verify if a record exist by its id

        **Parameters**

        * **id:** (int) Record ID

        **Returns**

        * **bool:** If True, so id record exist into database
        """
        return True if cls.get_or_none(id=id) else False

    class Meta:
        database = proxy