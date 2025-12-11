from peewee import CharField, ForeignKeyField
from ..dbmodels.core import BaseModel

class AccessType(BaseModel):
    r"""
    Database model for OPC UA Node Access Types (Read, Write, ReadWrite).
    """
    
    name = CharField(unique=True)

    @classmethod
    def create(cls, name:str="Read")-> dict:
        r"""
        Creates a new Access Type.

        **Parameters:**

        * **name** (str): Access type name.

        **Returns:**

        * **AccessType**: The created or existing record.
        """
        if name.lower()=="read" or name.lower()=="write" or name.lower()=="readwrite":

            access_type_obj = cls.read_by_name(name=name)
            
            if not access_type_obj:
                query = cls(name=name)
                query.save()  
                return query
            
        return cls.read_by_name(name=name)

    @classmethod
    def read_by_name(cls, name:str)->bool:
        r"""
        Retrieves an Access Type by name.
        """
        query = cls.get_or_none(name=name)
        
        if query is not None:

            return query
        
        return None

    @classmethod
    def name_exist(cls, name:str)->bool:
        r"""
        Checks if an Access Type name exists.
        """
        query = cls.get_or_none(name=name)
        
        if query is not None:

            return True
        
        return False

    def serialize(self)-> dict:
        r"""
        Serializes the record.
        """

        return {
            "id": self.id,
            "name": self.name
        }


class OPCUAServer(BaseModel):
    r"""
    Database model for OPC UA Server Node configurations.
    """
    
    name = CharField(unique=True)
    namespace = CharField(unique=True)
    access_type = ForeignKeyField(AccessType, null=True)

    @classmethod
    def create(cls, name:str, namespace:str, access_type:str)-> dict:
        r"""
        Creates a new OPC UA Server Node record.

        **Parameters:**

        * **name** (str): Node name.
        * **namespace** (str): Node namespace/ID.
        * **access_type** (str): Access level.

        **Returns:**

        * **OPCUAServer**: The created record.
        """
        if not cls.name_exist(name=name):
            
            if not cls.namespace_exist(namespace=namespace):
                
                if AccessType.name_exist(name=access_type):
                    access_type_obj = AccessType.read_by_name(name=access_type)
                else:
                    access_type_obj = AccessType.create(name=access_type)
                
                if access_type_obj:

                    query = cls(
                        name=name,
                        namespace=namespace,
                        access_type=access_type_obj
                        )
                    query.save()

                    return query

    @classmethod
    def read_by_name(cls, name:str)->bool:
        r"""
        Retrieves a node by name.
        """
        query = cls.get_or_none(name=name)
        
        if query is not None:

            return query
        
        return None
    
    @classmethod
    def read_by_namespace(cls, namespace:str)->bool:
        r"""
        Retrieves a node by namespace.
        """
        query = cls.get_or_none(namespace=namespace)
        
        if query is not None:

            return query
        
        return None

    @classmethod
    def name_exist(cls, name:str)->bool:
        r"""
        Checks if a node name exists.
        """
        query = cls.get_or_none(name=name)
        
        if query is not None:

            return True
        
        return False
    
    @classmethod
    def namespace_exist(cls, namespace:str)->bool:
        r"""
        Checks if a node namespace exists.
        """
        query = cls.get_or_none(namespace=namespace)
        
        if query is not None:

            return True
        
        return False
    
    @classmethod
    def update_access_type(cls, namespace:str, access_type:str)-> dict:
        r"""
        Updates the access type of an existing node.

        **Parameters:**

        * **namespace** (str): The node namespace.
        * **access_type** (str): The new access type.
        """
        obj = cls.get_or_none(namespace=namespace)
        
        if obj:
            
            if AccessType.name_exist(name=access_type):
                access_type_obj = AccessType.read_by_name(name=access_type)
            else:
                access_type_obj = AccessType.create(name=access_type)

            if access_type_obj:
                
                query = cls.update(access_type=access_type_obj).where(cls.id == obj.id)
                query.execute()
                return query

    def serialize(self)-> dict:
        r"""
        Serializes the node record.
        """

        return {
            "id": self.id,
            "name": self.name,
            "namespace": self.namespace,
            "access_type": self.access_type.serialize()
        }