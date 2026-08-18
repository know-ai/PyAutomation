from peewee import Proxy, Model

proxy = Proxy()

SQLITE = 'sqlite'
MYSQL = 'mysql'
POSTGRESQL = 'postgresql'


class BaseModel(Model):
    r"""
    Base model class for all database models.

    It provides common utility methods for CRUD operations and serialization.
    Inherits from `peewee.Model` and uses a dynamic database proxy.
    """

    @classmethod
    def read(cls, id:int|str):
        r"""
        Select a single record by its ID.

        **Parameters:**

        * **id** (int|str): The primary key of the record.

        **Returns:**

        * **Model**: The model instance if found, otherwise None.
        """
        query = cls.select().where(cls.id == id).get_or_none()

        if query:
            
            return query

    @classmethod
    def read_all(cls):
        r"""
        Retrieves all records from the table.

        **Returns:**

        * **list**: A list of serialized dictionaries representing all records.
        """
        data = []
        try:
            for query in cls.select():
                try:
                    data.append(query.serialize())
                except Exception as e:
                    # Si hay un error al serializar un registro, registrar y continuar
                    import logging
                    logging.warning(f"Error serializing {cls.__name__} record (id={query.id if hasattr(query, 'id') else 'unknown'}): {e}")
                    continue
        except Exception as e:
            # Si hay un error general, registrar y devolver lista vacía
            import logging
            logging.error(f"Error reading all {cls.__name__} records: {e}")
            return []

        return data

    @classmethod
    def scoped(cls, *, area: str | None = None, owner_node: str | None = None):
        """Construye una consulta acotada usando las dimensiones del modelo."""
        query = cls.select()
        applied = False
        fields = cls._meta.fields
        if area is not None and "area" in fields:
            query = query.where(fields["area"] == area)
            applied = True
        if owner_node is not None and "owner_node" in fields:
            query = query.where(fields["owner_node"] == owner_node)
            applied = True
        if not applied:
            raise ValueError(
                f"{cls.__name__} has no compatible scope for the supplied identity"
            )
        return query

    @classmethod
    def read_scoped(
        cls,
        *,
        area: str | None = None,
        owner_node: str | None = None,
    ) -> list[dict]:
        return [row.serialize() for row in cls.scoped(area=area, owner_node=owner_node)]

    @classmethod
    def put(cls, id:str, **fields):
        r"""
        Updates a record by its ID.

        **Parameters:**

        * **id** (str): The primary key of the record to update.
        * **fields**: Keyword arguments representing the fields to update.

        **Returns:**

        * **query**: The execution result.
        """     
        if cls.id_exists(id):
            
            query = cls.update(**fields).where(cls.id == id)
            query.execute()
            return query            

    @classmethod
    def id_exists(cls, id:str|int)->bool|None:
        r"""
        Checks if a record exists by its ID.

        **Parameters:**

        * **id** (int|str): Record ID.

        **Returns:**

        * **bool**: True if the record exists, False otherwise.
        """
        return True if cls.get_or_none(id=id) else False

    class Meta:
        database = proxy